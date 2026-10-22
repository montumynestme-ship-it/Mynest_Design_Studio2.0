"""
VLM-based floor plan parser — extract structured wall/door/window data from floor plan images.

Uses a vision-language model (via OpenAI-compatible API) to:
1. Parse the floor plan image into the schema format
2. Optionally compare rendered overlay with original for corrections
"""

from __future__ import annotations

import base64
import io
import json
import re
from pathlib import Path
from typing import Optional

from PIL import Image

from .schema import (
    FloorPlan,
    Wall,
    Opening,
    OpeningType,
    Point2D,
    CorrectionResult,
    Correction,
    CorrectionAction,
)
from .geometry import build_rooms, compute_floor_plan_geometry


def _image_to_base64(image: Image.Image | str | Path) -> str:
    """Convert image to base64 data URI."""
    if isinstance(image, (str, Path)):
        image = Image.open(image)
    image = image.convert("RGB")
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{b64}"


def _extract_json_from_response(text: str) -> dict:
    """Extract JSON from a VLM response that may contain markdown code blocks or thinking tokens."""
    # Strip Qwen3-style thinking blocks
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    patterns = [
        r"```json\s*\n?(.*?)\n?\s*```",
        r"```\s*\n?(.*?)\n?\s*```",
        r"\{.*\}",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            try:
                candidate = match.group(1) if match.lastindex else match.group(0)
                return json.loads(candidate)
            except (json.JSONDecodeError, IndexError):
                continue
    raise ValueError(f"Could not extract JSON from response:\n{text[:500]}")


PARSE_SYSTEM_PROMPT = """You are an expert architectural floor plan parser. Your job is to analyze floor plan images and extract structured data about walls, doors, and windows.

IMPORTANT RULES:
1. All coordinates are in a consistent unit system (use the image pixel coordinates, we'll convert to meters later)
2. Walls are defined by their centerline (a polyline) and thickness
3. Doors and windows are defined by their position ALONG a wall's centerline
4. Each wall must connect to adjacent walls (shared endpoints or very close endpoints)
5. The wall network must form closed loops (rooms)
6. Exterior walls are typically thicker (15-30 pixels) than interior walls (8-15 pixels)
7. Curved walls should be approximated as polylines with many points

OUTPUT FORMAT:
You must output valid JSON matching this exact schema:
{
  "walls": [
    {
      "id": "w1",
      "centerline": [{"x": 100, "y": 50}, {"x": 500, "y": 50}],
      "thickness": 20,
      "openings": [
        {
          "id": "d1",
          "type": "door",
          "start": 50,
          "length": 80
        }
      ]
    }
  ]
}

WALL DETECTION GUIDELINES:
- Trace the CENTER of each wall, not its edges
- Each wall segment should be a straight run between junctions/corners
- At T-junctions and L-corners, start a new wall segment
- Estimate thickness by measuring the visible wall width in pixels
- Be precise with coordinates — they will be overlaid on the original image for verification

OPENING DETECTION GUIDELINES:
- "start" = distance from the first centerline point along the wall to where the opening begins
- "length" = length of the opening along the wall
- Doors typically show an arc swing or a gap in the wall
- Windows typically show parallel lines or a different fill pattern within the wall
- Double-check that start + length doesn't exceed the wall's total centerline length"""


CORRECTION_SYSTEM_PROMPT = """You are an expert architectural floor plan verifier. You are shown two images:

1. The ORIGINAL floor plan image
2. An OVERLAY showing the parsed schema rendered on top of the original

Your job is to compare them and identify discrepancies. Look for:
- Walls that are misaligned (rendered wall doesn't match original wall position)
- Missing walls (visible in original but not in the overlay)
- Extra walls (in overlay but not in original)
- Wrong wall thickness (too thick or too thin compared to original)
- Misplaced doors/windows (wrong position along the wall)
- Missing doors/windows (visible in original but not detected)
- Wrong opening sizes (too wide or too narrow)

OUTPUT FORMAT:
{
  "score": 0.85,
  "converged": false,
  "corrections": [
    {
      "action": "modify",
      "target": "w3",
      "field": "centerline",
      "value": [{"x": 150, "y": 200}, {"x": 150, "y": 500}],
      "reason": "Wall is about 20 pixels too far to the right"
    },
    {
      "action": "add",
      "target": null,
      "field": null,
      "value": {"id": "w11", "centerline": [{"x": 100, "y": 300}, {"x": 400, "y": 300}], "thickness": 12, "openings": []},
      "reason": "Interior partition wall visible in original but missing from parse"
    },
    {
      "action": "delete",
      "target": "w5",
      "field": null,
      "value": null,
      "reason": "This is not a wall - it's a staircase outline"
    }
  ]
}

SCORING GUIDE:
- 1.0: Perfect alignment, no corrections needed
- 0.9+: Minor tweaks only (small position adjustments)
- 0.7-0.9: Some walls need repositioning, maybe 1-2 missing
- 0.5-0.7: Major misalignments, several missing/extra walls
- <0.5: Fundamental errors, most walls wrong

Set "converged": true if score >= 0.92 or if remaining corrections are cosmetic only."""


class FloorPlanParser:
    """VLM-based floor plan parser with iterative correction."""

    def __init__(self, api_key=None, base_url=None, model="gpt-4o"):
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError("openai package required: pip install openai")
        kwargs = {}
        if api_key:
            kwargs["api_key"] = api_key
        if base_url:
            kwargs["base_url"] = base_url
        self.client = OpenAI(**kwargs)
        self.model = model

    def parse_image(self, image, detail="high", temperature=0.1):
        """Parse a floor plan image into the structured schema."""
        image_b64 = _image_to_base64(image)
        
        # For Qwen3 models, prepend /no_think to disable extended reasoning
        system_content = PARSE_SYSTEM_PROMPT
        if "Qwen3" in self.model:
            system_content = "/no_think\n" + system_content
        
        response = self.client.chat.completions.create(
            model=self.model, temperature=temperature, max_tokens=8192,
            messages=[
                {"role": "system", "content": system_content},
                {"role": "user", "content": [
                    {"type": "text", "text": "Parse this floor plan image. Extract ALL walls with their centerlines, thicknesses, and any doors/windows on them. Use pixel coordinates. Be thorough — every wall segment matters for room detection. Output ONLY the JSON, no explanation."},
                    {"type": "image_url", "image_url": {"url": image_b64, "detail": detail}},
                ]},
            ],
        )
        raw = response.choices[0].message.content
        data = _extract_json_from_response(raw)
        return self._data_to_floorplan(data)

    def critique_overlay(self, original_image, overlay_image, current_schema, iteration=1, temperature=0.2):
        """Compare overlay with original and generate corrections."""
        orig_b64 = _image_to_base64(original_image)
        overlay_b64 = _image_to_base64(overlay_image)
        schema_json = current_schema.model_dump_json(indent=2)
        
        system_content = CORRECTION_SYSTEM_PROMPT
        if "Qwen3" in self.model:
            system_content = "/no_think\n" + system_content
        
        response = self.client.chat.completions.create(
            model=self.model, temperature=temperature, max_tokens=4096,
            messages=[
                {"role": "system", "content": system_content},
                {"role": "user", "content": [
                    {"type": "text", "text": f"Iteration {iteration}. Compare these two images and identify corrections needed.\n\nCurrent schema ({len(current_schema.walls)} walls, {sum(len(w.openings) for w in current_schema.walls)} openings):\n```json\n{schema_json}\n```\n\nImage 1 is the ORIGINAL floor plan. Image 2 is the OVERLAY (parsed schema rendered on the original)."},
                    {"type": "image_url", "image_url": {"url": orig_b64, "detail": "high"}},
                    {"type": "image_url", "image_url": {"url": overlay_b64, "detail": "high"}},
                ]},
            ],
        )
        raw = response.choices[0].message.content
        data = _extract_json_from_response(raw)
        return CorrectionResult(
            iteration=iteration, score=data.get("score", 0.5), converged=data.get("converged", False),
            corrections=[
                Correction(action=CorrectionAction(c["action"]), target=c.get("target"),
                           field=c.get("field"), value=c.get("value"), reason=c["reason"])
                for c in data.get("corrections", [])
            ],
        )

    def apply_corrections(self, floorplan, corrections):
        """Apply corrections to a floor plan schema. Returns (new_floorplan, room_polygons)."""
        walls_dict = {w.id: w.model_dump() for w in floorplan.walls}
        for correction in corrections.corrections:
            if correction.action == CorrectionAction.DELETE:
                if correction.target and correction.target in walls_dict:
                    del walls_dict[correction.target]
            elif correction.action == CorrectionAction.ADD:
                if correction.value and isinstance(correction.value, dict):
                    wall_data = correction.value
                    wall_id = wall_data.get("id", f"w_new_{len(walls_dict)}")
                    walls_dict[wall_id] = wall_data
            elif correction.action == CorrectionAction.MODIFY:
                if not correction.target:
                    continue
                parts = correction.target.split(".")
                wall_id = parts[0]
                if wall_id not in walls_dict:
                    continue
                if len(parts) == 1 and correction.field:
                    walls_dict[wall_id][correction.field] = correction.value
                elif len(parts) == 3 and parts[1] == "openings":
                    opening_id = parts[2]
                    for op in walls_dict[wall_id].get("openings", []):
                        if op.get("id") == opening_id and correction.field:
                            op[correction.field] = correction.value
                            break
        new_walls = []
        for wall_data in walls_dict.values():
            try:
                new_walls.append(self._parse_wall(wall_data))
            except Exception as e:
                print(f"Warning: skipping wall due to error: {e}")
                continue
        rooms, room_polygons = build_rooms(new_walls, min_area=1.0)
        return FloorPlan(scale=floorplan.scale, origin=floorplan.origin, walls=new_walls, rooms=rooms), room_polygons

    def _data_to_floorplan(self, data):
        """Convert raw parsed JSON to FloorPlan with rooms detected."""
        walls = []
        for w in data.get("walls", []):
            try:
                walls.append(self._parse_wall(w))
            except Exception as e:
                print(f"Warning: skipping wall {w.get('id', '?')}: {e}")
                continue
        rooms, room_polygons = build_rooms(walls, min_area=100.0)
        fp = FloorPlan(walls=walls, rooms=rooms)
        return fp, room_polygons

    @staticmethod
    def _parse_wall(w):
        """Parse a wall from dict, handling various coordinate formats."""
        centerline = []
        for pt in w["centerline"]:
            if isinstance(pt, dict):
                centerline.append(Point2D(x=pt["x"], y=pt["y"]))
            elif isinstance(pt, (list, tuple)):
                centerline.append(Point2D(x=pt[0], y=pt[1]))
        openings = []
        for o in w.get("openings", []):
            openings.append(Opening(id=o["id"], type=OpeningType(o["type"]),
                                     start=float(o["start"]), length=float(o["length"])))
        return Wall(id=w["id"], centerline=centerline, thickness=float(w["thickness"]), openings=openings)


def parse_floorplan(image, api_key=None, base_url=None, model="gpt-4o",
                    max_iterations=4, convergence_threshold=0.92, verbose=True):
    """Full parse-render-correct pipeline.
    
    Returns (final_floorplan, room_polygons, overlay_images_per_iteration)
    """
    from .renderer import render_to_image, overlay_on_image
    parser = FloorPlanParser(api_key=api_key, base_url=base_url, model=model)
    if verbose:
        print("🔍 Parsing floor plan image...")
    floorplan, room_polygons = parser.parse_image(image)
    if verbose:
        print(f"   Found {len(floorplan.walls)} walls, "
              f"{sum(len(w.openings) for w in floorplan.walls)} openings, "
              f"{len(floorplan.rooms)} rooms")
    overlays = []
    for iteration in range(1, max_iterations + 1):
        if verbose:
            print(f"\n📐 Iteration {iteration}: rendering overlay...")
        overlay = overlay_on_image(floorplan, image, room_polygons=room_polygons,
                                    schema_opacity=0.6, original_opacity=0.7)
        overlays.append(overlay)
        if verbose:
            print(f"   Comparing overlay with original...")
        critique = parser.critique_overlay(original_image=image, overlay_image=overlay,
                                            current_schema=floorplan, iteration=iteration)
        if verbose:
            print(f"   Score: {critique.score:.2f}, Corrections: {len(critique.corrections)}, Converged: {critique.converged}")
            for c in critique.corrections:
                print(f"     - [{c.action.value}] {c.target or 'new'}: {c.reason}")
        if critique.converged or critique.score >= convergence_threshold:
            if verbose:
                print(f"\n✅ Converged at iteration {iteration} (score={critique.score:.2f})")
            break
        if not critique.corrections:
            if verbose:
                print(f"\n⚠️ No corrections suggested, stopping.")
            break
        floorplan, room_polygons = parser.apply_corrections(floorplan, critique)
        if verbose:
            print(f"   Applied corrections → {len(floorplan.walls)} walls, {len(floorplan.rooms)} rooms")
    final_overlay = overlay_on_image(floorplan, image, room_polygons=room_polygons,
                                      schema_opacity=0.6, original_opacity=0.7)
    overlays.append(final_overlay)
    return floorplan, room_polygons, overlays
