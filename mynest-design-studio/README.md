# MyNest Design Studio

> **Authoritative Architectural Geometry & Deterministic AI Interior Visualization Platform**  
> *Floor plan geometry is the single source of truth. AI is strictly a non-authoritative visualizer.*

---

## Table of Contents

1. [Executive Summary & Business Context](#1-executive-summary--business-context)
   - [Vision & Value Proposition](#vision--value-proposition)
   - [The Core Business Problem & Industry Pain Points](#the-core-business-problem--industry-pain-points)
   - [How MyNest Design Studio Solves These Problems](#how-mynest-design-studio-solves-these-problems)
   - [Cardinal Rule: Invariant #1 (Geometry Authority)](#cardinal-rule-invariant-1-geometry-authority)
   - [Implementation Status Matrix](#implementation-status-matrix)
2. [High-Level Architecture & Technical Foundation](#2-high-level-architecture--technical-foundation)
   - [System Topology & Data Flow](#system-topology--data-flow)
   - [Technology Stack Inventory](#technology-stack-inventory)
   - [Repository Directory Structure](#repository-directory-structure)
   - [Database Schema & Data Models](#database-schema--data-models)
3. [Screen-by-Screen UI & Component Reference](#3-screen-by-screen-ui--component-reference)
   - [Global Layout & Navigation (AppShell, Sidebar, Header)](#31-global-layout--navigation)
   - [Screen 1: Project Dashboard (`/dashboard`)](#32-screen-1-project-dashboard-dashboard)
   - [Screen 2: Floor Plans Repository (`/floor-plans` & Detail)](#33-screen-2-floor-plans-repository-floor-plans)
   - [Screen 3: Design Studio & 2D Canvas (`/design-studio`)](#34-screen-3-design-studio--2d-canvas-design-studio)
   - [Screen 4: Deterministic 3D Scene Viewer (`Scene3DModal`)](#35-screen-4-deterministic-3d-scene-viewer-scene3dmodal)
   - [Screen 5: AI Render Gallery & Comparison (`GenerationGallery`)](#36-screen-5-ai-render-gallery--comparison-generationgallery)
   - [Screen 6: Projects Overview (`/projects`), History (`/ai-generations`), Settings (`/settings`)](#37-auxiliary-screens)
4. [End-to-End User Journeys & Workflows](#4-end-to-end-user-journeys--workflows)
   - [Workflow A: Project Creation & Onboarding](#workflow-a-project-creation--onboarding)
   - [Workflow B: Floor Plan Upload & Vector Geometry Extraction](#workflow-b-floor-plan-upload--vector-geometry-extraction)
   - [Workflow C: 2D Spatial Furniture Arrangement & Versioning](#workflow-c-2d-spatial-furniture-arrangement--versioning)
   - [Workflow D: Full House 3D Assembly & Geometry Inspection](#workflow-d-full-house-3d-assembly--geometry-inspection)
   - [Workflow E: Two-Pass Deterministic AI Visualization Pipeline](#workflow-e-two-pass-deterministic-ai-visualization-pipeline)
5. [Input, Processing & Output Technical Specifications](#5-input-processing--output-technical-specifications)
   - [1. File Ingestion & Parsing](#1-file-ingestion--parsing)
   - [2. Architectural Extraction & Room Topology](#2-architectural-extraction--room-topology)
   - [3. Layout Persistence & Version Snapshots](#3-layout-persistence--version-snapshots)
   - [4. Deterministic 3D Base Capture](#4-deterministic-3d-base-capture)
   - [5. AI Diffusion Rendering (ControlNet Depth + Canny)](#5-ai-diffusion-rendering-controlnet-depth--canny)
   - [6. Post-AI Geometry Validation Gates](#6-post-ai-geometry-validation-gates)
6. [First-Time User Step-by-Step Practical Guide](#6-first-time-user-step-by-step-practical-guide)
   - [Step 1: Accessing the Studio](#step-1-accessing-the-studio)
   - [Step 2: Creating Your Client Project](#step-2-creating-your-client-project)
   - [Step 3: Uploading a Floor Plan (Top-Right Action)](#step-3-uploading-a-floor-plan-top-right-action)
   - [Step 4: Arranging Furniture on the 2D Plan](#step-4-arranging-furniture-on-the-2d-plan)
   - [Step 5: Verifying Real 3D Walls and Proportions](#step-5-verifying-real-3d-walls-and-proportions)
   - [Step 6: Executing AI Photorealistic Visualization](#step-6-executing-ai-photorealistic-visualization)
   - [Step 7: Side-by-Side Verification & Export](#step-7-side-by-side-verification--export)
7. [API & Service Endpoint Reference](#7-api--service-endpoint-reference)
8. [Error Handling, Validation Gates & Troubleshooting](#8-error-handling-validation-gates--troubleshooting)
   - [Pre-Flight and Base Render Gates](#pre-flight-and-base-render-gates)
   - [Post-AI Validation Gate Codes](#post-ai-validation-gate-codes)
   - [Troubleshooting Common Issues](#troubleshooting-common-issues)
9. [Developer Setup & Local Execution Guide](#9-developer-setup--local-execution-guide)
   - [Prerequisites](#prerequisites)
   - [Backend Environment Setup](#backend-environment-setup)
   - [Frontend Environment Setup](#frontend-environment-setup)
   - [Running the Services Locally](#running-the-services-locally)
   - [Testing, Type-Checking & Quality Gates](#testing-type-checking--quality-gates)
10. [Architecture Principles & Maintenance Guide](#10-architecture-principles--maintenance-guide)
11. [📘 Deep Dive: Core Pipeline Technical Specification (`CORE_PIPELINE_DOCUMENTATION.md`)](CORE_PIPELINE_DOCUMENTATION.md)

---

## 1. Executive Summary & Business Context

### Vision & Value Proposition
**MyNest Design Studio** is an enterprise-grade interior architectural design workspace that bridges the gap between precision CAD/vector floor plans and cutting-edge generative AI visualization. 

In conventional interior design workflows, architectural drafting, 3D modelling, and rendering are siloed:
1. Floor plans are drafted in CAD or vector formats.
2. 3D modelers spend hours or days manually extruding walls, placing 3D assets, and assigning materials.
3. Designers who attempt to use modern Generative AI (e.g., Midjourney, Stable Diffusion, DALL-E) find that **AI hallucinations destroy architectural integrity**—walls shift, windows vanish, doors relocate, room proportions morph, and furniture pieces multiply or change into impossible physical forms.

**MyNest Design Studio eliminates this trade-off.** It enables interior designers, architects, and real estate developers to upload architectural plans, deterministically lay out real furniture items at true-to-life millimetre scales, inspect the design in a true-to-geometry interactive 3D WebGL environment, and trigger photorealistic AI visualizers that are **strictly geometry-locked**.

```
┌─────────────────┐      ┌─────────────────────────┐      ┌──────────────────────────┐
│   Floor Plan    │ ───► │ Deterministic Geometry  │ ───► │  Canonical Design JSON   │
│ (PDF / Image)   │      │ Engine (OpenCV / PyMu)  │      │  (Single Source of Truth)│
└─────────────────┘      └─────────────────────────┘      └─────────────┬────────────┘
                                                                        │
┌─────────────────────────┐      ┌─────────────────────────┐            │
│ AI Photoreal Visualizer │ ◄─── │ Deterministic 3D Base   │ ◄──────────┘
│ (Non-Authoritative)     │      │ Three.js / WebGL Capture│      
└─────────────────────────┘      └─────────────────────────┘
```

#### Core Design Philosophy at a Glance

```mermaid
pie title Architecture Responsibility Split
    "Deterministic Geometry (Walls, Dimensions, Furniture)" : 60
    "Photorealistic AI Styling (Finishes, Light, Textures)" : 30
    "Automated Quality Gates & Auditing" : 10
```

#### Rendering Performance & Pipeline Speed (Seconds)

```mermaid
flowchart LR
    A["📄 PDF Parse<br/>0.8s"]
    B["✏️ 2D Canvas Edit<br/>0.2s"]
    C["🏗️ 3D Scene Build<br/>0.4s"]
    D["📸 Offscreen Base PNG<br/>0.6s"]
    E["🎨 AI Pass A (Depth)<br/>9.2s"]
    F["✨ AI Pass B (Canny)<br/>7.5s"]
    G["🛡️ Gate Checks<br/>0.3s"]

    A --> B --> C --> D --> E --> F --> G

    style A fill:#f1f5f9,stroke:#64748b,stroke-width:1px
    style B fill:#f1f5f9,stroke:#64748b,stroke-width:1px
    style C fill:#f1f5f9,stroke:#64748b,stroke-width:1px
    style D fill:#fef3c7,stroke:#d97706,stroke-width:2px
    style E fill:#dbeafe,stroke:#2563eb,stroke-width:2px
    style F fill:#dbeafe,stroke:#2563eb,stroke-width:2px
    style G fill:#dcfce7,stroke:#16a34a,stroke-width:2px
```


---

### The Core Business Problem & Industry Pain Points

| Industry Challenge | What Happens in Conventional / AI Tools | How MyNest Design Studio Solves It |
| :--- | :--- | :--- |
| **Hallucinated Geometry** | Standard AI generative models imagine walls, doors, and windows arbitrarily. Rooms look stunning but are unbuildable. | **Geometry is authoritative.** Floor plan walls, openings, and boundaries are extracted deterministically. The AI model is constrained via multi-pass ControlNet conditioning (Depth + Canny). |
| **Furniture Inventory Drift** | Generic AI renders hallucinate random sofas, tables, or chandeliers not selected by the client, causing client disputes during procurement. | Furniture is placed by the user using a catalog with verified mm dimensions. The inventory is frozen into an immutable `canonical_json` snapshot before rendering. |
| **Slow 3D Turnaround Time** | Traditional photorealistic 3D rendering (3ds Max, V-Ray, Corona) takes 2 to 5 days per room by specialized 3D visualizers. | Real-time WebGL 3D preview is generated instantly from the floor plan; photorealistic multi-room AI renders complete in seconds. |
| **Lost Design History** | Client revisions overwrite CAD drafts, leading to confusion over which layout version was approved. | Append-only **Design Versioning** with automated cryptographic fingerprinting ensures zero layout loss and historical reversibility. |

---

### Cardinal Rule: Invariant #1 (Geometry Authority)

> [!IMPORTANT]
> **RULE #1 — GEOMETRY IS AUTHORITATIVE, NEVER ALTER IT (DO NOT BREAK)**  
> The 2D floor plan is the **single source of truth**. The following elements are fixed and **must never be moved, rescaled, added, or removed** by any code, prompt, AI model, or feature:
> 1. **Walls** — positions, lengths, thickness, angles.
> 2. **Windows & Doors** — positions, sizes, opening orientations.
> 3. **Room Proportions** — exact boundary shapes and dimensions.
> 4. **User-Placed Furniture** — exact $X, Y$, rotation, scale, and item identities recorded in `canonical_json`.
>
> *AI is a visualizer only (styling materials, finishes, lighting, textures, and atmosphere). AI is NEVER authoritative for geometry.*

---

### Implementation Status Matrix

| Subsystem / Feature | Status | Verification & Code Location |
| :--- | :--- | :--- |
| **Project & Floor Management** | ✅ Implemented | `backend/app/api/projects.py`, `frontend/src/pages/Dashboard.tsx` |
| **Floor Plan Ingestion (PDF / Images)** | ✅ Implemented | Streaming upload with mime/size checks: `storage/file_storage.py`, `UploadModal.tsx` |
| **Vector Wall & Opening Extraction** | ✅ Implemented | PyMuPDF vector line parsing + raster fallback: `geometry_extraction_service.py` |
| **Authoritative 2D Design Canvas** | ✅ Implemented | Konva stage with pan, zoom, snap, rotate, delete: `DesignCanvas.tsx` |
| **Real-Scale Furniture Library** | ✅ Implemented | Categorized catalog with mm dimensions: `frontend/src/data/furniture.ts` |
| **Immutable Design Versioning** | ✅ Implemented | Deduplicating append-only snapshots: `backend/app/db/models.py:DesignVersion` |
| **Full House Deterministic 3D** | ✅ Implemented | Three.js / React Three Fiber scene extrusion: `Scene3DModal.tsx`, `RoomScene3D.tsx` |
| **Offscreen 3D Base Render Capture** | ✅ Implemented | Headless WebGL capture batch (`1216x832`): `BaseRenderBatch.tsx` |
| **Multi-Provider AI Render Engine** | ✅ Implemented | fal.ai Flux (Depth + Canny two-pass) & NVIDIA NIM Flux: `app/services/ai/` |
| **Multi-Section Gallery & Split-View** | ✅ Implemented | Side-by-side plan/render inspector: `GenerationGallery.tsx` |
| **Invoice / BOQ Extraction & Ingestion**| ⚠️ Partial / Backend Ready | SQLAlchemy models + parser in `invoices.py`; UI pages pending integration |
| **Direct CAD (.dwg/.dxf) Importer** | 📋 Planned | Currently supports Vector PDF, PNG, JPG, WEBP |
| **Cloud S3 Object Storage Adapter** | 📋 Planned | Local disk storage implemented with clean abstraction in `file_storage.py` |

---

## 2. High-Level Architecture & Technical Foundation

### System Topology & Data Flow

```mermaid
graph TD
    User([User / Designer]) -->|Browser HTTP / WebSocket| FE[React + Vite Frontend]
    
    subgraph Frontend [Client Layer :5173]
        FE --> UI_Dash[Dashboard & Projects]
        FE --> UI_Canvas[2D Konva Canvas]
        FE --> UI_3D[Three.js 3D WebGL Scene]
        FE --> UI_Batch[BaseRenderBatch Offscreen Capturer]
        FE --> UI_Gallery[AI Generation Gallery]
    end
    
    FE -->|Proxy /api/*| BE[FastAPI Backend :8001]
    
    subgraph Backend [Server Layer]
        BE --> API_FP[Floor Plan API]
        BE --> API_GEN[Generation API]
        BE --> SVC_GEO[Geometry Extraction Service]
        BE --> SVC_SCENE[Scene Service & 3D Assembly]
        BE --> SVC_VAL[Validation & Geometry Gates]
        BE --> SVC_AI[AI Service Adapters]
    end
    
    subgraph Persistence [Data & Storage Layer]
        BE --> DB[(Supabase / PostgreSQL)]
        BE --> FS[(Local Storage Engine /storage)]
    end
    
    subgraph External_AI [Generative AI Providers]
        SVC_AI -->|fal.run / flux-lora-depth| FAL[fal.ai Flux Gateway]
        SVC_AI -->|integrate.api.nvidia.com| NVD[NVIDIA NIM AI]
    end
```

---

### Technology Stack Inventory

| Component | Technology | Version / Tool | Purpose |
| :--- | :--- | :--- | :--- |
| **Frontend Framework** | React + TypeScript | React 18.3, Vite 5.4 | High-performance SPA with client-side HMR |
| **2D Geometry Canvas** | Konva / react-konva | Konva 9.3, react-konva 18.2 | Canvas rendering for floor plans, furniture placement, and transforms |
| **3D Graphics Engine** | Three.js / React Three Fiber | Three 0.169, R3F 8.18, Drei 9.122 | Extrusion of walls, floors, ceilings, and 3D furniture models |
| **PDF Rasterization** | PDF.js | pdfjs-dist 4.7 | Browser-side vector plan rasterization |
| **Client State Management**| Zustand | Zustand 5.0 | Lightweight isolated stores (Editor, Viewport, UI state) |
| **Backend Framework** | Python + FastAPI | Python 3.11, FastAPI 0.115 | High-throughput async REST API |
| **Relational Database** | PostgreSQL / Supabase | SQLAlchemy 2.0 (Sync engine) | Relational persistence with JSONB document containment |
| **Vector & CV Processing** | PyMuPDF (fitz), OpenCV, Pillow | OpenCV 4.x, PyMuPDF 1.24 | Vector PDF extraction, line detection, opening classification |
| **Deep Learning** | Ultralytics YOLOv8 | YOLOv8n (Embedded) | Object detection for furniture and floor plan symbol verification |
| **AI Rendering Adapters** | fal.ai / NVIDIA Cloud Functions | Flux.1 [dev], ControlNet Depth/Canny | Deterministic img2img and ControlNet conditioning |
| **Code Quality Gates** | Ruff, Mypy, Pytest, ESLint | Ruff (3.11), Mypy (Strict), Pytest | 470+ passing automated backend unit and integration tests |

---

### Repository Directory Structure

```
mynest-design-studio/
├── CLAUDE.md                     # Agent guardrails & Cardinal Rule #1
├── README.md                     # Complete project & business documentation
├── CORE_PIPELINE_DOCUMENTATION.md # Comprehensive 16-stage pipeline & AI integration guide
├── AI_RENDER_FIX_REPORT.md       # Technical post-mortem on 2-pass ControlNet
├── PIPELINE_AUDIT_REPORT.md      # Detailed 13-stage end-to-end pipeline audit
├── backend/
│   ├── app/
│   │   ├── main.py               # FastAPI entry point, lifespan, CORS, health
│   │   ├── api/                  # Versioned API route endpoints
│   │   │   ├── floor_plans.py    # Upload, layout, scene, generate, control-image
│   │   │   ├── generations.py    # Generation status & image retrieval
│   │   │   ├── projects.py       # CRUD for projects and floors
│   │   │   └── invoices.py       # Invoice & BOQ extraction endpoints
│   │   ├── core/config.py        # Settings, paths, AI credentials, limits
│   │   ├── db/
│   │   │   ├── base.py           # DB engine, session factory, init_db()
│   │   │   └── models.py         # SQLAlchemy ORM models (Project, Version, etc.)
│   │   ├── schemas/              # Pydantic request & response contracts
│   │   ├── services/             # Core business & algorithmic logic
│   │   │   ├── architectural_service.py      # Wall graphs, door/window detection
│   │   │   ├── floor_plan_service.py         # Plan lifecycle, layout serialization
│   │   │   ├── geometry_extraction_service.py# Vector PDF parsing, OpenCV lines
│   │   │   ├── scene_service.py              # Authoritative 2D→3D spatial assembly
│   │   │   ├── generation_service.py         # AI generation orchestration & gates
│   │   │   ├── prompt_service.py             # Room-specific prompt synthesis
│   │   │   ├── validation_service.py         # Geometry fidelity validation gates
│   │   │   └── ai/                           # AI provider adapters
│   │   │       ├── fal_flux_adapter.py       # fal.ai Flux Depth + Canny adapter
│   │   │       └── nvidia_flux_adapter.py    # NVIDIA NIM Flux.1 adapter
│   │   └── storage/file_storage.py           # Filesystem storage manager
│   ├── tests/                    # 470+ Pytest automated validation test suites
│   ├── requirements.txt          # Python runtime dependencies
│   └── pyproject.toml            # Ruff and Mypy strict configuration
├── frontend/
│   ├── src/
│   │   ├── App.tsx               # Route mapping & AppShell wrapper
│   │   ├── main.tsx              # React DOM entry point
│   │   ├── pages/                # Primary application screens
│   │   │   ├── Dashboard.tsx     # Client project management screen
│   │   │   ├── FloorPlans.tsx    # Floor plan repository & upload center
│   │   │   ├── FloorPlanDetail.tsx# Single floor plan metadata & inspection
│   │   │   ├── DesignStudio.tsx  # Interactive 2D canvas & AI orchestration
│   │   │   ├── AIGenerations.tsx # Past rendering history & exports
│   │   │   └── Settings.tsx      # System preferences & provider configuration
│   │   ├── components/           # Modular UI components
│   │   │   ├── design-studio/    # Design Canvas, 3D Modal, BaseRenderBatch
│   │   │   ├── floor-plans/      # Upload Modal, Floor Plan Card & Toolbar
│   │   │   ├── layout/           # AppShell, Sidebar, Header
│   │   │   ├── projects/         # Create Project Modal
│   │   │   └── ui/               # Reusable Button, Card, Modal, EmptyState
│   │   ├── data/furniture.ts     # Curated millimetre-scale furniture catalog
│   │   ├── lib/                  # API client services & coordinate math
│   │   ├── store/                # Zustand client state stores
│   │   └── types/                # TypeScript shared domain contracts
│   ├── package.json              # Frontend scripts and dependencies
│   └── vite.config.ts            # Vite bundler configuration & backend proxy
```

---

### Database Schema & Data Models

The persistence layer uses PostgreSQL via SQLAlchemy 2.0 ORM. All layout edits are captured in the append-only `design_versions` table as a canonical JSON document.

```mermaid
erDiagram
    PROJECT ||--o{ FLOOR : contains
    PROJECT ||--o{ FLOOR_PLAN : has
    FLOOR ||--o{ FLOOR_PLAN : contains
    FLOOR_PLAN ||--o{ DESIGN_VERSION : tracks
    DESIGN_VERSION ||--o{ AI_GENERATION : generates
    AI_GENERATION ||--o{ AI_GENERATION_IMAGE : produces

    PROJECT {
        uuid id PK
        string name
        string client_name
        string property_type
        string design_status
    }
    FLOOR {
        uuid id PK
        uuid project_id FK
        string name
        int order_index
    }
    FLOOR_PLAN {
        uuid id PK
        uuid project_id FK
        uuid floor_id FK
        string original_filename
        string file_type
        int file_size
        numeric scale_mm_per_px
    }
    DESIGN_VERSION {
        uuid id PK
        uuid floor_plan_id FK
        int version_number
        jsonb canonical_json
        jsonb design_intent
        boolean is_frozen
    }
    AI_GENERATION {
        uuid id PK
        uuid design_version_id FK
        string provider
        string model
        string prompt
        string status
    }
    AI_GENERATION_IMAGE {
        uuid id PK
        uuid generation_id FK
        string image_url
        string label
        int design_index
    }
```

#### Core Database Tables
1. **`projects`**: High-level interior design engagements linked to clients and properties.
2. **`floors`**: Logical floor divisions within a project (e.g., "Ground Floor", "Level 1", "Penthouse").
3. **`floor_plans`**: Stored binary files (PDF, PNG, JPG) with resolution and extraction status.
4. **`design_versions`**: **Single Source of Truth.** Contains `canonical_json` capturing exact furniture placement coordinates, rotation, and dimensions.
5. **`ai_generations`**: Audit records of generation requests, provider choices, seeds, and execution statuses (`pending`, `completed`, `failed`).
6. **`ai_generation_images`**: High-resolution photorealistic output renders linked to specific room keys.

---

## 3. Screen-by-Screen UI & Component Reference

### 3.1 Global Layout & Navigation
The application uses a persistent two-column enterprise shell defined in `frontend/src/components/layout/AppShell.tsx`:

* **Left Navigation Sidebar (`Sidebar.tsx`)**:
  * **Brand Mark & Header**: Displays the MyNest Logo (`M`) and title `MYNEST Design Studio`.
  * **Navigation Links**:
    * **Dashboard** (`/dashboard`): Project management and client workspaces.
    * **Design Studio** (`/design-studio`): Active 2D floor plan layout editor, 3D visualizer, and AI generation console.
  * **User Profile Card**: Shows user avatar `MT` and current role ("MyNest Team · Interior Design").
* **Top Header Bar (`Header.tsx`)**:
  * **Left Side**: Dynamic active breadcrumb section title and system subtitle.
  * **Right Side**: Notifications icon (`Bell`), user profile indicator, and server health status.

---

### 3.2 Screen 1: Project Dashboard (`/dashboard`)
* **URL Route**: `/dashboard` (default redirect from `/`)
* **Component File**: `frontend/src/pages/Dashboard.tsx`
* **Purpose**: Serves as the primary operational hub where interior designers manage multi-room projects and access project-specific designs.

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│ Dashboard                                                 🔔 Notifications  [MT] │
├──────────────────────────────────────────────────────────────────────────────────┤
│ Projects                                                     [ + New Project ]   │
│                                                                                  │
│ ┌─────────────────────────┐  ┌─────────────────────────┐                         │
│ │ 📁 Luxury Villa - Palm  │  │ 📁 Penthouse Downtown   │                         │
│ │ Property: Residential   │  │ Property: Duplex        │                         │
│ │ Client: Mr. Al-Mansoor  │  │ Client: Sarah Jenkins   │                         │
│ │ 3 floors                │  │ 2 floors                │                         │
│ │ [ Open Design ]   [🗑️]  │  │ [ Open Design ]   [🗑️]  │                         │
│ └─────────────────────────┘  └─────────────────────────┘                         │
└──────────────────────────────────────────────────────────────────────────────────┘
```

#### Detailed Component & Interaction Reference
* **Top Action Bar**:
  * **"New Project" Button**: Located at the top right of the section. Clicking opens `CreateProjectModal`.
* **Project Grid (`project-grid`)**:
  * Displays projects in responsive cards. Each card showcases:
    * **Folder Icon**: Visual category badge (`FolderKanban`).
    * **Project Name**: Primary heading (e.g., "Skyline Apartment").
    * **Property Type & Client Name**: Metadata tags.
    * **Floor Count Badge**: Number of floors associated with the project.
    * **"Open Design" Button**: Navigates directly to `/design-studio?project={id}&floor={first_floor_id}`.
    * **"Delete" Icon Button (`Trash2`)**: Prompts a `ConfirmDialog` to permanently delete the project.
* **Empty State (`EmptyState.tsx`)**:
  * Appears when no projects exist, displaying a clear call-to-action button: **"Create New Project"**.

---

### 3.3 Screen 2: Floor Plans Repository (`/floor-plans`)
* **URL Route**: `/floor-plans`
* **Component File**: `frontend/src/pages/FloorPlans.tsx`
* **Purpose**: Repository for browsing, filtering, inspecting, and uploading floor plans across projects.

#### Detailed Component & Interaction Reference
* **Top Action Bar**:
  * Subtitle text: *"Manage and organize your uploaded floor plans."*
  * **"Upload Floor Plan" Button**: Primary action button. Opens the universal `UploadModal`.
* **Floor Plan Toolbar (`FloorPlanToolbar.tsx`)**:
  * **Search Input Field**: Real-time filtering by file name.
  * **Project Dropdown Filter**: Filters floor plans by project.
  * **Floor Dropdown Filter**: Filters by assigned floor level.
  * **View Switcher (`Grid` / `List`)**: Toggles card grid view versus dense list view.
* **Floor Plan Card (`FloorPlanCard.tsx`)**:
  * Displays a thumbnail preview of the plan, project affiliation, file format (`PDF`, `PNG`, `JPG`), and upload timestamp.
  * Clicking the card navigates to the detailed view: `/floor-plans/{id}`.

---

### 3.4 Screen 3: Design Studio & 2D Canvas (`/design-studio`)
* **URL Route**: `/design-studio` (supports optional query params: `?project={id}&floor={floor_id}`)
* **Component File**: `frontend/src/pages/DesignStudio.tsx`
* **Purpose**: The central workspace of the application. Allows designers to pan/zoom vector floor plans, position furniture at true mm scales, inspect deterministic geometry, and trigger AI visualizations.

```
┌───────────────────────────────────────────────────────────────────────────────────────────────────┬──────────────────────┐
│ [Select Floor Plan: Villa_Level1.pdf ▼]  Villa · Level 1 · PDF · 2.4 MB   [ ☰ Menu ▼ ] [ ✨ AI Render ] │ Furniture Library   │
├───────────────────────────────────────────────────────────────────────────────────────────────────┼──────────────────────┤
│                                                                                                   │ 🔍 [Search...]       │
│                                                                                                   │                      │
│   ┌────────────────────────────────────────────────────────┐                                      │ ▼ LIVING ROOM        │
│   │ [Placing: Bed (1800x2000 mm) - Click to drop]   [Done] │                                      │   🛋️ Loungers Sofa   │
│   └────────────────────────────────────────────────────────┘                                      │   📦 Center Table    │
│                                                                                                   │   📦 Console         │
│                                                                                                   │                      │
│                       [2D Interactive Canvas]                                                     │ ▼ BEDROOM            │
│                       - Vector Wall Overlay                                                       │   🛏️ Bed (Selected)  │
│                       - Placed Furniture with Handles                                             │   📦 Side Table      │
│                       - Rotate, Resize & Drag                                                     │   📦 Wardrobe        │
│                       - Pan (Middle/Drag) & Zoom (Wheel)                                          │   📦 Dressing        │
│                                                                                                   │                      │
│                                                                                                   │ ▼ DINING & KITCHEN   │
│                                                                                                   │   📦 Dining Table    │
│                                                                                                   │   📦 Kitchen Base    │
│                                                                                                   │   📦 Chimney         │
└───────────────────────────────────────────────────────────────────────────────────────────────────┴──────────────────────┘
```

#### Detailed Component & Interaction Reference

#### 1. Top Canvas Control Bar (`studio-canvas__bar`)
* **Floor Plan Selector (`studio-plan-select`)**: Dropdown listing all available floor plans. Switching plans immediately loads that plan's vector layer and furniture layout.
* **Metadata Breadcrumb (`studio-canvas__meta`)**: Displays assigned project name, floor level, file type, and file size in megabytes.
* **Actions Menu Button (`☰ Menu`)**: Opens an action dropdown containing:
  * **Save (`Save`)**: Manually persists the furniture layout immediately. Shows status: `Saving…` or `Saved`. *(Layouts also autosave with a 600ms debounce).*
  * **Deterministic 3D (`Box`)**: Opens the full-house 3D WebGL reconstruction (`Scene3DModal`).
  * **View AI Renders (`Sparkles`)**: Opens the generation gallery displaying past renders for this plan.
  * **Backend Canvas (`Layers`)**: Opens `/api/floor-plans/{id}/control-image` in a new tab, displaying the server-generated vector control image.
  * **Upload Floor Plan (`Upload`)**: Opens the upload dialog pre-scoped to the current project and floor.
  * **Delete Floor Plan (`Trash2`)**: Prompts for confirmation to permanently delete the active floor plan, its layout, and associated renders.
* **Primary AI Render Button (`✨ AI Render`)**:
  * When idle: Triggers the full two-pass AI generation pipeline.
  * When generating: Displays `Generating… (Cancel)` with a spinner. Clicking cancels the active generation request.

#### 2. The 2D Geometry Canvas (`DesignCanvas.tsx`)
* Powered by HTML5 Canvas & Konva.
* **Pan & Zoom**: Smooth mouse-wheel zooming and drag-to-pan across large architectural drawings.
* **Floor Plan Layer**: Renders high-resolution PDF or raster background.
* **Furniture Layer**: Renders placed furniture footprints with millimetre labels, rotation indicators, and selection bounding boxes.
* **Interactive Transforms**:
  * **Drag**: Move furniture across the floor plan.
  * **Transformer Handles**: Click any corner handle to resize or rotate the furniture item.
  * **Inline Renaming**: Double-click or click the edit icon (`Pencil`) on an item to give it a custom label (e.g., "Master Bedroom Bed").
  * **Keyboard Shortcuts**: Pressing `Delete` or `Backspace` removes the currently selected furniture item.

#### 3. Furniture Library Drawer (`FurnitureLibrary.tsx`)
* Located on the right side of the canvas.
* **Search Input (`Search`)**: Instant client-side filtering across the furniture catalog.
* **Categorized Sections**:
  * **Living Room**: Loungers Sofa (`1900×900 mm`), Center Table (`1000×600 mm`), Console (`1100×350 mm`), Partition (`1800×300 mm`).
  * **Bedroom**: Bed (`1800×2000 mm`), Side Table (`450×450 mm`), Wardrobe (`1200×600 mm`), Dressing (`1200×600 mm`).
  * **Dining & Kitchen**: Dining Table (`1500×900 mm`), Dining Chair (`450×500 mm`), Kitchen Base Counter (`2400×600 mm`), Chimney (`900×500 mm`).
  * **Entry & Structure**: Bay Window Seating, Shoe Rack, Structural Doors, Structural Windows.
* **Placement Interaction**: Clicking any furniture item enters **Placement Mode**. A banner appears above the canvas: *"Placing [Item Name] — click on the plan to drop it."* Clicking anywhere on the canvas places the item at those exact coordinates.

---

### 3.5 Screen 4: Deterministic 3D Scene Viewer (`Scene3DModal`)
* **Trigger**: Click `☰ Menu` → `Deterministic 3D` in the Design Studio.
* **Component File**: `frontend/src/components/design-studio/Scene3DModal.tsx`
* **Purpose**: Interactive WebGL inspection of the **entire floor plan as one connected 3D model**. All rooms are joined by their shared structural walls, with ceilings and furniture rendered at real-world scale.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 3D Model — Full Floor Plan                                                  [⬇️ Download PNG] [✕] │
│ One connected 3D reconstruction — every room joined by its real walls                            │
├────────────────────────────────┬─────────────────────────────────────────────────────────────────┤
│ 2D PLAN REFERENCE              │ INTERACTIVE THREE.JS 3D VIEW                                    │
│                                │ Camera Presets: [ Perspective ] [ Top-Down ] [ Eye Level ]      │
│ ┌────────────────────────────┐ │                                                                 │
│ │                            │ │                     /|                                          │
│ │      Floor Plan            │ │                    / |  [Extruded 3D Walls]                     │
│ │      2D Section            │ │                   /__|                                          │
│ │      Reference             │ │                  |   |                                          │
│ │                            │ │            [3D Bed]  |  [3D Wardrobe]                           │
│ └────────────────────────────┘ │                                                                 │
│                                │ Orbit: Left-Click Drag | Pan: Right-Click Drag | Zoom: Wheel    │
└────────────────────────────────┴─────────────────────────────────────────────────────────────────┘
```

#### Detailed Component & Interaction Reference
* **Split View**:
  * **Left Side (`RoomSection2D.tsx`)**: Authoritative 2D reference showing the exact orientation and room boundary.
  * **Right Side (`RoomScene3D.tsx`)**: Full 3D Three.js canvas.
* **Camera Preset Selector**:
  * **Perspective**: 45° isometric/perspective camera looking into the architectural model.
  * **Top**: Orthographic top-down plan view confirming spatial layout.
  * **Eye Level**: Human perspective camera ($z = 1.4\text{m}$) inside the room.
* **Interactive Navigation**: Left-click and drag to orbit, right-click to pan, scroll wheel to zoom.
* **Download Button (`Download`)**: Exports the current 3D WebGL render as a high-resolution PNG snapshot.

---

### 3.6 Screen 5: AI Render Gallery & Comparison (`GenerationGallery`)
* **Trigger**: Automatic display upon AI generation completion, or via `☰ Menu` → `View AI Renders`.
* **Component File**: `frontend/src/components/design-studio/GenerationGallery.tsx`
* **Purpose**: Side-by-side verification and inspection comparing the authoritative 2D/3D floor plan layout directly against the photorealistic AI render.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ AI Render — Master Bedroom (Section 1 of 5)                                       [⬇️ Export] [✕] │
├────────────────────────────────┬─────────────────────────────────────────────────────────────────┤
│ AUTHORITATIVE GEOMETRY         │ PHOTOREALISTIC AI VISUALIZATION                                 │
│ [ 2D Plan ]  [ 3D Base ]       │ Style: Modern Luxury · Mood: Warm, layered architectural digest │
│                                │                                                                 │
│ ┌────────────────────────────┐ │ ┌─────────────────────────────────────────────────────────────┐ │
│ │                            │ │ │                                                             │ │
│ │  Deterministic 2D Crop     │ │ │  Photorealistic AI Render                                   │ │
│ │  or 3D Extruded Base       │ │ │  - Statuario Marble Wall                                    │ │
│ │                            │ │ │  - Exact Bed & Nightstands Preserved                        │ │
│ │                            │ │ │  - Photoreal Lighting & Shadows                             │ │
│ └────────────────────────────┘ │ └─────────────────────────────────────────────────────────────┘ │
│                                │                                                                 │
│ [🟢 18 Walls Verified]         │ [🟢 Geometry Locked] [🟢 Furniture Preserved]                   │
├────────────────────────────────┴─────────────────────────────────────────────────────────────────┤
│ Navigation:  [◀ Previous Room]    ( Room 1: Master Bedroom )    [▶ Next Room]                    │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

#### Detailed Component & Interaction Reference
* **Split-View Verification**:
  * **Left Pane**: Displays the source geometry (toggleable between the 2D plan region and the deterministic 3D base render).
  * **Right Pane**: Displays the high-resolution photorealistic AI output image.
* **Room Carousel Navigation**: `Previous (◀)` and `Next (▶)` controls cycle through all rooms in the floor plan (e.g., Bedroom 1, Living Room, Kitchen).
* **Fidelity Badges (`geometryBadges`)**:
  * Displays real-time validation checks: Wall Count, Door Alignment, Furniture Inventory Match, and Geometry Lock status.
* **Export Action (`Download`)**: Downloads the active high-resolution visualization directly to the user's computer.

---

### 3.7 Auxiliary Screens

#### Screen 6: Projects Overview (`/projects`)
* **File**: `frontend/src/pages/Projects.tsx`
* **Purpose**: List view of client engagements. Provides shortcuts to project-level settings and bulk exports.

#### Screen 7: AI History & Generations (`/ai-generations`)
* **File**: `frontend/src/pages/AIGenerations.tsx`
* **Purpose**: Audit log of historical rendering batches across projects.

#### Screen 8: Settings (`/settings`)
* **File**: `frontend/src/pages/Settings.tsx`
* **Purpose**: System preferences, AI provider status indicators (`fal.ai` vs `NVIDIA NIM`), and client environment diagnostic flags.

---

## 4. End-to-End Workflows & User Journeys

```mermaid
sequenceDiagram
    autonumber
    actor Designer as Interior Designer
    participant UI as Frontend (Studio & Canvas)
    participant BE as FastAPI Backend
    participant Geo as Geometry Engine (OpenCV/PyMuPDF)
    participant Capturer as BaseRenderBatch (WebGL)
    participant AI as Generative AI (fal.ai / NVIDIA)

    Designer->>UI: 1. Upload Floor Plan (PDF / Image)
    UI->>BE: POST /api/floor-plans/upload
    BE->>Geo: Extract walls, doors, windows & rooms
    Geo-->>BE: Structural Geometry Graph
    BE-->>UI: FloorPlan Created (ID, metadata)

    Designer->>UI: 2. Drag & Drop Furniture onto 2D Plan
    UI->>BE: PUT /api/floor-plans/{id}/layout (Debounced 600ms)
    BE-->>UI: Stored in canonical_json (Version Created)

    Designer->>UI: 3. Click "AI Render"
    UI->>BE: GET /api/floor-plans/{id}/scene
    BE-->>UI: Authoritative Scene Graph + current version_id
    
    UI->>Capturer: Mount offscreen Three.js WebGL (1216x832)
    Capturer-->>UI: Capture Deterministic Base PNG per room
    
    UI->>BE: POST /api/floor-plans/{id}/generate (with Base PNGs)
    BE->>BE: Validate Base Render (Version, Room, Non-blank, Size)
    
    BE->>AI: Pass A: Flux Depth ControlNet (Volume & Lighting)
    AI-->>BE: Intermediate Pass-A Render
    BE->>AI: Pass B: Flux Canny ControlNet (Edge & Floor Re-lock)
    AI-->>BE: Final Photoreal Render
    
    BE->>BE: Post-AI Geometry Validation Gate
    BE-->>UI: 201 Created (Generation Images)
    UI->>Designer: Display Generation Gallery with Side-by-Side Comparison
```

---

### Layout & Design Version Lifecycle State Machine

```mermaid
stateDiagram-v2
    [*] --> DraftEmpty: Floor Plan Ingested
    DraftEmpty --> Editing: Add Furniture Item
    
    state Editing {
        [*] --> MovingItem: Drag on Canvas
        MovingItem --> RotatingItem: Corner Handle Rotate
        RotatingItem --> RenamingItem: Edit Label
        RenamingItem --> [*]
    }
    
    Editing --> DebounceWait: Layout Modified (600ms timer)
    DebounceWait --> ComputeFingerprint: SHA-256 Hash on items array
    
    state FingerprintCheck <<choice>>
    ComputeFingerprint --> FingerprintCheck
    
    FingerprintCheck --> SkippedSave: Hash unchanged (Identical)
    FingerprintCheck --> PersistNewVersion: Hash differs (New Layout)
    
    PersistNewVersion --> ActiveVersion: Increment version_number
    SkippedSave --> ActiveVersion
    
    ActiveVersion --> BaseRenderCapture: "AI Render" Triggered
    BaseRenderCapture --> TwoPassAI: Valid 1216x832 Base PNG
    TwoPassAI --> ValidatedRender: Passes Quality Gates
    ValidatedRender --> [*]
```

### Workflow A: Project Creation & Onboarding

1. **User Action**: The designer navigates to the Dashboard (`/dashboard`) and clicks **"New Project"**.
2. **Input**:
   * Project Name (e.g., *"Al-Reem Luxury Penthouse"*).
   * Client Name (e.g., *"Majid Al-Futtaim"*).
   * Property Type (e.g., *"Duplex Residential"*).
   * Initial Floors (e.g., *"Ground Floor"*, *"First Floor"*).
3. **System Processing**: `POST /api/projects` creates the project and associated floor records in PostgreSQL.
4. **Result**: The dashboard immediately renders the new project card. Clicking **"Open Design"** navigates the designer directly to the Design Studio scoped to that project.

---

### Workflow B: Floor Plan Upload & Vector Geometry Extraction
1. **User Action**: Inside the Design Studio or Floor Plans page, the user clicks **"Upload Floor Plan"**.
2. **Input**: A vector PDF or architectural drawing file (`.pdf`, `.png`, `.jpg`).
3. **System Processing**:
   * `file_storage.save_upload_stream`: File bytes are validated against size (`MAX_FILE_SIZE = 50 MB`) and mime type.
   * `geometry_extraction_service.extract_walls`: If a vector PDF is provided, PyMuPDF extracts vector drawing paths, identifying architectural wall lines, stroke thicknesses, and corner intersections.
   * `architectural_service.extract_doors_and_windows`: Classifies openings along structural walls.
   * `architectural_service.reconstruct_rooms`: Builds polygon boundaries for distinct rooms (e.g., Living Room, Master Bedroom).
4. **Result**: The plan appears in the Design Studio canvas, fully rasterized with detected rooms and boundaries ready for furniture placement.

---

### Workflow C: 2D Spatial Furniture Arrangement & Versioning
1. **User Action**: The user selects an item from the **Furniture Library** (e.g., "Bed") and clicks on the floor plan inside "Bedroom 1".
2. **Canvas Manipulation**:
   * The user drags the bed into place against the north wall.
   * Using the corner transformer handles, the user rotates the bed to $90^\circ$ orientation.
   * The user adds two "Side Table" units flanking the bed.
3. **Autosave & Invariant Protection**:
   * Changes trigger a debounced (600ms) save to `PUT /api/floor-plans/{id}/layout`.
   * The backend generates a SHA-256 fingerprint of all placed furniture items. If the layout has changed, an append-only `DesignVersion` record is written to the database.
   * **Crucial Rule**: The geometry extraction service never overwrites user furniture, and user furniture never alters architectural walls.

---

### Workflow D: Full House 3D Assembly & Geometry Inspection
1. **User Action**: The user clicks `☰ Menu` → **"Deterministic 3D"**.
2. **Processing**:
   * The frontend calls `GET /api/floor-plans/{id}/scene`.
   * `scene_service.build_scene` compiles the authoritative structural walls and placed furniture into a single scene payload.
   * `computeMpp` calibrates real-world millimetres to WebGL units using standard human-scale anchors.
   * `RoomScene3D` extrudes walls vertically, builds door openings, punches windows, lays down flooring, and positions 3D furniture meshes with exact dimensions and rotation.
3. **Result**: The designer interacts with the full 3D house in real time, validating sightlines and clearance before spending any AI rendering credits.

---

### Workflow E: Two-Pass Deterministic AI Visualization Pipeline
1. **User Action**: The user clicks **"✨ AI Render"** in the top bar.
2. **Step 1: Offscreen Base Capture**:
   * The client mounts `BaseRenderBatch.tsx` in a hidden container.
   * Three.js renders each room at an exact resolution of `1216×832` pixels from a calculated eye-level camera.
   * The canvas backing store captures uncompressed PNG snapshots of the deterministic 3D base.
3. **Step 2: Dispatch to Generation Service**:
   * The client sends `POST /api/floor-plans/{id}/generate`, packaging the base PNGs alongside the active `design_version_id`.
4. **Step 3: Server-Side Base Verification**:
   * The backend confirms that the base render matches the active design version, matches the target room, is non-blank, and matches exact pixel dimensions.
5. **Step 4: Two-Pass AI Generation**:
   * **Pass A (Flux Depth ControlNet)**: Synthesizes rich 3D materials, textures, fabrics, marble surfaces, and realistic lighting based on the room's depth buffer.
   * **Pass B (Flux Canny ControlNet)**: Re-locks floor level flatness and exact furniture silhouettes using edge detection against the deterministic base render.
6. **Step 5: Post-AI Validation & Display**:
   * The generated images are verified against geometry drift gates.
   * Passing images are saved to disk and recorded in `ai_generation_images`.
   * The `GenerationGallery` automatically opens on the client screen, displaying the final photorealistic renders side by side with the floor plan.

---

## 5. Input, Processing & Output Technical Specifications

### 1. File Ingestion & Parsing
* **Inputs**:
  * File types: `.pdf`, `.png`, `.jpg`, `.jpeg`, `.webp`.
  * Maximum size: 50 MB (`MAX_FILE_SIZE = 50 * 1024 * 1024`).
* **Processing**:
  * `storage/file_storage.py::save_upload_stream`: Streams file to disk chunk-by-chunk (`_CHUNK_SIZE = 1 MB`) to prevent memory exhaustion.
  * Server-side UUID path isolation: `storage/floor_plans/{project_id}/{floor_id}/{file_id}/original.<ext>`.
* **Output**: `FloorPlanResponse` containing `file_id`, sanitized filename, dimensions, and upload timestamp.

---

### 2. Architectural Extraction & Room Topology
* **Inputs**: Vector PDF path on disk.
* **Processing**:
  * `geometry_extraction_service.py`: Uses `fitz` (PyMuPDF) to extract PDF drawing paths and vectors.
  * Segments walls into coordinate lists: `[[x1, y1], [x2, y2]]`.
  * Detects door swings and window symbols via stroke color and geometry.
  * Reconstructs closed polygonal loops as distinct architectural rooms.
* **Output**: Structural geometry graph stored alongside the plan:
  ```json
  {
    "walls": [[[120.5, 45.0], [380.0, 45.0]], ...],
    "openings": [{"type": "door", "cx": 210.0, "cy": 45.0, "status": "VALID"}],
    "rooms": [{"id": "room-1", "label": "Master Bedroom", "bbox": [100, 40, 300, 250]}]
  }
  ```

---

### 3. Layout Persistence & Version Snapshots
* **Inputs**: `LayoutPayload` containing array of placed furniture items:
  ```json
  {
    "items": [
      {
        "uid": "bed-1718000-a1b2c3d4",
        "item_id": "bed",
        "cx": 245.5,
        "cy": 180.2,
        "w": 270.0,
        "h": 300.0,
        "rotation": 0,
        "label": "Master Bed"
      }
    ]
  }
  ```
* **Processing**:
  * `floor_plan_service.py::save_layout`:
    1. Computes SHA-256 fingerprint across all items.
    2. Compares against latest `DesignVersion.canonical_json`.
    3. If modified, inserts a new append-only `DesignVersion` record with incremented `version_number`.
* **Output**: Updated `LayoutPayload` with confirmed version persistence.

---

### 4. Deterministic 3D Base Capture
* **Inputs**: Authoritative room scene data and camera parameters (`solveEyeLevelCamera`).
* **Processing**:
  * Offscreen rendering via `BaseRenderBatch.tsx` with fixed device pixel ratio (`dpr={1}`).
  * Capture container dimensions: exactly `1216 × 832` pixels.
  * `canvas.toDataURL("image/png")` extracts the raw base PNG data.
* **Output**: Base render map transmitted via HTTP:
  ```json
  {
    "base_renders": {
      "room-1": "data:image/png;base64,iVBORw0KGgo..."
    },
    "base_render_meta": {
      "design_version_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
      "width": 1216,
      "height": 832
    }
  }
  ```

---

### 5. AI Diffusion Rendering (ControlNet Depth + Canny)

```mermaid
flowchart TD
    subgraph InputStage [1. Input Preparation]
        BR[Deterministic 3D Base PNG<br/>1216x832 px]
        PR[Architectural Prompt<br/>Materials + Style + Lighting]
        MC[Master Invariant Constraint<br/>Lock walls, openings, layout]
    end

    subgraph PassA [2. Pass A: Volume & Lighting Synthesis]
        CN_Depth[fal-ai/flux-control-lora-depth<br/>Control Strength: 1.0]
        BR -->|Extract 3D Depths| CN_Depth
        PR & MC --> CN_Depth
        CN_Depth --> ImgA[Pass A Intermediate Output<br/>Photoreal Materials & Lighting]
    end

    subgraph PassB [3. Pass B: Edge & Boundary Re-locking]
        CN_Canny[fal-ai/flux-control-lora-canny<br/>Control Strength: 1.0]
        BR -->|Extract Exact Edges| CN_Canny
        ImgA -->|Image Input| CN_Canny
        CN_Canny --> ImgB[Final Photoreal AI Render<br/>1216x832 High Resolution]
    end

    subgraph ValidationStage [4. Automated Quality Gate Audit]
        ImgB --> G1{Decodable &<br/>Non-corrupted?}
        G1 -- No --> FAIL[Reject: Corrupted Payload]
        G1 -- Yes --> G2{Std Dev > 5.0<br/>Not Blank?}
        G2 -- No --> FAIL
        G2 -- Yes --> G3{Aspect Ratio<br/>1216x832 Match?}
        G3 -- No --> FAIL
        G3 -- Yes --> G4{Meaningful<br/>Styling Delta?}
        G4 -- No --> FAIL
        G4 -- Yes --> PASS[PASS: Recorded in DB & UI Gallery]
    end

    style InputStage fill:#f8fafc,stroke:#94a3b8,stroke-width:1px
    style PassA fill:#eff6ff,stroke:#3b82f6,stroke-width:2px
    style PassB fill:#f0fdf4,stroke:#22c55e,stroke-width:2px
    style ValidationStage fill:#fefce8,stroke:#eab308,stroke-width:1px
    style PASS fill:#dcfce7,stroke:#16a34a,stroke-width:2px
    style FAIL fill:#fee2e2,stroke:#ef4444,stroke-width:2px
```

* **Inputs**:

  * Base Render PNG (`1216×832`).
  * Synthesized Architectural Prompt (`prompt_service.py`):
    ```
    Modern Luxury interior design, Master Bedroom, warm elegant architectural digest aesthetic,
    layered lighting, concealed 3000K warm LED cove strip lighting, Statuario porcelain marble
    accent wall, vertical fluted oak slat panels, textured bouclé upholstery, large-format polished
    marble floor tiles. Highly detailed, 8k resolution, photorealistic interior photograph.
    ```
  * Master AI Constraint (`MASTER_CONSTRAINT`):
    * *Preserve exact wall positions, window openings, door locations, and furniture placements.*
* **Processing**:
  * **Pass A**: `fal-ai/flux-control-lora-depth` at `strength = 1.0` paints materials, textures, and lighting over 3D volumes.
  * **Pass B**: `fal-ai/flux-control-lora-canny` at `strength = 1.0` re-locks structural edges and flat floors using the base image as control input and Pass A as image input.
* **Output**: High-resolution photorealistic PNG image (`1216×832`).

---

### 6. Post-AI Geometry Validation Gates
* **Inputs**: Generated AI image bytes and reference base render image bytes.
* **Processing (`validation_service.py::assess_ai_output_geometry`)**:
  1. **Decodability Check**: Verifies image headers and decodes via Pillow.
  2. **Blank Output Check**: Verifies standard deviation of pixel intensities (`std_dev > 5.0`).
  3. **Aspect Ratio Check**: Verifies that generated aspect ratio strictly matches expected dimensions.
  4. **Difference Verification**: Confirms that AI meaningfully styled the room rather than returning an unrendered copy or blank canvas.
* **Output**: Gate status `PASS` or rejection with error code (`FAILED_GEOMETRY_VALIDATION`).

---

## 6. First-Time User Step-by-Step Practical Guide

### Step 1: Accessing the Studio
1. Open your browser and navigate to `http://localhost:5173`.
2. The application opens directly to the **Project Dashboard** (`/dashboard`).
3. Check the top header: if the API server is healthy, the application displays `MYNEST DESIGN STUDIO` with no connection error banners.

---

### Step 2: Creating Your Client Project
1. On the top right of the Projects section, click **"New Project"**.
2. A modal dialog appears:
   * **Project Name**: Enter your project title (e.g., *"Villa Serene"*).
   * **Client Name**: Enter your client's name (e.g., *"Dr. Robert Chen"*).
   * **Property Type**: Select or enter *"Residential Apartment"*.
   * **Floors**: Enter *"Floor 1"*.
3. Click **"Create Project"**. The new project card appears on the dashboard.

---

### Step 3: Uploading a Floor Plan (Top-Right Action)
1. Click **"Open Design"** on your new project card to enter the **Design Studio**.
2. In the top right of the canvas toolbar, click the **`☰ Menu`** button.
3. In the dropdown menu, select **"Upload Floor Plan"** (`Upload` icon).
4. The **Upload Floor Plan** dialog opens:
   * **Drag & Drop** your PDF or image floor plan file into the upload dropzone, or click **"Browse files"**.
   * Note the file specifications: PDF, PNG, or JPG up to 50 MB.
   * The project and floor fields are pre-populated with your current project.
5. Click **"Upload"**. A progress indicator tracks the upload. Once complete, the dialog automatically closes and your floor plan renders on the interactive canvas.

---

### Step 4: Arranging Furniture on the 2D Plan
1. Look at the **Furniture Library** drawer on the right side of the screen.
2. Under the **Bedroom** category, click on **"Bed"** (`1800 × 2000 mm`).
3. Notice the blue placement banner appears above the canvas: *"Placing Bed — click on the plan to drop it."*
4. Click inside the master bedroom area on your floor plan. The bed appears on the canvas.
5. **Adjusting the Furniture**:
   * Click and drag the bed to position it against the desired wall.
   * Click on the rotation handle to rotate the bed.
   * Return to the Furniture Library and select **"Side Table"** (`450 × 450 mm`). Click on either side of the bed to place bedside tables.
6. Notice the top menu briefly displays `Saving…` and then `Saved`. Your layout is automatically persisted.

---

### Step 5: Verifying Real 3D Walls and Proportions
1. Click the top **`☰ Menu`** button.
2. Select **"Deterministic 3D"** (`Box` icon).
3. The **3D Model — Full Floor Plan** modal opens.
4. Verify the 3D scene:
   * Click the **"Eye Level"** camera preset to view the room from human standing height.
   * Left-click and drag to look around the room. Confirm that the bed and nightstands sit accurately against the structural walls.
5. Click the close button (`✕`) in the top right to return to the 2D canvas.

---

### Step 6: Executing AI Photorealistic Visualization
1. In the top right canvas toolbar, click the **"✨ AI Render"** button.
2. The button transitions to **`Generating… (Cancel)`**.
3. What the system is doing behind the scenes:
   * Captures deterministic 3D base views for each room.
   * Sends the base renders to the two-pass Flux ControlNet pipeline.
   * Applies luxury interior materials (Italian marble, fluted oak, warm LED lighting).
   * Validates that furniture and walls have not drifted.
4. *Note: If you need to stop the render, click the button again to cancel immediately.*

---

### Step 7: Side-by-Side Verification & Export
1. Upon completion, the **AI Render Gallery** modal opens automatically.
2. The left pane shows your authoritative 2D plan and 3D base geometry.
3. The right pane displays the finished photorealistic AI interior render.
4. Verify that:
   * The bed and side tables in the render match the exact positions from your 2D plan.
   * The wall materials, lighting, and textures look photorealistic and customer-ready.
5. Click the **"Export"** button (`Download` icon) at the top right to download the high-resolution visualization for client presentation.

---

## 7. API & Service Endpoint Reference

### Health & Diagnostics
* `GET /api/health`
  * **Description**: Server liveness check.
  * **Response**: `200 OK` → `{"status": "ok"}`
* `GET /api/ai-diagnostics`
  * **Description**: Returns active AI provider configuration, model, endpoint, and capability flags (never exposes raw API keys).

### Projects & Floors (`/api/projects`)
* `GET /api/projects`
  * **Description**: Retrieves all projects with their associated floors.
* `POST /api/projects`
  * **Description**: Creates a new project and associated floor levels.
  * **Request Body**:
    ```json
    {
      "name": "Skyline Duplex",
      "client_name": "Elena Rostova",
      "property_type": "Residential",
      "floors": [{"name": "Ground Level"}, {"name": "Upper Level"}]
    }
    ```
* `DELETE /api/projects/{project_id}`
  * **Description**: Permanently deletes a project, cascading to all associated floors, plans, and layouts.

### Floor Plans (`/api/floor-plans`)
* `POST /api/floor-plans/upload`
  * **Method**: `multipart/form-data`
  * **Fields**: `file` (binary), `project_id` (string, optional), `floor_id` (string, optional).
  * **Response**: `201 Created` → `FloorPlanResponse`
* `GET /api/floor-plans`
  * **Query Params**: `project_id`, `floor_id`, `search`.
  * **Response**: List of `FloorPlanResponse` objects.
* `GET /api/floor-plans/{file_id}/file`
  * **Description**: Streams the original binary file (`application/pdf`, `image/png`, etc.) inline.
* `GET /api/floor-plans/{file_id}/layout`
  * **Description**: Fetches the latest furniture layout (`items` array).
* `PUT /api/floor-plans/{file_id}/layout`
  * **Description**: Saves and versions the furniture layout.
  * **Request Body**: `{"items": [PlacedItem, ...]}`
* `GET /api/floor-plans/{file_id}/scene`
  * **Description**: Builds the authoritative 2D/3D scene graph (walls, rooms, openings, furniture, and current `design_version_id`).
* `GET /api/floor-plans/{file_id}/room-eligibility`
  * **Description**: Pre-flight check reporting which rooms are eligible for AI rendering and why unproven rooms are gated.
* `GET /api/floor-plans/{file_id}/control-image`
  * **Description**: Generates a high-contrast vector PNG control image containing architectural walls and furniture footprints.
* `POST /api/floor-plans/{file_id}/generate`
  * **Description**: Triggers the AI visualization pipeline.
  * **Request Body**:
    ```json
    {
      "provider": "fal",
      "count": 1,
      "rooms": ["room-1"],
      "all_sections": true,
      "base_renders": {"room-1": "data:image/png;base64,..."},
      "base_render_meta": {
        "design_version_id": "uuid",
        "width": 1216,
        "height": 832
      }
    }
    ```
  * **Response**: `201 Created` → `GenerationResponse`

### Generations (`/api/generations`)
* `GET /api/generations/{generation_id}/images/{index}.png`
  * **Description**: Streams the high-resolution generated PNG render directly from storage.

---

## 8. Error Handling, Validation Gates & Troubleshooting

### Pre-Flight and Base Render Gates
The system enforces strict pre-flight gates to guarantee that only valid geometry is sent to AI models:

```mermaid
flowchart TD
    Req[Incoming Generation Request] --> Check1{Enclosed Room Polygon?}
    Check1 -- No --> E1[422 BASE_GEOMETRY_INVALID<br/>Check wall closure]
    Check1 -- Yes --> Check2{At least 1 Furniture item?}
    Check2 -- No --> E2[422 ROOM_EMPTY<br/>Place furniture in room]
    Check2 -- Yes --> Check3{Version ID matches latest?}
    Check3 -- No --> E3[409 BASE_RENDER_WRONG_VERSION<br/>Refresh scene capture]
    Check3 -- Yes --> Check4{Exact 1216x832 px?}
    Check4 -- No --> E4[400 BASE_RENDER_WRONG_SIZE<br/>Check browser dpr/zoom]
    Check4 -- Yes --> Check5{Non-blank pixels?}
    Check5 -- No --> E5[400 BASE_RENDER_MISSING / BLANK<br/>Check WebGL acceleration]
    Check5 -- Yes --> Ready[Dispatch to 2-Pass AI Engine]

    style Req fill:#f1f5f9,stroke:#64748b,stroke-width:1px
    style Ready fill:#dcfce7,stroke:#16a34a,stroke-width:2px
    style E1 fill:#fee2e2,stroke:#ef4444,stroke-width:1px
    style E2 fill:#fee2e2,stroke:#ef4444,stroke-width:1px
    style E3 fill:#fee2e2,stroke:#ef4444,stroke-width:1px
    style E4 fill:#fee2e2,stroke:#ef4444,stroke-width:1px
    style E5 fill:#fee2e2,stroke:#ef4444,stroke-width:1px
```

| Gate Code | Meaning | User Recovery Action |
| :--- | :--- | :--- |
| `BASE_GEOMETRY_INVALID` | Room boundary could not be deterministically closed from the floor plan drawing. | Re-inspect the source floor plan to ensure wall lines form an enclosed room polygon. |
| `ROOM_EMPTY` | The selected room contains no placed furniture items. | Select furniture from the Furniture Library and place at least one item in the room before rendering. |
| `BASE_RENDER_WRONG_VERSION`| The captured 3D base render was created from an older layout version than the server's current version. | Close and re-open the plan; the system will capture a fresh base matching the latest layout. |
| `BASE_RENDER_WRONG_SIZE` | The captured base image dimensions do not match the required `1216×832` resolution (typically caused by browser zoom or HiDPI scaling). | The client forces `dpr={1}` during capture. If triggered, reset browser zoom to 100% and retry. |
| `BASE_RENDER_MISSING / BLANK` | WebGL capture failed to render or returned empty/transparent pixels. | Verify WebGL hardware acceleration is enabled in your browser settings. |


---

### Post-AI Validation Gate Codes
Every AI output image is checked before being saved or presented to the user:

* `FAILED_GEOMETRY_VALIDATION`: The generated image failed post-render checks (e.g., corrupted image stream, aspect ratio mismatch, or blank output). The system marks the generation as `failed` and surfaces a descriptive error message in the UI toast.

---

### Troubleshooting Common Issues

#### 1. "Backend Status: Disconnected" on the Frontend
* **Cause**: FastAPI server is not running or running on an unexpected port.
* **Fix**: Ensure the backend is running at `http://localhost:8001` or `http://localhost:8000`. Check `frontend/vite.config.ts` to confirm the proxy target matches your backend port.

#### 2. AI Generation Returns 401 Unauthorized
* **Cause**: Missing or invalid AI provider API key.
* **Fix**: Verify `FAL_KEY` (for fal.ai) or `NVIDIA_API_KEY` (for NVIDIA) is set in `backend/.env`. Restart the backend server after editing `.env`.

#### 3. AI Generation Fails with "Quota / Rate Limit Exceeded" (429)
* **Cause**: The external AI provider account has exhausted its compute credits.
* **Fix**: Top up credits on your provider dashboard (`fal.ai` or `build.nvidia.com`).

#### 4. Furniture Moves Unexpectedly or Resets on Refresh
* **Cause**: Layout failed to persist to the database before the page reloaded.
* **Fix**: Always look for the **`Saved`** checkmark in the `☰ Menu` button before navigating away from the Design Studio.

---

## 9. Developer Setup & Local Execution Guide

### Prerequisites
* **Node.js**: v18.x or v20.x LTS
* **Python**: v3.11.x (Python 3.12+ may encounter C-extension issues with PyMuPDF)
* **PostgreSQL / Supabase**: Accessible PostgreSQL database instance (or Supabase project)
* **Operating System**: Windows, macOS, or Linux

---

### Backend Environment Setup
1. Open a terminal and navigate to the backend directory:
   ```bash
   cd backend
   ```
2. Create and activate a Python virtual environment:
   * **Windows (PowerShell)**:
     ```powershell
     python -m venv .venv
     .venv\Scripts\Activate.ps1
     ```
   * **macOS / Linux**:
     ```bash
     python3 -m venv .venv
     source .venv/bin/activate
     ```
3. Install runtime and development dependencies:
   ```bash
   pip install -r requirements.txt
   pip install -r requirements-dev.txt
   ```
4. Configure environment variables by copying `.env.example`:
   ```bash
   cp .env.example .env
   ```
5. Edit `backend/.env` with your database and AI credentials:
   ```ini
   # Database Configuration (Supabase / PostgreSQL)
   DATABASE_URL=postgresql://postgres:your_password@db.your_supabase.co:5432/postgres

   # AI Provider Configuration
   DEFAULT_AI_PROVIDER=fal
   FAL_KEY=your_fal_ai_api_key_here
   FAL_IMAGE_MODEL=fal-ai/flux-lora-depth

   # Optional NVIDIA NIM Configuration
   NVIDIA_API_KEY=your_nvidia_api_key_here
   NVIDIA_IMAGE_MODEL=stabilityai/flux1-dev
   ```

---

### Frontend Environment Setup
1. Open a terminal and navigate to the frontend directory:
   ```bash
   cd frontend
   ```
2. Install npm package dependencies:
   ```bash
   npm install
   ```
3. (Optional) Create a `.env` file if customizing the API proxy:
   ```ini
   VITE_API_URL=http://localhost:8001
   ```

---

### Running the Services Locally

#### 1. Start the FastAPI Backend
```bash
cd backend
# Ensure virtualenv is active
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8001
```
* Interactive API documentation is available at: `http://localhost:8001/docs`
* API health check endpoint: `http://localhost:8001/api/health`

#### 2. Start the Vite Frontend Development Server
```bash
cd frontend
npm run dev
```
* Vite will start the development server at: `http://localhost:5173`
* Open your browser and navigate to `http://localhost:5173` to access the application.

---

### Testing, Type-Checking & Quality Gates

The project maintains strict automated quality gates. Always run these before committing code:

#### Backend Quality Gates
```bash
cd backend
# 1. Format and lint checks with Ruff
ruff check .
ruff format --check .

# 2. Strict static type analysis with Mypy
mypy app

# 3. Automated test suite with Pytest
python -m pytest tests/
```

#### Frontend Quality Gates
```bash
cd frontend
# 1. Strict TypeScript compilation check
npm run type-check

# 2. ESLint checks
npm run lint

# 3. Production build verification
npm run build
```

---

## 10. Architecture Principles & Maintenance Guide

When contributing to or extending MyNest Design Studio, adhere strictly to these core architectural guidelines:

1. **Geometry Invariant Protection**:
   * Never introduce an automated process that alters, snaps, simplifies, or normalizes wall coordinates or room boundaries without explicit user command.
   * AI adapters must never return new coordinate locations for furniture or walls.
2. **Deterministic Precedence**:
   * If a conflict occurs between an AI visual output and the deterministic floor plan geometry, **the floor plan geometry always wins**.
3. **Storage & Database Separation**:
   * Binary image files and PDFs must reside in the storage filesystem abstraction (`file_storage.py`).
   * Only metadata, relational linkages, and canonical JSON documents belong in PostgreSQL.
4. **Isolated Frontend Stores**:
   * Avoid monolithic state objects. Use dedicated Zustand stores for the Editor viewport, active selection, and UI dialog states.
5. **Secrets Management**:
   * Never commit `.env` files or API keys to version control. AI keys must remain server-side and are never exposed to browser clients.

---

*MyNest Design Studio — Engineered for architectural precision and photorealistic visual excellence.*
