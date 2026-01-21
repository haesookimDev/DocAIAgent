import json
from pathlib import Path
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]  # specs/

SCHEMA_MAP = {
    # path prefix -> schema file
    "workflows/": "schemas/workflow/workflow_v1.schema.json",
    "examples/render/layout_plan_example.json": "schemas/layout/layout_plan_v1.schema.json",
    "examples/render/pptx_ops_example.json": "schemas/render/pptx_ops_v1.schema.json",
    "examples/render/render_report_example.json": "schemas/render/render_report_v1.schema.json",
}

def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))

def load_schema(rel: str):
    return load_json(ROOT / rel)

def validate(instance_path: Path, schema_path: str) -> bool:
    schema = load_schema(schema_path)
    validator = Draft202012Validator(schema)
    instance = load_json(instance_path)

    errors = sorted(validator.iter_errors(instance), key=lambda e: e.path)
    if errors:
        print(f"[FAIL] {instance_path.relative_to(ROOT)} against {schema_path}")
        for e in errors[:20]:
            loc = "/".join([str(x) for x in e.path])
            print(f"  - {loc}: {e.message}")
        if len(errors) > 20:
            print(f"  ... {len(errors)-20} more")
        return False

    print(f"[OK] {instance_path.relative_to(ROOT)}")
    return True

def main() -> int:
    ok = True

    # validate workflows/
    workflow_schema = SCHEMA_MAP["workflows/"]
    for wf in sorted((ROOT / "workflows").rglob("*.json")):
        ok = validate(wf, workflow_schema) and ok

    # validate explicit examples
    for rel_instance, rel_schema in SCHEMA_MAP.items():
        if rel_instance.endswith("/"):
            continue
        ok = validate(ROOT / rel_instance, rel_schema) and ok

    return 0 if ok else 1

if __name__ == "__main__":
    raise SystemExit(main())
