# Architecture

This document describes the high-level architecture of MyNest Design Studio. It is a living document; sections will be expanded as features are implemented.

## Guiding principle

> **The floor-plan geometry is the source of truth. AI is never the source of truth for geometry.**

The deterministic geometry engine and the 2D editor are **authoritative** for walls, rooms, doors, windows, openings, and furniture (coordinates, dimensions, orientation, placement). The AI layer is a **visualizer only** — it may enhance materials, textures, colors, lighting, shadows, reflections, and render realism, but must not add, move, or remove geometry.

Correct data flow:

```
Floor Plan → Geometry Engine → Canonical Design JSON → 2D Editor → AI Renderer (non-authoritative)
```

Never build `Floor Plan → AI → Final Geometry`.

## Repository layout

```
mynest-design-studio/
├── frontend/     React + TypeScript + Vite
│   └── src/
│       ├── components/   reusable UI components
│       ├── features/     feature modules (dashboard, editor, ai, ...)
│       ├── lib/          shared utilities & API client
│       ├── store/        state slices (project, editor, furniture, ...)
│       ├── types/        shared TypeScript types
│       └── styles/       global styles
├── backend/      Python + FastAPI
│   └── app/
│       ├── api/v1/       versioned HTTP routes
│       ├── core/         config & app wiring
│       ├── services/     service boundaries (project, geometry, ai, ...)
│       ├── models/       persistence models
│       └── schemas/      request/response schemas
└── docs/
```

## Planned service boundaries (backend)

`ProjectService`, `FloorPlanService`, `RoomService`, `GeometryService`, `FurnitureService`, `DesignVersionService`, `ValidationService`, `PromptService`, `AIProviderService`, `GenerationService`, `ExportService`.

The `GeometryService` and `ValidationService` are authoritative. The AI services are strictly downstream consumers of a frozen, validated canonical design version — they can never mutate geometry.

## Planned frontend state ownership

Separate stores (no single giant state object): Project · Floor Plan · Editor · Furniture · Selection · Design Version · AI Generation.

## Security

AI provider API keys are **server-side only** (environment variables). They are never shipped to or callable from the browser; all provider calls are proxied through the backend.
