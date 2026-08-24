MYNEST DESIGN STUDIO

PRODUCT REQUIREMENTS DOCUMENT

1\. Product Overview

MYNEST DESIGN STUDIO is a desktop-first interior design application enabling users to create accurate 2D interior layouts from floor plans, place and edit furniture, maintain a synchronized backend design representation, and generate AI-based 3D interior visualizations.

2\. Product Vision

To empower interior designers and homeowners with a precise, intuitive tool that bridges 2D floor planning and realistic 3D visualization, streamlining the design workflow from concept to presentation.

3\. Goals

\- Provide accurate 2D floor-plan editing with preserved geometry.

\- Offer a rich, searchable furniture library with SVG assets.

\- Enable real-time furniture manipulation (move, resize, rotate).

\- Synchronize frontend changes with a backend design data layer.

\- Generate multiple AI-driven 3D visualizations from structured design data.

\- Support multiple floor plans per project.

\- Deliver a clean, professional desktop UI inspired by industry-standard tools.

4\. Users

Primary: Interior designers, architects, home renovators.

Secondary: Real estate agents, DIY homeowners, design students.

&#x20;5. User Workflow

&#x20;6. Open Project (or create new).

&#x20;7. Open one or multiple floor plans.

&#x20;8. View selected floor plan on canvas.

&#x20;9. Browse/search furniture library.

10\. Drag-and-drop furniture onto canvas.

11\. Adjust furniture (position, size, rotation) using selection controls.

12\. Complete room-wise layout (living area, kitchen, bedroom, etc.).

13\. Save design (local/project file).

14\. Backend design layer updates automatically.

15\. Trigger AI 3D generation with current design data.

16\. View 2D floor plan alongside generated 3D result.

17\. Browse multiple AI generations via previous/next controls.

18\. Export or iterate as needed.

6\. Product Architecture

\- Frontend: React.js + TypeScript, modular components.

\- Backend: Python + FastAPI, RESTful API.

\- Data Synchronization: Frontend state changes propagated via API to backend; backend returns canonical design state.

\- AI Generation: Provider-agnostic abstraction layer; accepts structured design JSON, returns image/model URL.

\- Storage: Local file system for projects; optional cloud sync.

7\. Application Navigation

\- Global Header: App name, project selector, save/status indicators, user menu.

\- Main Toolbar (below header): Undo/redo, zoom controls, 2D/3D toggle, AI generate button.

\- Left Panel (Navigation/Tools): Floor plan list, layer visibility, measurement tools, grid/snap settings.

\- Central Canvas: Interactive 2D floor plan with walls, doors, windows, furniture.

\- Right Panel (Furniture/Object Panel): Search bar, category tabs, furniture thumbnails, property editor for selected item.

\- Bottom Status Bar (optional): Coordinates, unit display, tool hints.

8\. Floor Plan Management

\- Upload floor plans (image or PDF) per floor.

\- Support multiple floor plans per project (e.g., ground floor, second floor).

\- List floor plans in left navigation with thumbnails and names.

\- Click to set active floor plan; canvas updates accordingly.

\- Rename, delete, reorder floor plans.

\- Active floor plan highlighted; others dimmed or shown in background if multi-view supported.

\- Canvas displays only active floor plan geometry; furniture confined to that plan.

&#x20;9. Design Studio (Main Workspace)

Layout as described in section 7, with canvas as primary interaction area. Panels are collapsible. Toolbar provides context-sensitive actions (e.g., furniture-specific controls when item selected).

10\. 2D Canvas

\- Renders vector-based floor plan geometry (walls, rooms, doors, windows) with accurate scaling.

\- Displays furniture as SVG or raster icons with selection bounding box.

\- Supports pan (drag empty area), zoom (mouse wheel or pinch), zoom-to-fit.

\- Grid and snap-to-grid options.

\- Dimension lines show wall lengths and furniture spacing on hover or via toggle.

\- Selection box shows resize handles (corners/sides) and rotation handle.

\- Context menu on furniture for duplicate, delete, properties, bring-forward/send-backward.

11\. Furniture Library

\- Categorized as: Sofa, Bed, Chair, Table, Dining Table, Wardrobe, TV Unit, Cabinet, Kitchen Furniture, Bathroom Furniture, Lighting, Decor, Other.

\- Each category tab shows scrollable thumbnail grid.

\- Search bar filters by name, tags, dimensions.

\- Preview pane shows larger view and metadata (size, material options).

\- Furniture represented by SVG assets for scalability; fallback to PNG.

\- Metadata includes: type, default width/depth/height, rotatable flag, collision bounds.

\- Dragging a thumbnail initiates placement; dropping onto canvas creates furniture instance at drop point (snapped to floor).

12\. Furniture Manipulation

\- Selected furniture shows bounding box with:

\- Corner/side handles for width/depth resizing (maintain aspect ratio unless alt key held).

\- Circular handle for rotation (angle display).

\- Center drag for translation.

\- Precise input via properties panel (X,Y,Z coordinates, width, height, rotation).

\- Delete via Delete key or toolbar button.

\- Duplicate via Ctrl+D or context menu.

\- Copy/paste supported.

\- Furniture cannot be placed outside floorplan boundary or inside walls (collision detection).

\- Align/distribute guides appear when moving near other furniture or walls.

13\. Room-wise Design

\- Canvas visually indicates rooms via wall loops or color shading.

\- Furniture snap-to-wall and snap-to-floor alignment.

\- Room type can be tagged via properties panel (living, kitchen, etc.) for reporting.

\- Users can create custom rooms by drawing partitions (optional advanced feature).

\- Furniture list grouped by room in properties panel or separate outline view.

14\. Backend Design Layer

\- Data model mirrors canvas state:

\- Project { id, name, floors\[] }

\- Floor { id, name, width, height, scale, walls\[], doors\[], windows\[], furnitureInstances\[] }

\- Wall { id, startPoint, endPoint, thickness }

\- Door/Window { id, boundingBox, swingDirection }

\- FurnitureInstance { id, typeRef, position (x,y), width, height, rotation, roomId }

\- Frontend sends updates via REST endpoints (PUT /furniture/:id) on transform.

\- Backend validates and returns normalized state.

\- Changes are transactional; undo/redo maintained frontend but persisted via API.

15\. Data Model

Entities as above; additional:

\- FurnitureType { id, name, category, svgUrl, defaultDimensions }

\- DesignVersion { id, floorId, timestamp, serializedDesign }

\- AIGeneration { id, designVersionId, provider, prompt, resultUrl, status, createdAt }

Relationships: Floor has many Walls/Doors/Windows/FurnitureInstances; FurnitureInstance belongsTo FurnitureType; AIGeneration belongsTo DesignVersion.

16\. API Requirements

\- GET /projects/:id – retrieve project with floors.

\- POST /projects – create new project.

\- PUT /projects/:id – update project metadata.

\- GET /floors/:id – get floor geometry.

\- POST /furniture – place new furniture.

\- PUT /furniture/:id – update transform/properties.

\- DELETE /furniture/:id – remove item.

\- POST /designs/:floorId/generate – trigger AI generation (sends structured design JSON).

\- GET /generations/:id – get generation result.

\- GET /generations?designVersionId=:id – list generations for a design.

\- WebSocket optional for real‑time sync.

17\. AI Provider Architecture

\- Abstract service: AIGeneratorInterface with method generate(designData, providerConfig).

\- Provider implementations: OpenAIGenerator, GeminiGenerator, etc., each conforming to interface.

\- Factory selects provider based on user setting or environment variable.

\- Request payload includes: floor plan SVG, room labels, furniture list with types, positions, dimensions, optional style prompt.

\- Response: URL to hosted image or GLTF model, plus metadata (seed, variant).

\- Error handling: fallback to other provider, retry logic, user‑visible error toast.

18\. AI 3D Generation

\- User clicks "Generate 3D" after completing layout.

\- System serializes current floor plan design to JSON.

\- Request sent to backend AI service endpoint.

\- Backend forwards to selected provider; stores result URL.

\- Upon completion, notification appears; 3D workspace auto‑loads result.

\- Generation supports multiple variants (user can request N variations).

19\. 2D + 3D Comparison Workspace

\- Split view: left pane raw floor plan (2D), right pane AI‑generated 3D image/model.

\- Divider draggable to adjust ratio.

\- Left pane identical to main canvas but locked to view‑only (no editing).

\- Right pane shows 3D render with lighting, materials, camera angle based on room layout.

\- Controls: rotate 3D model, zoom, change lighting preset, toggle wireframe.

\- Sync option: moving camera in 3D view does not affect 2D; but selecting a furniture piece in 2D highlights similar object in 3D (if model supports object IDs).

20\. Multiple AI Generations

\- Each generation saved as variant under same design version.

\- Bottom carousel or header shows: "< Prev  1 / X  Next >".

\- Clicking Prev/Next updates right‑pane 3D view; left 2D remains unchanged.

\- Users can rename, delete, or set favorite generation.

\- Export options: download image, share link, send to client.

21\. UI/UX Requirements

\- Desktop‑first layout with resizable panels.

\- Consistent design system: spacing 8px grid, primary color #4F46E5 (indigo), neutral grays.

\- Font: Inter or similar sans‑serif.

\- Icons: stroke‑style, 24px.

\- Furniture icons: solid fill, single‑color for library; colored when selected.

\- Selection box: dashed blue line, blue handles.

\- Hover states: subtle elevation, outline.

\- Loading skeletons for library and generation.

\- Tooltips for all tools and icons.

\- Keyboard shortcuts: Del (delete), Ctrl+D (duplicate), Ctrl+Z/Y (undo/redo), Space (pan), +/- (zoom), R (rotate mode), ESC (clear selection).

22\. Reference Image Analysis

Examined reference images for common patterns: top‑app bar, side toolbar, left‑nav panel, central canvas, right‑side properties panel, furniture thumbnail grid, zoom controls, 2D/3D split view, previous/next generation controls. Inspired MYNEST DESIGN STUDIO’s layout while ensuring original branding and visual identity.

23\. .agent Requirements

Reviewed .agent folder containing generic PRD generation prompts (codebase reverse‑engineering, screencast video flow, problem statement/greenfield, PRD amendment). These prompts guided the structure and rigor of this PRD but did not dictate specific product features; they were used as methodological references only.

24\. Functional Requirements

\- FR-PJ-01: Create, open, save projects.

\- FR-FP-01: Upload, list, select, rename, delete floor plans.

\- FR-CV-01: Pan, zoom, zoom‑to‑fit floor‑plan canvas.

\- FR-FL-01: Display furniture library with search, categories, thumbnails.

\- FR-FL-02: Drag furniture thumbnail onto canvas to instantiate.

\- FR-FM-01: Select furniture and show bounding box with resize/rotation handles.

\- FR-FM-02: Move selected furniture via drag or numeric input.

\- FR-FM-03: Resize width/height via handles or numeric fields.

\- FR-FM-04: Rotate furniture via handle or numeric angle.

\- FR-FM-05: Delete selected furniture via key/button.

\- FR-FM-06: Duplicate selected furniture.

\- FR-FM-07: Prevent placement inside walls or outside floor boundary.

\- FR-RD-01: Tag furniture with room type; filter/filter by room.

\- FR-BE-01: Backend API receives and stores frontend design changes.

\- FR-BE-02: Frontend subscribes to backend for canonical state (optimistic UI).

\- FR-AI-01: Trigger AI 3D generation with current design data.

\- FR-AI-02: Display generated 3D result in split view.

\- FR-AI-03: Browse multiple generations via previous/next controls.

\- FR-UI-01: Resizable, collapsible panels with persistent state.

\- FR-UI-02: Keyboard shortcuts for core actions.

\- FR-UI-03: Tooltips and status messages.

\- FR-EX-01: Export design as JSON or image.

\- FR-EX-02: Export favorite 3D rendering.

25\. Non-functional Requirements

\- NFR-PF-01: Canvas shall maintain 60 FPS during manipulation with up to 200 furniture items.

\- NFR-PF-02: Load time for a project with 5 floor plans and 500 furniture items < 3 seconds.

\- NFR-SC-01: Support unlimited floors per project; performance degrades gracefully.

\- NFR-RL-01: Data synchronization eventual consistency; conflicts resolved by last‑write‑win with timestamp.

\- NFR-SEC-01: All API communication over HTTPS; no storage of API keys in client.

\- NFR-MT-01: Code modularized by feature (project, floor, canvas, furniture, AI) for maintainability.

\- NFR-US-01: WCAG 2.1 AA compliance for keyboard navigation, focus outlines, contrast ratios.

\- NFR-ER-01: Graceful degradation if AI service unavailable; user can still edit 2D and retry later.

26\. Error Handling

\- Validation errors (e.g., invalid dimensions) show inline toast.

\- Network failures display retry banner with exponential backoff.

\- AI service errors show specific message (quota exceeded, invalid prompt) with option to change provider.

\- Undo/redo stack cleared on major structural changes (new floor plan) with warning.

\- Invalid floor‑plan upload reports unsupported format or corrupt file.

27\. Security

\- Sanitize all user‑generated text (furniture names, notes) to prevent XSS.

\- Restrict file uploads to safe MIME types (image/png, image/jpeg, application/pdf).

\- Store API keys environment‑side only; client never sees them.

\- Implement rate‑limiting on AI generation endpoints per user.

28\. Performance

\- Use requestIdleBackground for non‑critical UI updates.

\- Virtualize furniture library list for large catalogs.

\- Memoize SVG rendering of furniture types.

\- Debounce resize/move events while dragging; update on release.

\- Cache AI generation results to avoid duplicate calls.

29\. Implementation Phases

Phase 1 – Project Shell + Navigation

\- Set up React + TS project structure.

\- Implement header, toolbar, left nav, right panel placeholders.

\- Basic routing between project list and editor.

Phase 2 – Project + Floor Plan Management

\- Upload floor plan images, store as blobs or base64.

\- List floor plans with thumbnails.

\- Active floor plan state.

Phase 3 – Floor Plan Viewer + 2D Canvas

\- Render walls/doors/windows from SVG path data.

\- Implement pan, zoom, zoom‑to‑fit.

\- Grid and snap toggles.

Phase 4 – Furniture Library + SVG Assets

\- Build library UI with search, category tabs.

\- Load SVG furniture thumbnails.

\- Drag‑start from thumbnail.

Phase 5 – Furniture Drag/Drop + Transformations

\- Drop handler creates furniture instance at cursor.

\- Selection box with handles.

\- Move, resize, rotate via mouse.

\- Numeric properties panel.

Phase 6 – Room‑wise Furniture Layout

\- Detect rooms via wall loops (simple rectilinear assumption).

\- Allow tagging furniture with room.

\- Show room outline or label.

Phase 7 – Backend Design Synchronization

\- Set up FastAPI server with project/floor/furniture models.

\- CRUD endpoints for furniture.

\- Frontend sends updates on transform complete; optimistic UI.

Phase 8 – AI Provider Abstraction

\- Define AIGenerator interface.

\- Implement stub provider returning placeholder image.

\- Backend endpoint to trigger generation.

Phase 9 – AI 3D Generation (Stub → Real)

\- Integrate with a chosen provider (e.g., OpenAI DALL·E) for image generation.

\- Send structured design JSON; receive image URL.

\- Display in 3D workspace.

Phase 10 – 2D + 3D Comparison Workspace

\- Build split‑view layout.

\- Left pane: read‑only canvas.

\- Right pane: image viewer with zoom/rotate.

\- Divider interaction.

Phase 11 – Multiple AI Generations + Previous/Next

\- Store generation metadata.

\- Carousel controls to switch variants.

\- Ability to rename/delete generations.

Phase 12 – Testing + Optimization + Production Readiness

\- Unit tests for core logic (transform calculations, collision).

\- E2E tests for key workflows (place furniture, generate 3D).

\- Performance profiling, bundle optimization.

\- Documentation, release scripts.

30\. Testing Strategy

\- Jest + React Testing Library for component unit tests.

\- Cypress for end‑to‑end user workflows.

\- Mock API endpoints (MSW) for frontend‑backend contract testing.

\- Property‑based testing for geometry functions (e.g., point‑in‑polygon).

\- Visual regression tests for canvas rendering.

\- Load testing for AI generation concurrency.

31\. Acceptance Criteria

\- User can create a project, add two floor plans, place furniture on each, and switch between plans without data loss.

\- Furniture placement respects walls; attempting to place inside wall shows error and prevents drop.

\- Changing furniture dimensions via numeric fields updates canvas instantly and syncs to backend.

\- After completing a layout, clicking “Generate 3D” yields a 3D rendering within 10 seconds (depending on provider).

\- The 2D/3D split view shows the unchanged floor plan on left and the generated image on right.

\- User can browse at least three generated variants using Prev/Next controls.

\- Undo/redo works for all furniture manipulations across sessions (if project saved).

\- Application launches and becomes interactive within 3 seconds on a mid‑tier desktop.

\- All toolbar buttons have accessible labels and keyboard shortcuts.

\- No console errors in production build during typical usage.

32\. Future Enhancements

\- Real‑time collaboration via WebSocket CRDTs.

\- Advanced room detection (non‑rectilinear) and automatic furniture arrangement suggestions.

\- Material editor (apply textures/colors to furniture).

\- Lighting simulation for 3D views (time of day, artificial lights).

\- VR/AR export for immersive walkthrough.

\- Integration with measurement laser tools via Bluetooth.

\- Cloud storage with version history.

\- Plugin architecture for custom furniture providers or AI services.

