"""Canonical Object Class Taxonomy for ML/DL Object Detection in MyNest Design Studio.

Maps the canonical Furniture Library items to normalized ML classes and class IDs.
Ensures single source of truth across dataset generation, YOLO training, inference,
and evaluation.
"""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MLClassInfo:
    class_id: int
    class_name: str
    item_id: str
    display_name: str
    category: str
    width_mm: float
    depth_mm: float
    height_mm: float
    kind: str
    svg_name: str
    has_meaningful_rotation: bool
    color_rgb: tuple[int, int, int]


# The 14 canonical Furniture Library items mapped to ML detection classes
CANONICAL_ML_CLASSES: list[MLClassInfo] = [
    MLClassInfo(
        class_id=0,
        class_name="loungers_sofa",
        item_id="lounger-sofa",
        display_name="Loungers Sofa",
        category="Living Room",
        width_mm=1900.0,
        depth_mm=900.0,
        height_mm=800.0,
        kind="sofa",
        svg_name="lounger.svg",
        has_meaningful_rotation=True,
        color_rgb=(200, 180, 150),
    ),
    MLClassInfo(
        class_id=1,
        class_name="center_table",
        item_id="center-table",
        display_name="Center Table",
        category="Living Room",
        width_mm=1000.0,
        depth_mm=600.0,
        height_mm=400.0,
        kind="coffee_table",
        svg_name="coffee-table.svg",
        has_meaningful_rotation=True,
        color_rgb=(160, 120, 80),
    ),
    MLClassInfo(
        class_id=2,
        class_name="console",
        item_id="console",
        display_name="Console",
        category="Living Room",
        width_mm=1100.0,
        depth_mm=350.0,
        height_mm=800.0,
        kind="dresser",
        svg_name="console.svg",
        has_meaningful_rotation=True,
        color_rgb=(180, 140, 100),
    ),
    MLClassInfo(
        class_id=3,
        class_name="partition",
        item_id="partition",
        display_name="Partition",
        category="Living Room",
        width_mm=1800.0,
        depth_mm=300.0,
        height_mm=1800.0,
        kind="generic",
        svg_name="partition.svg",
        has_meaningful_rotation=True,
        color_rgb=(138, 106, 69),
    ),
    MLClassInfo(
        class_id=4,
        class_name="bed",
        item_id="bed",
        display_name="Bed",
        category="Bedroom",
        width_mm=1800.0,
        depth_mm=2000.0,
        height_mm=1100.0,
        kind="bed",
        svg_name="bed.svg",
        has_meaningful_rotation=True,
        color_rgb=(111, 74, 46),
    ),
    MLClassInfo(
        class_id=5,
        class_name="side_table",
        item_id="side-table",
        display_name="Side Table",
        category="Bedroom",
        width_mm=450.0,
        depth_mm=450.0,
        height_mm=550.0,
        kind="side_table",
        svg_name="side-table.svg",
        has_meaningful_rotation=False,
        color_rgb=(170, 130, 90),
    ),
    MLClassInfo(
        class_id=6,
        class_name="dressing",
        item_id="dressing-table",
        display_name="Dressing",
        category="Bedroom",
        width_mm=1200.0,
        depth_mm=600.0,
        height_mm=750.0,
        kind="dresser",
        svg_name="dressing-table.svg",
        has_meaningful_rotation=True,
        color_rgb=(156, 122, 82),
    ),
    MLClassInfo(
        class_id=7,
        class_name="dining_table",
        item_id="dining-table",
        display_name="Dining Table",
        category="Dining & Kitchen",
        width_mm=1500.0,
        depth_mm=900.0,
        height_mm=750.0,
        kind="dining_table",
        svg_name="dining-table.svg",
        has_meaningful_rotation=True,
        color_rgb=(190, 150, 100),
    ),
    MLClassInfo(
        class_id=8,
        class_name="dining_chair",
        item_id="dining-chair",
        display_name="Dining Chair",
        category="Dining & Kitchen",
        width_mm=450.0,
        depth_mm=500.0,
        height_mm=900.0,
        kind="dining_chair",
        svg_name="chair.svg",
        has_meaningful_rotation=True,
        color_rgb=(176, 154, 122),
    ),
    MLClassInfo(
        class_id=9,
        class_name="kitchen_base",
        item_id="kitchen-base",
        display_name="Kitchen Base",
        category="Dining & Kitchen",
        width_mm=2400.0,
        depth_mm=600.0,
        height_mm=900.0,
        kind="dresser",
        svg_name="kitchen-base.svg",
        has_meaningful_rotation=True,
        color_rgb=(154, 160, 166),
    ),
    MLClassInfo(
        class_id=10,
        class_name="chimney",
        item_id="chimney",
        display_name="Chimney",
        category="Dining & Kitchen",
        width_mm=900.0,
        depth_mm=500.0,
        height_mm=600.0,
        kind="generic",
        svg_name="chimney.svg",
        has_meaningful_rotation=True,
        color_rgb=(184, 188, 192),
    ),
    MLClassInfo(
        class_id=11,
        class_name="bay_window_seating",
        item_id="bay-window-seat",
        display_name="Bay Window Seating",
        category="Entry & Structure",
        width_mm=1500.0,
        depth_mm=600.0,
        height_mm=450.0,
        kind="bench",
        svg_name="bay-window-seat.svg",
        has_meaningful_rotation=True,
        color_rgb=(200, 183, 158),
    ),
    MLClassInfo(
        class_id=12,
        class_name="shoe_rack",
        item_id="shoe-rack",
        display_name="Shoe Rack",
        category="Entry & Structure",
        width_mm=900.0,
        depth_mm=350.0,
        height_mm=600.0,
        kind="dresser",
        svg_name="shoe-rack.svg",
        has_meaningful_rotation=True,
        color_rgb=(138, 106, 69),
    ),
    MLClassInfo(
        class_id=13,
        class_name="door",
        item_id="door",
        display_name="Doors",
        category="Entry & Structure",
        width_mm=900.0,
        depth_mm=900.0,
        height_mm=2100.0,
        kind="door",
        svg_name="door.svg",
        has_meaningful_rotation=True,
        color_rgb=(122, 92, 59),
    ),
]

# Quick lookup indexes
CLASS_BY_ID: dict[int, MLClassInfo] = {c.class_id: c for c in CANONICAL_ML_CLASSES}
CLASS_BY_NAME: dict[str, MLClassInfo] = {c.class_name: c for c in CANONICAL_ML_CLASSES}
CLASS_BY_ITEM_ID: dict[str, MLClassInfo] = {c.item_id: c for c in CANONICAL_ML_CLASSES}

# Canonical list of class name strings in index order
CLASS_NAMES: list[str] = [c.class_name for c in CANONICAL_ML_CLASSES]
NUM_CLASSES: int = len(CANONICAL_ML_CLASSES)

# Extended catalog items (architectural structure & openings)
WINDOW_INFO = MLClassInfo(
    class_id=14,
    class_name="window",
    item_id="window",
    display_name="Window",
    category="Entry & Structure",
    width_mm=1200.0,
    depth_mm=200.0,
    height_mm=1200.0,
    kind="window",
    svg_name="window.svg",
    has_meaningful_rotation=True,
    color_rgb=(0, 229, 255),
)
CLASS_BY_ITEM_ID["window"] = WINDOW_INFO
CLASS_BY_NAME["window"] = WINDOW_INFO


def item_id_to_ml_class(item_id: str) -> str | None:
    """Map a furniture item_id (e.g. 'lounger-sofa' or 'bed') to canonical ML class name."""
    info = CLASS_BY_ITEM_ID.get(item_id)
    if info:
        return info.class_name
    # Fallback normalizations for aliases or legacy IDs
    normalized = item_id.lower().replace("-", "_")
    if normalized in CLASS_BY_NAME:
        return normalized
    if "window" in normalized and "bay" not in normalized:
        return "window"
    if "bed" in normalized and "side" not in normalized:
        return "bed"
    if "chair" in normalized:
        return "dining_chair"
    if "sofa" in normalized:
        return "loungers_sofa"
    return None


def ml_class_to_item_id(class_name: str) -> str:
    """Map an ML class name (e.g. 'loungers_sofa') back to catalog item_id."""
    info = CLASS_BY_NAME.get(class_name)
    if info:
        return info.item_id
    return class_name.replace("_", "-")


def class_name_to_id(class_name: str) -> int:
    """Get numeric 0-indexed ID for a class name."""
    info = CLASS_BY_NAME.get(class_name)
    if info is not None:
        return info.class_id
    raise ValueError(f"Unknown ML class name: {class_name}")


def class_id_to_name(class_id: int) -> str:
    """Get class name string for numeric ID."""
    info = CLASS_BY_ID.get(class_id)
    if info is not None:
        return info.class_name
    raise ValueError(f"Unknown ML class ID: {class_id}")


def get_yolo_yaml_dict() -> dict[int, str]:
    """Generate the names dictionary needed for YOLO data.yaml."""
    return {c.class_id: c.class_name for c in CANONICAL_ML_CLASSES}
