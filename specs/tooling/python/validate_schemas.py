import json
from pathlib import Path
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]  # specs/
SCHEMAS_DIR = ROOT / "schemas"

def main() -> int:
    schema_files = sorted(SCHEMAS_DIR.rglob("*.schema.json"))
    if not schema_files:
        print("No schema files found.")
        return 1

    ok = True
    for p in schema_files:
        try:
            schema = json.loads(p.read_text(encoding="utf-8"))
            Draft202012Validator.check_schema(schema)
            print(f"[OK] schema: {p.relative_to(ROOT)}")
        except Exception as e:
            ok = False
            print(f"[FAIL] schema: {p.relative_to(ROOT)} -> {e}")
    return 0 if ok else 1

if __name__ == "__main__":
    raise SystemExit(main())
