import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # specs/
PACKAGE = ROOT / "layout_presets" / "builtin_default_v1" / "package.json"
OUT_DIR = ROOT / "layout_presets" / "builtin_default_v1" / "layouts"

def main():
    pkg = json.loads(PACKAGE.read_text(encoding="utf-8"))
    layouts = pkg.get("layouts", {})
    if not layouts:
        raise RuntimeError("No layouts found in package.json")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    for layout_id, layout_obj in layouts.items():
        out_path = OUT_DIR / f"{layout_id}.json"
        out_path.write_text(json.dumps(layout_obj, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[OK] wrote {out_path.relative_to(ROOT)}")

if __name__ == "__main__":
    main()
