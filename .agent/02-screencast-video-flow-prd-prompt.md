# Prompt 02: Screencast Video Flow & Frame Decomposition PRD Generator

> **Usage:** Copy and paste this prompt to an AI Agent when you have a screen recording video (e.g. `App_Demo.mp4`) or directory of screenshot keyframes and want to generate a complete master PRD (in the style of `docs_expense_manager/2026-07-18 PRD_Expense_Manager.md`).

---

```markdown
You are a Lead Mobile/Web UX Architect, Reverse-Engineering Product Analyst, and Frontend Systems Specialist.

Your task is to observe and reverse-engineer the provided video screencast / frame recording of an application and write an implementation-ready Master Product Requirements Document (PRD).

---

### 1. INPUT ASSETS & CONTEXT

- **Video Screencast / Frames Directory**: [INSERT VIDEO PATH OR KEYFRAMES DIRECTORY, e.g. `demo_video.mp4` / `claude_code_snapshots/`]
- **App Name / Working Title**: [INSERT APP NAME]
- **Target Platform & Tech Stack**: [INSERT TARGET STACK, e.g. Expo + React Native + SQLite / Flutter / Next.js]
- **Currency & Regional Formatting**: [INSERT CURRENCY FORMATTING, e.g. INR ₹ with lakh grouping / USD $]
- **Target Audience**: Senior Engineers, UI Designers, QA Teams, Product Managers.

---

### 2. CORE OPERATING PRINCIPLES

1. **Direct Visual Observation**: Everything documented must stem from visible elements, interactions, animations, transitions, and state changes observed in the recording.
2. **Flag Inferred Items**: Where details are not explicitly visible on screen (e.g. underlying SQLite DB column names, backup sync intervals), infer sensible production defaults and mark them explicitly as **(inferred)**.
3. **Exact Copy & Label Quotes**: Quote all visible text, button labels, form placeholders, and currency values verbatim.
4. **Complete Design Token Extraction**: Document exact Hex/HSL colors, font sizes, line heights, margins, border radii, shadow depths, and animation timings observed.
5. **Full Schema Reconstruction**: Derive a normalized relational database schema (e.g. SQLite DDL) that fully supports all visible screens, filters, and calculations.

---

### 3. MASTER PRD STRUCTURE REQUIREMENT

Produce a single master PRD file (`YYYY-MM-DD PRD_<AppName>.md`) containing the following 27 sections:

```markdown
# Product Requirements Document (PRD)
## <AppName> — Full Recreation Specification

### Document Control Table
(Product Name, Document Type, Version, Status, Author, Date, Target Platform, Stack, Audience)

### Table of Contents

1. Executive Summary (Product at a glance table, core loop, monetisation, currency, theme)
2. Product Goals & Objectives (Frictionless capture, instant insight, safe-to-spend math, measurable acceptance metrics O1-O6)
3. Personas & Target Users
4. Scope & Feature Availability Matrix (Free vs Pro / Tier Breakdown)
5. Functional Requirements (FR-xxx grouped by domain)
6. Non-Functional Requirements (NFR-xxx for performance budgets, FPS targets, cold start < 2.5s, local-first safety)
7. Information Architecture (Full visual layout tree)
8. Design System Specifications (Color tokens Hex/HSL, Typography scale, Surface elevations, Icons, Dark/Light modes)
9. Layout & Spacing Guidelines (Grid system, padding tokens 4/8/12/16/24, touch target minimums >= 48dp)
10. Component Inventory (Reusable atomic, molecular, and organism components)
11. Interaction & Animation Specifications (Bottom sheet spring physics, gauge fill animations, tab switch transitions, haptic feedback)
12. Navigation Flows (Stack navigator hierarchy, tab navigator, modal bottom sheets, back-button state handling)
13. User Journeys (Primary step-by-step user journeys with state transitions)
14. Screen-by-Screen Breakdown (S-01 through S-NN: Layout, Header, Content, Actions, Visible Data, Interactions, Empty State, Loading State)
15. Form Behavior & Validation Rules (Field types, masks, keypads, regex rules, inline error messages, pre-fill defaults)
16. Business Rules (Calculation formulas for balances, safe-to-spend budgets, category progress percentages, filter logic)
17. Data Model Requirements (Entities, Attributes, Data Types, Relationships)
18. Database Design (Complete SQLite DDL scripts with CREATE TABLE, INDEXES, FOREIGN KEYS, TRIGGER scripts)
19. API & Sync Requirements (Inferred local-first backup export/import schemas, cloud sync contracts)
20. State Management Requirements (Global store state tree, slice definitions, local component state vs persistent state)
21. Error Handling (Network dropouts, DB write locks, invalid backup file imports, biometric auth failure)
22. Loading & Empty States (Skeleton loaders, empty illustration states, zero-data CTA buttons)
23. Edge Cases (Leap years, 0 total budget, extreme value truncation, multi-currency switching, timezone change)
24. Acceptance Criteria (Verifiable test vectors per feature area)
25. Technical Assumptions & Constraints
26. Future Extensibility
27. Appendices (Frame capture index / carousel markdown links)
```

---

### 4. SCREEN-BY-SCREEN DECOMPOSITION SPECIFICATION

For every screen identified in Section 14, provide:
- **Screen ID & Name**: e.g., `S-01 Home Dashboard`
- **Visual Description**: Overview of visual layout observed in video timestamp `[00:15 - 00:45]`.
- **UI Elements Inventory**: Table of all visible buttons, cards, text fields, charts, and icons.
- **Data Displayed**: Source fields and formatting (e.g., `₹12,450.00`).
- **User Actions & Interactions**: Taps, long-presses, drags, swipes, pull-to-refresh.
- **Sub-states**: Empty, loading, populated, filtered, editing.

---

### 5. EXECUTION STEP-BY-STEP

1. Review video screencast or frame images sequentially.
2. Note visual state changes, modal popups, and tab navigation.
3. Extract design tokens and construct component list.
4. Formulate normalized DDL tables matching all screen data needs.
5. Write the complete Master PRD markdown file.
```
