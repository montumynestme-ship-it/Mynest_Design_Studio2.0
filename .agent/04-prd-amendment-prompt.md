# Prompt 04: PRD Feature Delta & Amendment Generator

> **Usage:** Copy and paste this prompt to an AI Agent when you have an existing baseline PRD document and need to write a targeted PRD amendment for a new feature, scope addition, or architectural change.

---

```markdown
You are a Lead Software Architect and Senior Product Manager.

Your task is to analyze a new feature request or gap analysis report against an existing baseline PRD and write a formal **PRD Amendment Document** (modeled after `docs_expense_manager/*_prd_amendment.md`).

---

### 1. INPUT CONTEXT

- **Baseline PRD Document**: [INSERT BASELINE PRD FILE PATH, e.g. `docs_expense_manager/2026-07-18 PRD_Expense_Manager.md`]
- **New Feature / Scope Delta**: [INSERT NEW FEATURE TITLE & DESCRIPTION, e.g. Budget Configuration (Monthly & Annual)]
- **Target Release / Version**: [INSERT TARGET VERSION, e.g. v1.1.0 Amendment]

---

### 2. PRINCIPLES & GOALS

1. **Non-Destructive Extension**: Preserve baseline PRD definitions while explicitly extending or overriding impacted sections.
2. **Gap Summary**: Explicitly enumerate what was missing in the baseline PRD and why this amendment is necessary.
3. **Delta Data Models**: Provide explicit database schema migration scripts (`ALTER TABLE`, new tables, new indexes).
4. **New Screen & Flow Specifications**: Detail new UI mockups, interaction changes, and navigation entry points.

---

### 3. AMENDMENT DOCUMENT STRUCTURE

Produce a single amendment file (`YYYY-MM-DD <feature_name>_prd_amendment.md`) containing:

```markdown
# PRD Amendment: <Feature Name>

> [!IMPORTANT]
> This document details all additions and modifications to the baseline PRD (`<BaselinePRDFilename>`) to cover **<Feature Name>**. All changes are scoped to specific sections that need updating.

---

## 1. Summary of Gaps Addressed
- List of specific gaps or missing capabilities in the baseline PRD.

## 2. Updated & New Functional Requirements
- List of new functional requirements (`FR-<DOMAIN>-NEW-01` etc.) adhering to the 18-field specification schema.

## 3. Screen Breakdown & UI Flow Additions
- New screens (`S-NEW-XX`) layout breakdown, components, visual hierarchy.
- Navigation updates (how to reach new screens from existing navigation entries).

## 4. Data Model & Database Schema Amendment
- DDL additions, new table definitions, migration SQL scripts.

## 5. Business Rules & Logic Updates
- Updated calculation rules, state machine updates, validation rules.

## 6. Acceptance Criteria Delta
- Verifiable acceptance criteria for the amended functionality.
```

---

### 4. EXECUTION INSTRUCTIONS

1. Compare new feature requirement against existing baseline PRD.
2. Identify all affected sections (DB schemas, screens, navigation, business rules).
3. Draft amendment markdown file and place in documentation directory.
```
