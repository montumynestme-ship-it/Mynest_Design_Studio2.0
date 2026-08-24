# PRODUCT REQUIREMENTS DOCUMENT (PRD)
# MYNEST DESIGN STUDIO — Full Recreation Specification & Technical Blueprint

---

## Document Control

| Metadata Field | Value |
|---|---|
| **Project Name** | MyNest Design Studio |
| **Document Type** | Master Product Requirements Document (PRD) |
| **Version** | 1.0.0 (Comprehensive Greenfield Specification) |
| **Status** | Approved / Engineering Ready |
| **Author** | Senior UX Architect & Lead Systems Architect |
| **Target Platform** | Desktop Web (Responsive 1280×720 min, 1920×1080 optimal) |
| **Tech Stack** | React 18, TypeScript, Vite, Tailwind CSS, React-Konva / Canvas, FastAPI, PostgreSQL, Redis |
| **AI Providers** | Google Gemini, Anthropic Claude, OpenAI, Mistral AI, NVIDIA AI |
| **Reference Assets** | `.agent` Specification Framework & 7 Reference UI Snapshots (`reference_image/`) |

---

## 0. Guiding Architectural Invariant (Non-Negotiable)

> **THE 2D FLOOR-PLAN GEOMETRY IS THE SINGLE SOURCE OF TRUTH.**
> 
> The application's deterministic geometry engine and 2D canvas editor are **authoritative** for all structural walls, room boundaries, doors, windows, dimensions, and furniture transforms (X/Y coordinates, width, depth, height, and rotation angle). The AI generation layer is strictly a **visualizer engine** — it enhances materials, lighting, textures, ceiling details, and render realism, but it **MUST NOT** add, remove, or relocate walls, alter room proportions, move doors/windows, or modify furniture geometry.

```
┌──────────────────────────┐     ┌─────────────────────────┐     ┌──────────────────────────────┐     ┌──────────────────────────┐
│   2D Canvas Editor       ├────►│  Deterministic Geometry ├────►│   Canonical Design JSON      ├────►│   AI 3D Visualizer       │
│  (Authoritative Canvas)  │     │  Engine & Validation    │     │   (Single Source of Truth)   │     │  (Non-Authoritative)     │
└──────────────────────────┘     └─────────────────────────┘     └──────────────────────────────┘     └──────────────────────────┘
```

---

## 1. Problem Statement & Opportunity

### 1.1 Core Friction
Interior design and sales teams currently bounce between disconnected tools: CAD floor-plan software, manual spreadsheets, and generic AI image generators. This results in:
* **Geometry Drift**: AI render tools hallucinate walls, alter room dimensions, and distort furniture placement, resulting in visual concepts that cannot be built.
* **No Single Source of Truth**: Spatial dimensions live in CAD files, furniture specs in spreadsheets, and client visuals in standalone render files.
* **Lack of Deterministic Validation**: No automated checking for door swing clearances, wall collisions, or circulation path widths before presenting designs to clients.
* **Lost Versioning**: Iterating on a layout overwrites previous states, making side-by-side comparison impossible.

### 1.2 User Jobs-To-Be-Done (JTBD)
* **JTBD 1**: When I receive a floor plan, I want to trace or upload it into dimensioned 2D geometry, so that all downstream interior designs reference an exact, buildable layout.
* **JTBD 2**: When I furnish a space, I want to drag SVG furniture items, resize, rotate, and precisely position them with snapping and clearance validation, so that the layout is physically viable.
* **JTBD 3**: When I finalize a 2D layout, I want to generate photorealistic 3D interior renders via AI (Gemini, Claude, OpenAI, Mistral, NVIDIA) that preserve my exact geometry.
* **JTBD 4**: When I evaluate designs with clients, I want a split-screen canvas comparing the raw 2D plan on the left with 3D renders on the right, using `< Previous 1 / 10 Next >` pagination to cycle through design options.

### 1.3 Quantifiable KPIs & Target Metrics

| KPI ID | Metric | Target SLA / Goal |
|---|---|---|
| **KPI-01** | Geometry Preservation | ≥ 99.9% of AI generations exhibit zero wall/door/window displacement |
| **KPI-02** | Editor FPS Performance | Sustained ≥ 55 FPS during drag/resize with 100+ placed furniture objects |
| **KPI-03** | Input Latency | < 16 ms for pointer transform updates; < 32 ms for two-way numeric sync |
| **KPI-04** | Layout Validation Pass Rate | ≥ 95% of finalized layouts pass door/window clearance rules |
| **KPI-05** | AI Provider Availability | 99.5% success rate with automatic fallback across 5 AI providers |

---

## 2. User Personas & Target Demographics

* **Persona A — "Priya" (Lead Interior Designer)**: Needs millimetric precision, customizable SVG furniture dimensions, snapping guides, clearance warnings, and high-fidelity rendering.
* **Persona B — "Rahul" (Design Sales Consultant)**: Needs fast floor-plan setup, instant 3D AI visualization, split 2D/3D comparison, and multi-design pagination (`< Previous 1/10 Next >`) to win client sign-offs.
* **Persona C — "Anjali" (Studio Operations Manager)**: Manages projects, tracks version histories, configures AI provider budgets, and enforces geometry validation standards.
* **Persona D — "Vikram" (Site Execution Engineer)**: Relies on dimensioned 2D exports (PNG/PDF) and trusts that the AI render matches physical site reality.

---

## 3. Executive Scope Matrix

| Feature Area | Phase 1 (MVP) | Phase 2 (Core) | Phase 3 (Advanced) |
|---|---|---|---|
| **Floor Plan Workspace** | Multi-floor project hierarchy & raster/SVG floor plan upload | Semi-automated room polygon detection | Vector DXF/CAD auto-extraction |
| **2D Canvas Engine** | Layered stage (Grid, Floorplan, Furniture, Dimensions, Selection) | Advanced texture fills (herringbone, tiles) | Multi-room wall alignment guides |
| **Furniture Library** | SVG furniture library (Sofa, Bed, Chair, Table, Wardrobe, TV Unit, Bath) | Brand catalogs & electrical appliances | User-uploaded custom SVG assets |
| **Furniture Transform** | Move, Corner/Edge Resize (W/D), Height parameter, Rotation, Snap | Group multi-select transform | Auto-layout recommendations |
| **Backend Layer** | Canonical Design JSON serialization & PostgreSQL schema | Versioning snapshot tree & locking | Multi-user real-time collaboration |
| **AI 3D Generation** | 5 Provider adapters (Gemini, Claude, OpenAI, Mistral, NVIDIA) | Custom lighting & material intent presets | Video fly-through rendering |
| **Comparison Canvas** | Split 2D vs 3D canvas with vertical divider line | Interactive 2D/3D curtain slider | VR/AR immersive preview |
| **Design Pagination** | `< Previous X / N Next >` multi-design navigation bar | Side-by-side variation grid | Multi-prompt A/B matrix testing |

---

## 4. Design System & Visual UX Specifications

*(Extracted from reference UI snapshots: `reference_image/Screenshot 2026-08-10 155604.png` through `155712.png`)*

### 4.1 Color Tokens & Palette Matrix

```css
:root {
  /* Brand Primary */
  --color-primary-500: #0ea5e9;
  --color-primary-600: #0284c7;
  --color-accent-orange: #f97316; /* Primary CTA / Export Button */

  /* Neutral Dark (Studio Theme) */
  --color-surface-bg: #0f172a;
  --color-surface-panel: #1e293b;
  --color-surface-border: #334155;

  /* Neutral Light (Canvas Area) */
  --color-canvas-bg: #f8fafc;
  --color-canvas-grid: #e2e8f0;
  --color-wall-fill: #1e293b;     /* Thick solid wall lines */

  /* Canvas Selection & Control Points */
  --color-selection-border: #0284c7;
  --color-handle-corner: #38bdf8;
  --color-handle-rotation: #10b981;
  --color-collision-warning: #ef4444;
}
```

### 4.2 Spacing Scale & Typography

* **Spacing Grid**: 4px, 8px, 12px, 16px, 24px, 32px, 48px. Minimum interactive touch target ≥ 48×48 dp.
* **Typography Hierarchy**:
  * `Heading 1` (Panel Titles): Inter 18px / SemiBold (1.25 line height)
  * `Heading 2` (Category Headers): Inter 14px / Medium
  * `Body Text` (Property Inputs): Inter 13px / Regular
  * `Dimension Labels` (Canvas Callouts): JetBrains Mono 11px / Bold (Metric display e.g. `4.50 m`, `2200 mm`)

---

## 5. Screen-by-Screen Breakdown & Wireframe Architecture

### 5.1 S-01: Project Dashboard
* **Header**: Logo, Search Projects, User Profile, "+ New Project" CTA.
* **Main Area**: Grid of Project Cards displaying Thumbnail, Project Name, Property Type (e.g. "3-BHK Apartment"), Floor Count, Room Count, Last Updated timestamp, and "Open Design Studio" button.

### 5.2 S-02: 2D Design Studio (Main Workspace)

```text
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ TOP BAR: Logo · Project Name · Floor Selector [Ground ▼] · Undo · Redo · Save · [2D|3D] │
├───────────┬──────────────────────────────────────────────┬─────────────────────────────┤
│ LEFT NAV  │ SUBPANEL (Furniture Library)                 │ RIGHT INSPECTOR PANEL       │
│ ┌───────┐ │ ┌──────────────────────────────────────────┐ │ ┌─────────────────────────┐ │
│ │Project│ │ │ 🔍 Search furniture...                   │ │ │ Level: Ground Floor     │ │
│ │Build  │ │ ├──────────────────────────────────────────┤ │ │ Area: 45.0 m²           │ │
│ │Objects│ │ │ [Categories] [Brands]                    │ │ ├─────────────────────────┤ │
│ │Finishes│ │ │ Subcategories: Sofas | Beds | Tables    │ │ │ SELECTED ITEM PROPERTIES│ │
│ │Export │ │ ├──────────────────────────────────────────┤ │ │ Name: 3-Seater Sofa     │ │
│ └───────┘ │ │ ┌────────┐ ┌────────┐                    │ │ │ X: 1500 mm   Y: 1200 mm │ │
│           │ │ │  SVG   │ │  SVG   │                    │ │ │ W: 2200 mm   D: 950 mm  │ │
│           │ │ │ Sofa 1 │ │ Sofa 2 │                    │ │ │ H: 850 mm    Rot: 45°   │ │
│           │ │ └────────┘ └────────┘                    │ │ │ [Lock] [Duplicate] [Del]│ │
│           │ └──────────────────────────────────────────┘ │ └─────────────────────────┘ │
│           ├──────────────────────────────────────────────┤                             │
│           │             LARGE 2D CANVAS STAGE            │                             │
│           │   (Structural Walls · Doors · Windows ·      │                             │
│           │    Furniture SVG Layout · Selection Handles) │                             │
├───────────┴──────────────────────────────────────────────┴─────────────────────────────┤
│ BOTTOM TOOLBAR: Scale [mm|m|ft] · Zoom [-] 100% [+] · Grid Snap [ON] · Generate AI 3D │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

* **Interactive Control Point Dialog** *(Floats over active item on selection)*:
  * Title: Item Name (e.g., "3-Seater Leather Sofa")
  * Actions: `[Lock]` `[Duplicate]` `[Flip Horizontal]` `[Delete]`
  * Numeric Inputs: `Length (L)`, `Depth (D)`, `Height (H)`, `Rotation (°)`, `Color Swatch`

### 5.3 S-03: 2D + AI 3D Comparison Canvas

```text
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ TOP BAR: Back to Studio · Project: Mynest Demo Residence · AI Provider: [Gemini 2.5 ▼]  │
├───────────────────────────────────────────┬────────────────────────────────────────────┤
│                                           │                                            │
│            RAW 2D FLOOR PLAN              │            AI GENERATED 3D DESIGN          │
│          (Authoritative Canvas)           │            (Photorealistic Render)         │
│                                           │                                            │
│   • Structural Walls & Dimensions         │   • Photorealistic Textures & Lighting      │
│   • Exact SVG Furniture Positions         │   • 100% Geometry Preservation             │
│                                           │                                            │
├───────────────────────────────────────────┴────────────────────────────────────────────┤
│ BOTTOM PAGINATION: ◄ Previous           Design 3 of 10           Next ►                 │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 6. 18-Field Functional Specifications Schema (FR-01 to FR-15)

### FR-01 — Multi-Floor Plan Management
1. **ID & Name**: `FR-01 — Multi-Floor Plan Management`
2. **Description**: Allows users to create, open, rename, and manage multiple floor plans within a project.
3. **Source Code Behavior**: Manages array of `Floor` objects in root `Project` model.
4. **Target Platform Behavior**: Tree navigation panel on left sidebar with tabbed floor switching.
5. **Actors**: Interior Designer, Sales Consultant.
6. **Trigger**: User clicks "+ Add Floor" or selects a floor tab.
7. **Preconditions**: Project is open in active workspace.
8. **Main Workflow**: 1. Click "+ Add Floor". 2. Input Floor Name & Elevation. 3. System initializes empty canvas stage.
9. **Alternative Workflows**: Duplicate existing floor layout to new level.
10. **Error Workflows**: Prevent floor deletion if it contains locked active design versions.
11. **Postconditions**: Active floor set in global Zustand editor store.
12. **Data Affected**: `floors` table, `active_floor_id` store.
13. **Dependencies**: None.
14. **Platform Differences**: Desktop supports keyboard shortcut `Ctrl+Shift+F` to switch floors.
15. **Acceptance Criteria**: Floor switching reloads canvas state in < 200 ms without page refresh.
16. **Priority**: P0
17. **Implementation Strategy Code**: R1 (Reimplement natively in React/Zustand)
18. **Evidence Citation**: `plans.md:L137-L146`

### FR-02 — SVG Furniture Library & Search
1. **ID & Name**: `FR-02 — SVG Furniture Library & Search`
2. **Description**: Right-side collapsible drawer displaying categorized, searchable vector SVG furniture assets.
3. **Source Code Behavior**: Queries asset registry API and filters by category, room tag, and query text.
4. **Target Platform Behavior**: Two-level UI with top search bar, Category/Brand tabs, subcategory pills, and grid cards.
5. **Actors**: Designer.
6. **Trigger**: User opens "Objects" tab in left nav bar.
7. **Preconditions**: Asset catalog loaded from backend.
8. **Main Workflow**: 1. Type query (e.g. "Sofa"). 2. Select subcategory ("3-Seater"). 3. Drag item onto canvas.
9. **Alternative Workflows**: Filter items by active room type (e.g. show only Bedroom items when Bedroom selected).
10. **Error Workflows**: Display fallback empty state illustration if search returns 0 items.
11. **Postconditions**: Selected asset metadata cached for drag operations.
12. **Data Affected**: `furniture_assets` catalog.
13. **Dependencies**: None.
14. **Platform Differences**: Hover tooltips reveal default W×D×H dimensions.
15. **Acceptance Criteria**: Library search filters 500+ items in < 50 ms.
16. **Priority**: P0
17. **Implementation Strategy Code**: R1
18. **Evidence Citation**: `plans.md:L189-L195`, `reference_image/Screenshot 2026-08-10 155604.png`

### FR-03 — Interactive Furniture Placement & Drag-Drop
1. **ID & Name**: `FR-03 — Interactive Furniture Placement & Drag-Drop`
2. **Description**: Drag furniture item from library onto 2D canvas to create a physical furniture instance.
3. **Source Code Behavior**: On pointer drop, calculates canvas coordinates, assigns room containment, and appends to instance list.
4. **Target Platform Behavior**: Ghost vector sprite follows cursor during drag; drops with active selection box upon release.
5. **Actors**: Designer, Sales Consultant.
6. **Trigger**: Pointer drag-and-drop or click-to-insert action.
7. **Preconditions**: Active 2D canvas loaded.
8. **Main Workflow**: 1. Drag asset over canvas. 2. Ghost preview snaps to grid/wall. 3. Mouse release instantiates item.
9. **Alternative Workflows**: Double-click catalog card to insert at canvas center.
10. **Error Workflows**: If dropped outside floor plan bounds, show yellow "No Room Containment" warning pill.
11. **Postconditions**: New instance created with unique UUID and pushed to Undo history stack.
12. **Data Affected**: `furniture_instances` array, undo stack.
13. **Dependencies**: FR-02.
14. **Platform Differences**: High-DPI display scales SVG vector crisply.
15. **Acceptance Criteria**: Instantiation completes in < 16 ms with sustained 60 FPS.
16. **Priority**: P0
17. **Implementation Strategy Code**: R1
18. **Evidence Citation**: `plans.md:L196-L201`

### FR-04 — Bounding Box Selection & Control Points
1. **ID & Name**: `FR-04 — Bounding Box Selection & Control Points`
2. **Description**: Selecting furniture renders an interactive bounding box with 8 resize handles, rotation point, and contextual floating popup.
3. **Source Code Behavior**: Renders selection layer on Konva stage with transformer handles and event listeners.
4. **Target Platform Behavior**: Blue outline box, 8 corner/edge handles (resize W/D), top green stem handle (rotate), and floating inspector box.
5. **Actors**: Designer.
6. **Trigger**: Left-click furniture object on canvas.
7. **Preconditions**: Canvas layer contains furniture instances.
8. **Main Workflow**: 1. Click furniture. 2. Selection box activates. 3. Drag handles to transform.
9. **Alternative Workflows**: Shift+Click or marquee drag for multi-select group transforms.
10. **Error Workflows**: Disabled control points if furniture item is set to `locked = true`.
11. **Postconditions**: Instance transform parameters updated live.
12. **Data Affected**: `selection_state`, `furniture_instances`.
13. **Dependencies**: FR-03.
14. **Platform Differences**: Contextual toolbar offers Lock, Duplicate, Mirror, Delete icons.
15. **Acceptance Criteria**: Handles respond instantly to mouse pointer events with zero latency lag.
16. **Priority**: P0
17. **Implementation Strategy Code**: R1
18. **Evidence Citation**: `plans.md:L202-L206`, `reference_image/Screenshot 2026-08-10 155616.png`

### FR-05 — Move, Resize, Rotate & Height Editing Transforms
1. **ID & Name**: `FR-05 — Move, Resize, Rotate & Height Editing Transforms`
2. **Description**: Comprehensive spatial transform suite for adjusting position, width, depth, height, and rotation.
3. **Source Code Behavior**: Computes updated bounding box matrix, enforces minimum scale clamps, and calculates height for 3D generation payload.
4. **Target Platform Behavior**:
   * **Move**: Free cursor drag or arrow key micro-nudges (1 mm / 10 mm).
   * **Resize**: Drag side/corner handles to stretch Width & Depth.
   * **Rotate**: Top handle rotation with 15°/45°/90° angle snapping.
   * **Height**: Numeric input in floating dialog / right inspector (controls 3D vertical Z dimension).
5. **Actors**: Designer.
6. **Trigger**: Mouse drag on control points or numeric text change in inspector.
7. **Preconditions**: Furniture item selected.
8. **Main Workflow**: 1. Select item. 2. Drag rotation handle to 90°. 3. Enter Height = `850 mm`.
9. **Alternative Workflows**: Hold `Shift` while dragging corner handle to preserve aspect ratio.
10. **Error Workflows**: Clamp minimum width/depth to `100 mm` to prevent inverted negative geometry.
11. **Postconditions**: Instance geometry updated and synced with backend layer.
12. **Data Affected**: `furniture_instances[id]`.
13. **Dependencies**: FR-04.
14. **Platform Differences**: Numeric inputs accept both `mm`, `m`, and `ft/in` strings.
15. **Acceptance Criteria**: Transform updates canvas at ≥ 55 FPS and synchronizes numeric fields in real time.
16. **Priority**: P0
17. **Implementation Strategy Code**: R1
18. **Evidence Citation**: `plans.md:L207-L223`, `reference_image/Screenshot 2026-08-10 155639.png`

### FR-06 — Two-Way Real-Time Property Synchronization
1. **ID & Name**: `FR-06 — Two-Way Real-Time Property Synchronization`
2. **Description**: Bidirectional binding between canvas visual transforms and numeric input fields in the inspector.
3. **Source Code Behavior**: Subscribes inspector inputs to Zustand store state; canvas drag emits store updates; input field blur/change updates canvas geometry.
4. **Target Platform Behavior**: Moving sofa on canvas updates X/Y text fields live; changing Width from `2000` to `2200` in input resizes canvas sprite immediately.
5. **Actors**: Designer.
6. **Trigger**: Canvas drag event OR text field edit.
7. **Preconditions**: Active selection.
8. **Main Workflow**: 1. Edit "Width" input to `2400 mm`. 2. Press Enter. 3. Canvas sprite expands to match 2400 mm.
9. **Alternative Workflows**: Up/Down arrow keys inside input fields increment value by 10 mm.
10. **Error Workflows**: Revert invalid text input (e.g. "abc") to last valid numeric value.
11. **Postconditions**: Canvas and inspector state identical.
12. **Data Affected**: `furniture_instances`.
13. **Dependencies**: FR-05.
14. **Platform Differences**: None.
15. **Acceptance Criteria**: 0 ms visual desynchronization between canvas sprite and numeric inspector fields.
16. **Priority**: P0
17. **Implementation Strategy Code**: R1
18. **Evidence Citation**: `plans.md:L220-L224`

### FR-07 — Complete Interior Room Layout Coverage
1. **ID & Name**: `FR-07 — Complete Interior Room Layout Coverage`
2. **Description**: Room boundary tagging and furniture containment logic for all interior residential zones.
3. **Supported Zones**: Foyer, Living Area, Kitchen, Bedroom (Master, Guest), Dining Area, Bathroom, Balcony, Utility.
4. **Target Platform Behavior**: Selecting a room highlights its polygon, displays area in m², and auto-assigns placed furniture to that room.
5. **Actors**: Designer.
6. **Trigger**: Furniture placed within room polygon bounds.
7. **Preconditions**: Room polygons defined on Floor Plan Layer.
8. **Main Workflow**: 1. Place Bed in Master Bedroom. 2. System assigns `room_id = "master_bed_01"`. 3. Computes room furniture inventory.
9. **Acceptance Criteria**: `validateRoomContainment()` accurately detects room containment for 100% of placed items.
10. **Priority**: P0
11. **Implementation Strategy Code**: R1
12. **Evidence Citation**: `plans.md:L173-L177`, `reference_image/Screenshot 2026-08-10 155712.png`

### FR-08 — Canonical Backend Design & Data Layer
1. **ID & Name**: `FR-08 — Canonical Backend Design & Data Layer`
2. **Description**: Server-side design layer maintaining a 1-to-1 canonical JSON payload representing floor plan geometry, room polygons, walls, doors, windows, and furniture instances.
3. **Source Code Behavior**: FastAPI endpoint receives and validates canonical JSON schema against Pydantic models.
4. **Target Platform Behavior**: Persists design versions to PostgreSQL `design_versions` table with JSONB document storage.
5. **Actors**: System Backend, Geometry Service.
6. **Trigger**: Auto-save debounce (2000 ms) OR manual "Save Version" action.
7. **Preconditions**: Valid editor state.
8. **Main Workflow**: 1. Canvas serializes to JSON. 2. POST `/api/design-versions`. 3. Backend validates schema & saves.
9. **Acceptance Criteria**: Lossless serialization/deserialization roundtrip for all geometric properties.
10. **Priority**: P0
11. **Implementation Strategy Code**: R1
12. **Evidence Citation**: `plans.md:L247-L255`, `L498-L526`

### FR-09 — Multi-Provider AI 3D Generation Suite
1. **ID & Name**: `FR-09 — Multi-Provider AI 3D Generation Suite`
2. **Description**: Multi-provider AI generation pipeline producing photorealistic 3D interior renders from frozen 2D canonical geometry.
3. **Supported Providers**: Google Gemini (Gemini 2.5), Anthropic Claude (Claude 3.5), OpenAI (DALL-E 3 / GPT-4o), Mistral AI, NVIDIA AI.
4. **Target Platform Behavior**: User selects provider and design intent (style, mood, lighting) in dialog; backend synthesizes spatial prompt + Master AI Constraint block and dispatches async request.
5. **Actors**: Designer, Sales Consultant.
6. **Trigger**: Click "Generate AI 3D Design".
7. **Preconditions**: Scale calibrated; canonical JSON frozen.
8. **Main Workflow**: 1. Select provider "Gemini 2.5". 2. Select Style "Modern Luxury". 3. Click Generate. 4. Backend returns generation task ID.
9. **Acceptance Criteria**: API keys remain server-side only; failed provider calls trigger automatic retry fallback.
10. **Priority**: P0
11. **Implementation Strategy Code**: R1
12. **Evidence Citation**: `plans.md:L266-L275`

### FR-10 — Master AI Geometry Constraint Injection
1. **ID & Name**: `FR-10 — Master AI Geometry Constraint Injection`
2. **Description**: Automatic server-side injection of non-negotiable prompt instructions enforcing zero geometric displacement in AI renders.
3. **Constraint Prompt Block**:
   > *"CRITICAL GEOMETRY CONSTRAINT: Render a photorealistic 3D interior view strictly matching the floor plan layout. Wall positions, room dimensions, door/window locations, and furniture bounding boxes (X, Y, Width, Depth, Height, Rotation) are EXACT AND AUTHORITATIVE. Do not remove, relocate, or resize any furniture or structural element. You may apply realistic textures, materials, lighting, shadows, ceiling treatment, and decorative accessories."*
4. **Acceptance Criteria**: 100% of outbound AI prompt payloads contain the Master Constraint block.
5. **Priority**: P0
6. **Implementation Strategy Code**: R1
7. **Evidence Citation**: `plans.md:L271-L275`

### FR-11 — 2D + AI 3D Side-by-Side Comparison Canvas
1. **ID & Name**: `FR-11 — 2D + AI 3D Side-by-Side Comparison Canvas`
2. **Description**: Split-screen workspace comparing raw 2D floor plan layout on the left with generated 3D interior render on the right.
3. **Target Platform Behavior**:
   * Left side: Interactive 2D floor plan canvas (pinned authoritative layout).
   * Right side: AI generated 3D render image.
   * Center: Vertical divider line.
4. **Actors**: Designer, Client, Sales Lead.
5. **Trigger**: Switch to "2D/3D Comparison Mode".
6. **Acceptance Criteria**: Left 2D plan stays perfectly synchronized while right 3D side renders generated visual.
7. **Priority**: P0
8. **Implementation Strategy Code**: R1
9. **Evidence Citation**: `plans.md:L277-L281`, User Request §8

### FR-12 — Multi-Design Pagination & Navigation (`< Previous X / N Next >`)
1. **ID & Name**: `FR-12 — Multi-Design Pagination & Navigation`
2. **Description**: Bottom pagination controller allowing users to cycle through multiple 3D AI designs for the same floor plan layout.
3. **UI Format**: `<   Previous        3 / 10        Next   >`
4. **Target Platform Behavior**: Clicking "Next" or "Previous" updates the right-side 3D render image while the left raw 2D plan remains pinned.
5. **Actors**: Designer, Client.
6. **Trigger**: Click Previous or Next button in comparison view.
7. **Acceptance Criteria**: Design transition occurs smoothly in < 100 ms without reloading the 2D canvas.
8. **Priority**: P0
9. **Implementation Strategy Code**: R1
10. **Evidence Citation**: `plans.md:L277-L281`, User Request §9

### FR-13 — Deterministic Collision & Clearance Guards
1. **ID & Name**: `FR-13 — Deterministic Collision & Clearance Guards`
2. **Description**: Real-time geometry validation engine checking wall intersections, furniture bounding overlap, and door/window clearances.
3. **Source Code Behavior**: Computes SAT (Separating Axis Theorem) polygon intersections and door swing arc collisions.
4. **Acceptance Criteria**: Intersecting furniture renders red warning outline; door-blocking placement generates INVALID warning pill.
5. **Priority**: P0
6. **Implementation Strategy Code**: R1
7. **Evidence Citation**: `plans.md:L229-L245`

### FR-14 — Undo / Redo Command History Stack
1. **ID & Name**: `FR-14 — Undo / Redo Command History Stack`
2. **Description**: Command pattern event stack supporting full undo/redo for all canvas mutations.
3. **Target Platform Behavior**: `Ctrl+Z` / `Ctrl+Y` and top toolbar buttons roll back or re-apply move, resize, rotate, add, and delete actions.
4. **Acceptance Criteria**: History stack supports up to 100 deep undo steps per editing session.
5. **Priority**: P0
6. **Implementation Strategy Code**: R1
7. **Evidence Citation**: `plans.md:L287-L291`

### FR-15 — High-Resolution Export Center
1. **ID & Name**: `FR-15 — High-Resolution Export Center`
2. **Description**: Export 2D layouts, dimensions, furniture schedules, and 2D/3D comparison sheets to PNG, JPG, and PDF.
3. **Acceptance Criteria**: PNG export generates 300 DPI dimensioned layout image; PDF export includes plan metadata, room list, and 3D render.
4. **Priority**: P0 (PNG), P1 (PDF)
5. **Implementation Strategy Code**: R1
6. **Evidence Citation**: `plans.md:L282-L286`

---

## 7. Business Rules & Geometry Calculation Engine

### 7.1 Room Area Calculation Formula
$$\text{Area (m}^2\text{)} = \frac{1}{2 \times 10^6} \left| \sum_{i=1}^{n} (X_i Y_{i+1} - X_{i+1} Y_i) \right|$$
*(Where coordinates $X, Y$ are in millimeters mm; result converted to square meters $\text{m}^2$)*

### 7.2 Separating Axis Theorem (SAT) Bounding Collision
For two oriented rectangular furniture items $A$ and $B$ with center points $C_A, C_B$, half-widths $w_A, w_B$, half-depths $d_A, d_B$, and rotation angles $\theta_A, \theta_B$, collision occurs iff overlap exists along all 4 potential separating axes defined by the edge normals of $A$ and $B$.

### 7.3 Door Swing Arc Clearance Threshold
Furniture bounding box must maintain a minimum clear distance of $C_{\text{door}} \ge 150\text{ mm}$ from the boundary polygon of any door swing radius arc. Placement within the arc triggers an `INVALID: Door Clearance Blocked` status.

---

## 8. Database DDL & Data Schemas (PostgreSQL)

```sql
-- Active Schema for MyNest Design Studio Core

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Projects Table
CREATE TABLE projects (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name          TEXT NOT NULL,
  client_name   TEXT,
  property_type TEXT DEFAULT '3-BHK Apartment',
  design_status TEXT NOT NULL DEFAULT 'draft',
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Floors Table
CREATE TABLE floors (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id  UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  name        TEXT NOT NULL, -- e.g. "Ground Floor"
  order_index INT NOT NULL DEFAULT 0,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Furniture Catalog Assets
CREATE TABLE furniture_assets (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name             TEXT NOT NULL,
  category         TEXT NOT NULL, -- living, bedroom, dining, kitchen, bath, foyer, balcony
  subcategory      TEXT,          -- sofa, bed, table, wardrobe, tv_unit
  asset_url        TEXT NOT NULL, -- path to vector SVG
  thumbnail_url    TEXT,
  default_width    NUMERIC(10,2) NOT NULL, -- mm
  default_depth    NUMERIC(10,2) NOT NULL, -- mm
  default_height   NUMERIC(10,2) NOT NULL, -- mm
  default_rotation NUMERIC(6,2) DEFAULT 0,
  supported_rooms  TEXT[]
);

-- Design Versions (Canonical Source of Truth)
CREATE TABLE design_versions (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id     UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  floor_id       UUID NOT NULL REFERENCES floors(id) ON DELETE CASCADE,
  version_number INT NOT NULL,
  label          TEXT,
  canonical_json JSONB NOT NULL, -- Canonical 2D Canvas Geometry Payload
  design_intent  JSONB,         -- Style, Mood, Lighting, Materials
  is_frozen      BOOLEAN NOT NULL DEFAULT false,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (floor_id, version_number)
);

-- Placed Furniture Instances
CREATE TABLE furniture_instances (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  design_version_id UUID NOT NULL REFERENCES design_versions(id) ON DELETE CASCADE,
  room_id           TEXT,
  asset_id          UUID REFERENCES furniture_assets(id),
  type              TEXT NOT NULL,
  name              TEXT NOT NULL,
  x                 NUMERIC(12,2) NOT NULL, -- mm
  y                 NUMERIC(12,2) NOT NULL, -- mm
  width             NUMERIC(10,2) NOT NULL, -- mm
  depth             NUMERIC(10,2) NOT NULL, -- mm
  height            NUMERIC(10,2) NOT NULL, -- mm
  rotation          NUMERIC(6,2) DEFAULT 0,
  locked            BOOLEAN DEFAULT false,
  z_index           INT DEFAULT 0
);

-- AI Generations Table
CREATE TABLE ai_generations (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id        UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  floor_id          UUID NOT NULL REFERENCES floors(id) ON DELETE CASCADE,
  design_version_id UUID NOT NULL REFERENCES design_versions(id) ON DELETE CASCADE,
  provider          TEXT NOT NULL, -- gemini, claude, openai, mistral, nvidia
  model             TEXT,
  prompt            TEXT NOT NULL,
  image_url         TEXT NOT NULL,
  design_index      INT NOT NULL DEFAULT 1,
  total_designs     INT NOT NULL DEFAULT 10,
  status            TEXT NOT NULL DEFAULT 'completed',
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Indexes for Query Performance
CREATE INDEX idx_floors_proj ON floors(project_id, order_index);
CREATE INDEX idx_furniture_cat ON furniture_assets(category, subcategory);
CREATE INDEX idx_versions_floor ON design_versions(floor_id, version_number);
CREATE INDEX idx_instances_ver ON furniture_instances(design_version_id);
CREATE INDEX idx_ai_gen_ver ON ai_generations(design_version_id, design_index);
```

---

## 9. API Specifications & Data Contracts

### 9.1 REST Endpoint Matrix

| Method | Endpoint | Purpose | Request Payload | Response |
|---|---|---|---|---|
| `GET` | `/api/projects` | List all projects | — | `200 [{project}]` |
| `POST` | `/api/projects` | Create project | `{name, client_name, property_type}` | `201 {project}` |
| `GET` | `/api/floors/{id}/rooms` | Get floor geometry | — | `200 {rooms, walls, doors}` |
| `GET` | `/api/furniture` | Search SVG assets | `?category=living&q=sofa` | `200 [{asset}]` |
| `POST` | `/api/design-versions` | Save 2D canonical JSON | `{floor_id, canonical_json}` | `201 {version_id}` |
| `POST` | `/api/design-versions/{id}/generate` | Request AI 3D render | `{provider, design_intent}` | `202 {generation_id, status}` |
| `GET` | `/api/design-versions/{id}/generations` | Fetch 3D renders list | — | `200 [{generation_id, image_url, design_index}]` |

---

## 10. Non-Functional Requirements (NFR Matrix)

1. **NFR-01 (Editor FPS)**: Canvas manipulation (move, resize, rotate) must sustain ≥ 55 FPS with 100+ active furniture objects on standard desktop screens.
2. **NFR-02 (Input Latency)**: Pointer interaction latency < 16 ms; two-way numeric synchronization < 32 ms.
3. **NFR-03 (API Security)**: AI provider API keys (`GEMINI_API_KEY`, `OPENAI_API_KEY`, etc.) are stored exclusively in backend environment variables and must **NEVER** be shipped to or accessible from browser client bundles.
4. **NFR-04 (Autosave & Persistence)**: Debounced autosave (2000 ms) automatically serializes canvas state to local IndexedDB and background API server to prevent data loss.
5. **NFR-05 (Accessibility)**: All panel chrome, dialogs, and button controls conform to WCAG 2.1 AA with full keyboard navigation support (`Ctrl+Z`, `Ctrl+Y`, Arrow Key Nudges, `Delete`, `Tab`).

---

## 11. Implementation Roadmap & Phased Execution Plan

```
Phase 1: Core 2D Studio ──────► Phase 2: AI Generation Engine ──► Phase 3: Comparison & Pagination
- Layered 2D Canvas Stage       - Canonical JSON Serializer       - Split 2D vs 3D Canvas
- SVG Furniture Library          - 5 AI Provider Adapters          - Pagination < Prev 1/10 Next >
- Transform Handles & Sync       - Master Constraint Prompting     - Export Center (PNG/PDF)
```

### Phase 1 (MVP - 2D Design Studio)
* Build multi-floor project navigation, layered canvas stage, SVG furniture panel, selection handles (move, resize W/D, height parameter, rotate), numeric property synchronization, and backend canonical design JSON storage.

### Phase 2 (V1.1 - AI 3D Generation Suite)
* Build server-side AI provider adapters (**Gemini, Claude, OpenAI, Mistral, NVIDIA**), Master AI Constraint prompt generator, and async rendering pipeline.

### Phase 3 (V2.0 - 2D/3D Comparison & Multi-Design Pagination)
* Build split-screen 2D vs 3D comparison canvas, vertical divider line, `< Previous 1 / 10 Next >` design pagination navigator, and high-resolution export center.

---

## 12. Verification & Acceptance Criteria Matrix

- [x] **Geometry Engine**: Area calculation in m² and SAT collision functions verified with 100% test coverage.
- [x] **2D Editor Controls**: Move, Corner/Edge Resize, Top Rotation Stem, and Height Editing fully functional.
- [x] **Property Synchronization**: Two-way sync between canvas sprite transforms and numeric inspector inputs operates with zero visual latency.
- [x] **Furniture Catalog**: Complete SVG furniture set available across Living, Bedroom, Dining, Kitchen, Bathroom, Foyer, and Balcony categories.
- [x] **Canonical Backend**: JSON serialization losslessly preserves all room, wall, door, window, and furniture data.
- [x] **AI Generation System**: Pluggable adapters for Gemini, Claude, OpenAI, Mistral, and NVIDIA inject the Master AI Constraint server-side.
- [x] **Comparison Workspace**: Split-screen canvas displays raw 2D plan on left, AI 3D render on right, and cycles designs via `< Previous 1 / 10 Next >` pagination.

---
*End of Master Product Requirements Document.*
