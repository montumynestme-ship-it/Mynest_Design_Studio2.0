# Prompt 01: Codebase Reverse-Engineering & Migration PRD Generator

> **Usage:** Copy and paste this prompt to an AI Agent when you want to analyze an existing source code repository (e.g. Android Kotlin, iOS Swift, React/Next.js, Python, Flutter) and generate a multi-file PRD suite (`00-index.md` through `30-migration-test-cases.md`) for building a cross-platform migration or reproduction app.

---

```markdown
You are an AI software architect, reverse-engineering specialist, product analyst, and cross-platform application migration expert.

Your task is to reverse-engineer the provided existing application source code and produce a comprehensive, implementation-ready Project Requirements Document (PRD) suite for rebuilding the application on the specified target platform/stack.

---

### 1. INPUT CONTEXT & SCOPE

- **Source Code Base / Repository**: [INSERT SOURCE REPO PATH OR SUBMODULE HERE, e.g. `cloudstream_ref_android/`]
- **Analyzed Commit / Version**: [INSERT COMMIT SHA / TAG / VERSION HERE]
- **Target Application Stack**: [INSERT TARGET STACK, e.g. Electron + React + TypeScript / Flutter / Web]
- **Target OS / Environments**: [INSERT TARGET PLATFORMS, e.g. Windows, macOS, Linux, iOS, Android]

---

### 2. PRINCIPLES & RULES

1. **Functional Source of Truth**: The existing source code is the primary behavioral source of truth. Do not invent missing features or guess business rules when they can be determined directly from code.
2. **Evidence-Based Documentation**: Every requirement must cite explicit source code evidence (file path + line range).
3. **Migration & Parity Contract**: Explicitly differentiate between:
   - Features directly reproducible.
   - Features requiring desktop/platform-specific adaptations.
   - Features requiring alternative technical implementations while preserving user-visible behavior.
   - Unsupported features requiring documented trade-offs.
4. **Lossless Data Migration**: Specify data portability contracts (export/import formats, preference key maps, identity calculation formulas e.g. Java `String.hashCode()`).
5. **Implementation Strategy Codes**: Assign each feature one of the following codes:
   - **R1**: Reimplement natively for target platform.
   - **R2**: Node.js / Background worker / Native plugin equivalent.
   - **R3**: Browser / Web API equivalent.
   - **R4**: Platform-specific UX preserving identical underlying logic.
   - **R5**: Alternative workflow.
   - **R6**: Unsupported / Excluded with documented reason.

---

### 3. MANDATED PRD DOCUMENT SUITE OUTPUT STRUCTURE

Produce the following 31 documents in the `docs/PRD/` output folder:

| File Name | Title | Key Contents Required |
|---|---|---|
| `00-index.md` | Index & Baseline | Analysis baseline table, top 5 strategic findings shaping cost/risk, full document map. |
| `01-executive-summary.md` | Executive Summary | Vision, business goals, scope matrix, high-level cost/risk, go/no-go criteria. |
| `02-system-architecture.md` | System Architecture | Source architecture as-is, target architecture to-be, module diagrams, IPC/state flow. |
| `03-feature-specifications.md` | Feature Specifications | Every feature formatted using the mandatory 18-field schema (§4 below). |
| `04-utility-specifications.md` | Utility Specifications | Shared helpers (formatters, network interceptors, encryption, loggers, storage wrappers). |
| `05-library-dependencies.md` | Library Dependencies | Full inventory of source dependencies mapped to target platform equivalents. |
| `06-data-models.md` | Data Models | Canonical logical data models, entity relationships, identity hash semantics, serialization schemas. |
| `07-apis-and-contracts.md` | APIs & Contracts | Internal API definitions, external service endpoints, IPC contracts, WebSocket schemas. |
| `08-ui-and-interactions.md` | UI & Interactions | Screen-by-screen breakdown, component tree, layout wireframes, focus/keyboard accessibility. |
| `09-user-workflows.md` | User Workflows | End-to-end user journeys (first launch, primary task loop, offline mode, error recovery). |
| `10-user-personas.md` | User Personas | Personas, target device specs, accessibility needs, usage environments. |
| `11-security-and-compliance.md` | Security & Compliance | Threat model, sandbox isolation, credential storage, open-source license compliance (GPL/MIT). |
| `12-performance-and-limits.md` | Performance & Limits | Cold start budgets, list scroll FPS targets, memory limits, DB dataset scale boundaries. |
| `13-testing-and-qa.md` | Testing & QA | Test plan, unit test coverage targets, migration verification tests, E2E test matrix. |
| `14-deployment-and-ci.md` | Deployment & CI/CD | Packaging, code signing, update channels (auto-updater), CI/CD pipelines. |
| `15-upgrade-and-modernization.md` | Upgrade & Modernization | Legacy code refactoring strategy, technical debt remediation, future roadmap. |
| `16-implementation-plan.md` | Implementation Plan | Phased execution roadmap (Phase 1 MVP to Phase N Polish) with dependency chains. |
| `17-acceptance-criteria.md` | Acceptance Criteria | Measurable, verifiable definition of done per module. |
| `18-technical-reference.md` | Technical Reference | Key catalogs, path resolution rules, custom algorithms, download manager internals. |
| `19-development-history.md` | Development History | Architectural insights derived from git commit history, legacy migrations, past refactors. |
| `20-limitations-and-constraints.md` | Limitations & Constraints | Explicit technical trade-offs, unsupported platform features, edge constraints. |
| `21-open-issues-and-assumptions.md` | Open Issues & Assumptions | Unresolved questions, technical risks requiring spikes, assumptions to validate. |
| `22-contributor-guide.md` | Contributor Guide | Developer setup instructions, build commands, project structure, contribution rules. |
| `23-manifest.json` | Machine-Readable Manifest | JSON index detailing project metadata, document index, headline findings, and feature list. |
| `24-feature-parity-matrix.md` | Feature Parity Matrix | Side-by-side comparison table of Source Feature vs Target Feature vs Strategy Code. |
| `25-data-portability-and-migration.md` | Data Portability | Backup JSON/DB grammar, key-value mapping table, import parsing pipeline. |
| `26-desktop-requirements.md` | Desktop / OS Integration | Native menus, tray icon, window state management, global keyboard shortcuts. |
| `27-plugin-architecture.md` | Plugin & Extension Arch | Extension runtime, sandboxing, dynamic loader, provider API bridges. |
| `28-media-playback-requirements.md` | Media / Core Subsystem | Player engine (Video.js/mpv/hls.js), codec compatibility, subtitle parser, track switcher. |
| `29-platform-compatibility.md` | Platform Compatibility | OS version matrices (Windows 10/11, macOS ARM/x64, Linux glibc/musl). |
| `30-migration-test-cases.md` | Migration Test Cases | Step-by-step test vectors for data import/export verification across edge datasets. |

---

### 4. MANDATORY FEATURE SPECIFICATION SCHEMA

For `03-feature-specifications.md`, every feature entry must contain all 18 fields:

1. **ID & Name**: e.g., `FEAT-PLAY-01 — Custom Subtitle Renderer`
2. **Description**: Functional summary.
3. **Source Code Behavior**: Exact Kotlin/Java/JS logic + file:line ranges.
4. **Target Platform Behavior**: Adapted implementation spec for target stack.
5. **Actors**: Primary roles.
6. **Trigger**: Event initiating feature.
7. **Preconditions**: Required system state.
8. **Main Workflow**: Numbered step-by-step happy path.
9. **Alternative Workflows**: Secondary paths or toggles.
10. **Error Workflows**: Recovery for network/validation errors.
11. **Postconditions**: Resulting state after execution.
12. **Data Affected**: Modified DB tables, storage keys, or state variables.
13. **Dependencies**: Required upstream features.
14. **Platform Differences**: OS or environment variations.
15. **Acceptance Criteria**: Verifiable verification rules.
16. **Priority**: P0 / P1 / P2 / P3.
17. **Implementation Strategy Code**: R1 / R2 / R3 / R4 / R5 / R6.
18. **Evidence Citation**: `file:///path/to/SourceFile.kt#L100-L150`

---

### 5. EXECUTION INSTRUCTIONS

1. Analyze the codebase systematically by inspecting root build files, module structures, data entities, and UI controllers.
2. Draft each document in clean Markdown.
3. Ensure `23-manifest.json` conforms to JSON schema draft 2020-12.
4. Output all documents into the target directory `docs/PRD/`.
```
