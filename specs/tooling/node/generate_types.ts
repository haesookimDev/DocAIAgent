import { compileFromFile } from "json-schema-to-typescript";
import path from "path";
import { mkdirSync, writeFileSync } from "fs";

const ROOT = path.resolve(__dirname, "../.."); // specs/
const OUT_DIR = path.resolve(ROOT, "../frontend/src/generated/spec-types"); // adjust if needed

const TARGETS: Array<{ schemaRel: string; outFile: string }> = [
  { schemaRel: "schemas/workflow/workflow_v1.schema.json", outFile: "workflow_v1.d.ts" },
  { schemaRel: "schemas/layout/layout_preset_package_v1.schema.json", outFile: "layout_preset_package_v1.d.ts" },
  { schemaRel: "schemas/layout/layout_plan_v1.schema.json", outFile: "layout_plan_v1.d.ts" },
  { schemaRel: "schemas/render/pptx_ops_v1.schema.json", outFile: "pptx_ops_v1.d.ts" },
  { schemaRel: "schemas/render/render_report_v1.schema.json", outFile: "render_report_v1.d.ts" }
];

async function main() {
  mkdirSync(OUT_DIR, { recursive: true });

  for (const t of TARGETS) {
    const schemaPath = path.resolve(ROOT, t.schemaRel);
    const ts = await compileFromFile(schemaPath, {
      bannerComment: `/* AUTO-GENERATED FROM ${t.schemaRel}. DO NOT EDIT. */`,
      style: { singleQuote: true }
    });

    writeFileSync(path.resolve(OUT_DIR, t.outFile), ts, "utf-8");
    console.log(`[OK] Generated ${t.outFile}`);
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
