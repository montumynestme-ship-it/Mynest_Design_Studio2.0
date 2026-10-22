# 🏠 Floor Plan Parser + 3D Reconstruction

Parse floor plan images into structured data — walls with thickness, doors, windows, and automatically detected rooms. Then generate interactive 3D models.

**🎮 Try it live:** [rikhoffbauer2/floorplan-3d](https://huggingface.co/spaces/rikhoffbauer2/floorplan-3d)

## Architecture

```
Floor Plan Image (raster or vector)
       │
       ▼
┌──────────────────────────────┐
│  1. INITIAL PARSE            │  VLM extracts walls/doors/windows
│     (VLM or vector parser)   │  into structured JSON schema
└──────────────────────────────┘
       │
       ▼
┌──────────────────────────────┐
│  2. COMPUTE TOPOLOGY         │  Derive rooms from wall faces
│     (computational geometry) │  via planar subdivision (Shapely)
└──────────────────────────────┘
       │
       ▼
┌──────────────────────────────┐
│  3. RENDER OVERLAY           │  Schema → SVG/PNG → alpha-composite
│     (PIL / SVG)              │  on original image for verification
└──────────────────────────────┘
       │
       ▼
┌──────────────────────────────┐
│  4. VERIFY & CORRECT         │  VLM sees overlay vs original,
│     (VLM or human)           │  outputs field-level corrections
└──────────────────────────────┘
       │
       ▼  converged? ──no──→ back to step 2
      yes
       ▼
┌──────────────────────────────┐
│  5. 3D RECONSTRUCTION        │  Extrude walls, cut openings,
│     (trimesh + manifold3d)   │  add floors/ceilings → GLB
└──────────────────────────────┘
       ▼
     Interactive 3D model (GLB/glTF)
```

## Modules

| File | Purpose |
|------|---------|
| `floorplan/schema.py` | Pydantic data models — `Wall`, `Opening`, `Room`, `FloorPlan`, `Correction` |
| `floorplan/geometry.py` | Computational geometry — wall polygons, room detection, centerline ops |
| `floorplan/renderer.py` | SVG + PIL rendering for visual verification and overlay |
| `floorplan/parser.py` | VLM-based parsing with iterative correction loop |
| `floorplan/reconstruction.py` | **NEW** — 3D mesh generation, boolean ops, GLB/OBJ export |

## The Schema

```json
{
  "walls": [
    {
      "id": "w1",
      "centerline": [{"x": 0, "y": 0}, {"x": 6, "y": 0}],
      "thickness": 0.24,
      "openings": [
        {"id": "win1", "type": "window", "start": 1.5, "length": 1.5}
      ]
    }
  ],
  "rooms": [
    {
      "id": "r1", "label": "bedroom",
      "boundary": [{"wall_id": "w1", "side": "right"}, {"wall_id": "w2", "side": "left"}],
      "area": 16.0
    }
  ]
}
```

## Quick Start

### Demo (no API key needed)

```python
from floorplan import *

# Build a floor plan
walls = [
    Wall(id="w1", centerline=[Point2D(x=0, y=0), Point2D(x=5, y=0)], thickness=0.24,
         openings=[Opening(id="d1", type=OpeningType.DOOR, start=1.0, length=0.9)]),
    Wall(id="w2", centerline=[Point2D(x=5, y=0), Point2D(x=5, y=4)], thickness=0.24),
    Wall(id="w3", centerline=[Point2D(x=5, y=4), Point2D(x=0, y=4)], thickness=0.24),
    Wall(id="w4", centerline=[Point2D(x=0, y=4), Point2D(x=0, y=0)], thickness=0.24),
]

rooms, room_polygons = build_rooms(walls)
fp = FloorPlan(walls=walls, rooms=rooms)

# 2D render
img = render_to_image(fp, room_polygons=room_polygons)
img.save("output.png")

# 3D model
scene = generate_3d_model(fp, room_polygons=room_polygons)
export_glb(scene, "model.glb")  # Open in any 3D viewer or Three.js
```

### Parse a real floor plan with VLM

```python
from floorplan import parse_floorplan, generate_3d_model, export_glb

# Parse image → structured data (uses HF Inference API)
fp, room_polygons, overlays = parse_floorplan(
    image="floorplan.png",
    api_key="hf_...",
    base_url="https://router.huggingface.co/v1",
    model="Qwen/Qwen2.5-VL-72B-Instruct",
    max_iterations=3,
)

# Generate 3D
scene = generate_3d_model(fp, room_polygons=room_polygons, pixels_per_meter=100)
export_glb(scene, "model.glb")
```

## 3D Output

The 3D reconstruction generates:
- **Walls** — extruded from 2D polygons, all walls boolean-unioned into a single watertight mesh
- **Door openings** — cut through walls via boolean subtraction + door frame meshes
- **Window openings** — cut at sill/head height + glass pane meshes
- **Floor slabs** — per room, with wood material
- **Ceilings** — per room, with white material
- **PBR materials** — walls (warm white), floors (light wood), ceilings (white), glass (translucent blue)

Export formats: **GLB** (web/Three.js), **glTF**, **OBJ**

## Dependencies

**Core:**
- `pydantic` — schema validation
- `shapely` — computational geometry
- `numpy` — array ops
- `pillow` — image rendering

**3D reconstruction:**
- `trimesh[easy]` — mesh generation, boolean ops, GLB export (includes manifold3d)

**VLM parsing (optional):**
- `openai` — for VLM API calls

## License

MIT
