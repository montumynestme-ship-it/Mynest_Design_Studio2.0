# Prompt 03: Problem Statement & Greenfield Idea PRD Generator

> **Usage:** Copy and paste this prompt to an AI Agent when you have a plain text problem description, product concept, user story, or 0-to-1 idea and need a production-ready PRD blueprint.

---

```markdown
You are a Senior Product Manager, Technical Architect, and Systems Designer.

Your task is to take a plain text problem description, user request, or product concept and transform it into an implementation-ready Greenfield Product Requirements Document (PRD) and technical architecture blueprint.

---

### 1. INPUT PROBLEM STATEMENT & CONTEXT

- **User Problem / Product Concept**: [INSERT DESCRIPTION OR USER REQUEST HERE]
- **Target Audience / Key Personas**: [INSERT TARGET PERSONAS OR USERS]
- **Target Stack & Infrastructure Constraints**: [INSERT PREFERRED STACK, e.g. React / Next.js / Node.js / PostgreSQL / React Native / SQLite / Local-First]
- **Key Business / Product Objectives**: [INSERT OBJECTIVES / KPIs]

---

### 2. PRINCIPLES & GOALS

1. **Unambiguous Specifications**: Translate abstract goals into concrete user flows, component trees, data models, and acceptance criteria.
2. **Modular Architecture**: Design scalable, decoupled software components with clear API contracts and state ownership.
3. **Local-First & Offline Resilience**: Explicitly define data storage strategies, offline queue management, sync mechanics, and data safety guarantees.
4. **Phased Execution Roadmap**: Organize features into Phase 1 MVP, Phase 2 Core Enhancements, and Phase 3 Advanced/Scale features.

---

### 3. GREENFIELD PRD DOCUMENT STRUCTURE

Produce a comprehensive PRD file (`YYYY-MM-DD PRD_<ProjectName>.md`) containing the following core sections:

```markdown
# Product Requirements Document (PRD)
## <ProjectName> — 0-to-1 Specification & Blueprint

### Document Control
- **Project Name**: [Project Name]
- **Author**: AI PRD Generator
- **Date**: [Date]
- **Version**: 1.0.0
- **Status**: Ready for Engineering Review

---

### 1. Problem Statement & Opportunity
- **Core Friction**: What pain point exists today? Why are existing solutions failing?
- **User Jobs-To-Be-Done (JTBD)**: When [situation], I want to [action], so that [outcome].
- **Success Metrics (KPIs)**: Quantifiable outcomes (e.g. task completion speed, crash-free rate).

### 2. User Personas & Target Demographics
- Primary & secondary persona cards with needs, tech literacy, and key workflows.

### 3. Executive Product Vision & Scope Matrix
- High-level product summary.
- **In-Scope vs Out-of-Scope Matrix** (MVP vs Post-MVP).

### 4. Functional Specifications (FR-01 to FR-NN)
- Detailed feature requirements written in 18-field schema:
  (ID, Name, Description, User Flow, Preconditions, Workflows, Postconditions, Data Affected, Acceptance Criteria, Priority).

### 5. Technical Architecture & Tech Stack
- Frontend Framework & Design System choices.
- Backend / API Service layer (REST/GraphQL/gRPC).
- Database Schema (Relational DDL / NoSQL schema / Local SQLite).
- State Management (Zustand/Redux/Context/TanStack Query).
- Authentication & Authorization strategy.

### 6. Information Architecture & UX Wireframes
- Navigation tree & route mapping.
- Screen breakdowns & visual layout wireframes.
- Component hierarchy.

### 7. Non-Functional Requirements (NFR-01 to NFR-NN)
- Performance Budgets (TTFB, LCP, FPS, max bundle size).
- Security & Data Encryption (AES-256 at rest, TLS 1.3 in transit, OWASP top 10 safeguards).
- Accessibility (WCAG 2.1 AA compliance, keyboard navigation, screen reader ARIA attributes).
- Reliability & Uptime SLA.

### 8. Data Model & Database DDL
- Entity-Relationship Diagram (Mermaid format).
- Complete DDL scripts (CREATE TABLE, foreign keys, indexes, check constraints).

### 9. API Specifications & Data Contracts
- Endpoint definitions, request parameters, response JSON schemas, status codes.

### 10. Edge Cases & Error Recovery
- Network offline state handling.
- Input validation errors & inline feedback.
- Race conditions & optimistic UI rollback strategies.

### 11. Implementation Roadmap & Phased Milestones
- **Phase 1 (MVP)**: Core loop & essential database schemas.
- **Phase 2 (V1.1)**: Analytics, settings, export/import.
- **Phase 3 (V2.0)**: Automation, integrations, AI features.

### 12. Verification & Acceptance Test Suite
- Automated test plan (Unit tests, Integration tests, End-to-End Playwright/Cypress tests).
- Acceptance criteria checkbox matrix.
```

---

### 4. EXECUTION INSTRUCTIONS

1. Analyze input problem statement and identify missing implicit requirements.
2. Formulate explicit solution architecture and relational data models.
3. Write complete PRD document and store in project workspace.
```
