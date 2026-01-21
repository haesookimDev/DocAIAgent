# WorkAgent Specs (Single Source of Truth)

This repository contains versioned, language-neutral specifications for:
- JSON Schemas (validation contracts)
- Workflow specs (agent DAGs)
- Layout presets (slot-based deterministic layout)
- Render artifacts (LayoutPlan, PptxOps, RenderReport)
- Examples (validation fixtures)

## Structure
- `schemas/`: JSON Schema (Draft 2020-12)
- `workflows/`: versioned agent workflow specs
- `layout_presets/`: deterministic layout packages
- `examples/`: example JSON instances validated by schemas
- `tooling/`: validation tools (Python) + optional TS type generation (Node)

## Validation (Python)
```bash
python tooling/python/validate_schemas.py
python tooling/python/validate_examples.py
```

## Type Generation (Next.js)
(Optional) Generate TypeScript types from JSON Schemas:
```bash
cd tooling/node
npm install
npm run gen:types
```

## Versioning Rules
- Schemas are versioned by major: `*_v1.schema.json`
- Workflow specs are semantic versions: `workflows/<agent>/<semver>.json`
- Layout packages are versioned folders: `layout_presets/<name>_v1/`

## Notes
- All runtime systems (backend orchestrator, renderer, UI editors) should validate against these schemas in CI.
- Examples serve as fixtures to prevent breaking changes.