---
name: update-doc
description: Generate and iteratively improve project documentation with architecture, features, limits, and operational concerns
tags: [documentation, architecture, production, onboarding]
---

# Update Doc Skill

This skill generates high-level project documentation that gives you confidence in what you built—architecture, features, limits, and risks—without implementation minutiae.

## When to use

Invoke with `/update-doc` in any project you're building. The skill will:
1. Ask for project context
2. Generate a markdown doc structured for prod confidence
3. Request feedback on what worked/was bloat
4. Evolve the template based on feedback

## Rule: update in place, don't regenerate from scratch

A project usually already has its own docs: a root `README.md` for the
whole-project, high-level design, and a separate `README.md` per part (e.g.
`frontend/README.md`, `backend/README.md`) for that part's detail. Before
writing anything:

1. **Find existing docs first.** Look for a root-level architecture/design
   doc — `ARCHITECTURE.md` if the project has one (a plain root `README.md`
   often plays this role in projects that haven't split it out yet) — and
   any README under each top-level part of the project (frontend, backend,
   services, etc.). If both a root `README.md` and a root `ARCHITECTURE.md`
   exist, `ARCHITECTURE.md` is the high-level-design doc and `README.md` is
   the short onboarding/quickstart doc — don't write architecture content
   into the README.
2. **Scope to the current change.** Look at what actually changed (recent
   diff, new/modified files, new commits) and figure out which existing
   doc(s) that change belongs to — the root architecture doc if it changes
   cross-project architecture or how the parts fit together, a part's own
   README if it's local to that part (a new endpoint, a new component, a new
   env var, a new dependency, etc.). A change that only affects local
   run/quickstart steps belongs in the root README instead.
3. **Edit only the relevant doc(s), only the relevant section(s).** Do not
   regenerate the whole file and do not rewrite sections the change didn't
   touch. Treat the Doc Template below as the section structure to slot
   updates into where it already exists in a doc, not as a full document to
   produce every run.
4. **Only fall back to generating a fresh doc from the full template** when
   no relevant existing doc is found for the part being changed (e.g. a new
   frontend/backend/service directory with no README yet), or when the user
   explicitly asks for a full regeneration.
5. State which file(s) you updated and why you picked them, so the user can
   confirm the scoping was right.

## Doc Template (evolves over time)

Each generated doc includes:

- **Architecture**: Diagram or textual description of layers, data flow, external dependencies
- **Features Matrix**: Feature name, why it exists, config, data flow through layers, limits/risks
- **Operational Concerns**: Scaling bottlenecks, cost drivers, monitoring alerts, security risks
- **Known Limits**: What breaks under load, graceful degradation gaps, acceptable tech debt
- **Key Decisions**: Why this architecture, not another (ADR format)

## Feedback loop

After doc is generated:
1. User rates each section: helpful / bloat / missing
2. Feedback stored in global memory
3. Next project uses refined template based on patterns
4. Skill shows what changed ("added Cost breakdown based on feedback")

## Memory reference

Global feedback tracked in: `/Users/jvxoq/.claude/doc-feedback.md`

This path is fixed and project-independent — it lives outside any project's `projects/<project>/memory/` folder, so it's the same file no matter which project you run `/update-doc` from. It's read only when this skill runs, not loaded into every session's context, so it carries no ongoing context/performance cost.

This file stores:
- Which sections users found useful across all projects
- Which sections were consistently bloated
- New sections users requested
- Section order preferences

---

**Usage**: Run `/update-doc` in your project directory and follow the prompts.
