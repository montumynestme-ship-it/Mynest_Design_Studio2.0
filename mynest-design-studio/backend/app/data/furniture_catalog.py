"""Mirror of the frontend furniture catalog: item_id -> (display name, room type).

Used to group placed furniture into rooms for room-aware AI prompts.
"""

FURNITURE: dict[str, tuple[str, str]] = {
    # --- Current library items ---
    "bed": ("Bed", "Bedroom"),
    "dressing-table": ("Dressing Table", "Bedroom"),
    "lounger-sofa": ("Loungers Sofa", "Living Room"),
    "center-table": ("Center Table", "Living Room"),
    "console": ("Console", "Living Room"),
    "partition": ("Partition", "Living Room"),
    "kitchen-base": ("Kitchen Base", "Kitchen"),
    "chimney": ("Chimney", "Kitchen"),
    "bay-window-seat": ("Bay Window Seating", "Living Room"),
    "shoe-rack": ("Shoe Rack", "Other"),
    "door": ("Door", "Other"),
    # --- Retired items (kept for existing plans' AI grouping) ---
    # Living Room
    "sofa-3": ("3 Seater Sofa", "Living Room"),
    "sofa-l": ("L-Shaped Sofa", "Living Room"),
    "armchair": ("Arm Chair", "Living Room"),
    "coffee-table": ("Coffee Table", "Living Room"),
    "tv-unit": ("TV Unit", "Living Room"),
    "bookshelf": ("Bookshelf", "Living Room"),
    # Bedroom
    "queen-bed": ("Queen Bed", "Bedroom"),
    "king-bed": ("King Bed", "Bedroom"),
    "wardrobe": ("Wardrobe", "Bedroom"),
    "side-table": ("Side Table", "Bedroom"),
    "dresser": ("Dresser", "Bedroom"),
    # Dining
    "dining-table": ("Dining Table", "Dining Room"),
    "dining-chair": ("Dining Chair", "Dining Room"),
    "bench": ("Bench", "Dining Room"),
    # Kitchen
    "refrigerator": ("Refrigerator", "Kitchen"),
    "cooktop": ("Cooktop", "Kitchen"),
    "sink": ("Sink", "Kitchen"),
    # Bathroom
    "bathtub": ("Bathtub", "Bathroom"),
    "shower": ("Shower", "Bathroom"),
    "washbasin": ("Washbasin", "Bathroom"),
    # Lighting (assigned to the nearest room)
    "floor-lamp": ("Floor Lamp", "Lighting"),
    "desk-lamp": ("Desk Lamp", "Lighting"),
}

BEDS = {"queen-bed", "king-bed", "bed"}

# Concise real-world appearance of each piece (FORM + defining features, kept
# material-neutral so the design-intent STYLE/MATERIALS still governs finishes).
# Fed into the AI-render prompt so the text-to-image model renders each object
# true to its type instead of guessing from a bare label. This is the same
# structured furniture knowledge the plan-view SVG icons encode, expressed as text.
VISUAL: dict[str, str] = {
    # Current library items
    "bed": "a bed with a tall upholstered headboard, duvet and pillows",
    "dressing-table": "a dressing table with a large mirror and a stool",
    "lounger-sofa": "a chaise lounge sofa with an extended seat",
    "center-table": "a low central coffee/center table",
    "console": "a narrow console table against the wall",
    "partition": "a slatted room-divider partition screen",
    "kitchen-base": "a run of base kitchen cabinets with a countertop",
    "chimney": "a kitchen chimney / cooker hood mounted above the hob",
    "bay-window-seat": "a cushioned bay-window bench seat set into a window nook",
    "shoe-rack": "a low shoe rack with open shelves",
    "door": "a hinged interior door",
    # Retired items
    "sofa-3": "a three-seater sofa with plush back and seat cushions and low arms",
    "sofa-l": "an L-shaped sectional sofa with a chaise and plush cushions",
    "armchair": "a single upholstered lounge armchair with arms",
    "coffee-table": "a low rectangular coffee table in front of the sofa",
    "tv-unit": "a long low media console with a large flat-screen TV mounted on the wall above it",
    "bookshelf": "a tall open bookshelf with horizontal shelves",
    "queen-bed": "a queen bed with a tall upholstered headboard, duvet and pillows",
    "king-bed": "a king bed with a tall upholstered headboard, duvet and pillows",
    "wardrobe": "a tall two-door wardrobe cabinet",
    "side-table": "a small low side/bedside table",
    "dresser": "a low chest of drawers with several drawer fronts",
    "dining-table": "a rectangular dining table",
    "dining-chair": "an upholstered dining chair with a backrest",
    "bench": "a long low backless bench seat",
    "refrigerator": "a tall double-door refrigerator",
    "cooktop": "a cooktop/hob with burners set into the countertop",
    "sink": "a kitchen sink basin set into the counter with a tall tap",
    "bathtub": "a bathtub",
    "shower": "a glass shower enclosure with an overhead rain-shower head",
    "washbasin": "a washbasin/vanity with a tap",
    "floor-lamp": "a slim standing floor lamp",
    "desk-lamp": "a small table/desk lamp",
}


def describe(item_id: str) -> tuple[str, str]:
    return FURNITURE.get(item_id, (item_id.replace("-", " ").title(), "Other"))


def describe_visual(item_id: str) -> str | None:
    """Appearance phrase for the AI-render prompt, or None for unknown items."""
    return VISUAL.get(item_id)
