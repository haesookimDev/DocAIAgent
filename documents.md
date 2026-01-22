
# 1) Platform Definition

## 1.1 Platform Name (Working)

**WorkAgent Platform** — an AI-agent platform specialized for **business documents** (PPTX/DOCX/PDF) with reproducible, auditable generation.

## 1.2 Platform Scope

### In-scope (MVP → V1)

* Upload business files (PDF/DOCX/PPTX/XLSX) and index them for retrieval (RAG).
* Create **AI agent runs** that produce:

  * **PPT deck** (PPTX + preview PDF + thumbnails)
  * **Doc** (DOCX + PDF) (V1)
* “Plan → Approve → Generate → QC → Fix → Render” loop.
* Team/workspace model: org → project → artifacts.
* Template + brand kit support.

### Out-of-scope (initial)

* Real-time collaborative editing inside the product (use exported PPTX/DOCX for editing).
* Full WYSIWYG editor (later).
* Complex BI dashboards (later, via plugins).

## 1.3 Key Platform Concepts

* **Run**: an execution instance of an agent workflow.
* **Step**: a unit of work inside a run (agent/tool/render/quality/approval/system).
* **IR (Intermediate Representation)**: strict JSON spec that is validated and rendered:

  * `SlideSpec v1 (slidespec_v1)`
  * `DocSpec v1 (docspec_v1)`
* **LayoutPlan**: deterministic layout computation output used for QC and fixes.
* **Ops List (PptxOps)**: a renderer command list for reproducible PPT generation.

## 1.4 Non-functional Requirements (NFR)

* **Reproducibility**: same IR + same template/brand should produce consistent output.
* **Auditability**: tool invocations + evidence + policy decisions must be recorded.
* **Safety/Policy**: external web access may be disabled; connectors are permissioned.
* **Quality**: automated checks for overflow/overlap/out-of-bounds; fix loop.
* **Scalability**: queue-based steps; stateless workers; object storage for binaries.

---

# 2) Development Purpose

## 2.1 Primary Goal

Build a platform that enables teams to create **work-grade AI agents** that reliably generate **business documents (PPTX/DOCX)**, using templates and citations, with a deterministic QC/fix loop.

## 2.2 Target Users

* Business teams (product, strategy, sales, marketing)
* Analysts and consultants
* Internal ops teams producing recurring reports

## 2.3 Core Use Cases (MVP)

1. Generate a deck from a prompt + source PDFs:

   * outline approval optional
   * citations included
2. Regenerate selected slides only (partial regeneration).
3. Apply organization brand kit + PPT template.
4. Provide preview + downloadable PPTX.

## 2.4 Success Metrics (MVP)

* % runs completing successfully without manual intervention
* Average # of fix loop iterations per deck
* Text overflow rate (should approach ~0)
* Time-to-first-preview
* User acceptance rate after outline approval step

---

# 3) System Architecture

## 3.1 High-level Architecture (Services)

**Frontend**

* Web app (project workspace, run creation, approval UI, preview & download)

**Backend API**

* Auth + RBAC
* Project/files/templates/brandkits CRUD
* Runs orchestration API + SSE events API

**Orchestrator**

* Executes workflow DAG from `WorkflowSpec`
* Creates/enqueues steps; handles retries/cancellation/state transitions

**Workers**

* Agent Worker (LLM calls): outline, SlideSpec/DocSpec planning, repair, summarization
* Tool Worker (RAG/Connectors): indexing, retrieval
* Render Worker: PPTX/DOCX rendering + preview generation
* Quality Worker: layout QC, compliance checks

**Storage**

* PostgreSQL: metadata, runs, steps, policies, IR versions, audit events
* Object Storage (S3): uploaded files, generated PPTX/DOCX/PDF, thumbnails, layout plans, ops

**Search / Vector**

* pgvector (MVP) or external vector DB (later) for chunk embeddings
* chunk store + evidence references

## 3.2 Data Flow (PPT)

1. User uploads files → extract/index jobs
2. User starts run → `runs` row created
3. Orchestrator executes:

   * retrieve evidence → outline → (approval) → slidespec plan/repair
   * compute layout plan → QC → fix loop → render pptx → finalize artifact version
4. UI subscribes to SSE events for progress/intermediates
5. Artifact is available for download (signed URL)

## 3.3 Run State Machine (Summary)

`created → planning → waiting_approval → executing → rendering → quality_check → completed`
With failures: `failed`, and user cancellation: `cancelled`.

## 3.4 Security & Compliance

* RBAC: org and project memberships
* Policy profiles per project: external web on/off; connector allowlist; PII masking
* Audit events on tool invocation, file reads, artifact downloads

## 3.5 Reliability

* Queue-based processing with step-level retries & timeouts
* Idempotency for run creation and file ingestion
* Run events persisted to DB for replayable streaming

---

# 4) Development Stack

## 4.1 Recommended Stack (Pragmatic MVP)

**Backend API**

* Language: **TypeScript**
* Framework: **NestJS** (or Fastify-based)
* DB: PostgreSQL + pgvector
* Queue: **BullMQ (Redis)** (MVP)

  * Upgrade path: Temporal / Cadence for complex workflows
* Storage: S3-compatible
* Real-time: SSE for run events

**Workers**

* Agent worker: TypeScript (same repo) or Python (if ML tooling preferred)
* Render worker:

  * PPTX: **PptxGenJS** (Node/TS) + template handling utilities
  * DOCX: python-docx or docx templating service (V1)
* Quality: Node/TS

**Frontend**

* React + Next.js
* SSE client for run streams
* Preview viewer (PDF) + thumbnails

**Infra**

* Docker + Kubernetes (or ECS)
* Observability: OpenTelemetry + Prometheus/Grafana + centralized logs

## 4.2 Alternative Stack (if Python-first)

* API: FastAPI
* Queue: Celery + Redis
* PPTX: python-pptx (template fidelity can be harder)
  → still feasible, but Node/PptxGenJS tends to be faster to iterate for layout.

## 4.3 Why this stack

* Single-language (TS) across API + orchestrator + renderer reduces friction.
* BullMQ is easy for MVP and works well with step-based jobs.
* pgvector simplifies MVP without adding new infra.

---

# 5) Detailed Component Definitions (Unit Specs)

Below are the “units” you can hand to a dev team as implementable specs.

---

## 5.1 Identity & Access (Auth/RBAC)

### 5.1.1 Entities

* `orgs`
* `users`
* `org_memberships`
* `projects`
* `project_memberships`

### 5.1.2 Required Features

* JWT/OIDC login
* Org context selection (header `X-Org-Id`)
* Role checks:

  * org_admin: manage org resources
  * project owner/editor/viewer
* Audit on:

  * file read
  * connector access
  * artifact download

### 5.1.3 API Units

* `GET /projects`
* `POST /projects`
* `GET /projects/{id}`

---

## 5.2 File Ingestion & Processing

### 5.2.1 Entities

* `file_assets`
* `file_processing_jobs`
* `document_chunks`
* `chunk_embeddings`
* `evidences`

### 5.2.2 Functional Requirements

* Two-phase upload:

  * initiate → presigned URL
  * complete → enqueue extract/index
* Extraction:

  * pdf text extraction
  * docx text extraction (V1)
* Chunking:

  * chunk size: ~500–1200 chars (config)
  * store metadata: page, section, bbox if available
* Embedding:

  * store vectors per chunk, record model/version

### 5.2.3 API Units

* `POST /projects/{project_id}/files:initiate`
* `POST /projects/{project_id}/files/{file_id}:complete`
* `GET /projects/{project_id}/files`
* `POST /files/{file_id}:index`

### 5.2.4 Worker Jobs (Unit Specs)

* `extract(file_id)`
* `index(file_id)`
* `thumbnail(file_id)` (optional)

---

## 5.3 Templates & Brand Kits

### 5.3.1 Entities

* `templates`
* `brand_kits`

### 5.3.2 Functional Requirements

* Template upload (pptx/docx)
* TemplateAnalyzer (pptx):

  * list layouts
  * placeholder bbox extraction
  * slide size
  * (optional) theme fonts/colors
* Brand tokens:

  * colors, fonts, logo, spacing, constraints

### 5.3.3 API Units

* `POST /templates:initiate`
* `POST /templates/{id}:complete`
* `GET /templates`
* `POST /brandkits`
* `GET /brandkits`
* `GET /brandkits/{id}`

---

## 5.4 Agent Registry & WorkflowSpec

### 5.4.1 Entities

* `agent_packages`
* `agent_package_versions`
* `tool_plugins`

### 5.4.2 Functional Requirements

* Store workflow specs as JSON (versioned)
* Validate WorkflowSpec on publish:

  * step graph integrity
  * step_key uniqueness
  * allowed step types
* Tool plugin registry:

  * input/output schema
  * permission requirements

### 5.4.3 Unit Specs

* `WorkflowSpec v1` (JSON)
* Step fields: `step_key`, `type`, `runner`, `when`, `input`, `output`, `retry_policy`, `timeout_sec`, `on_failure`, `emit`

---

## 5.5 Runs, Steps, Events (Execution Core)

### 5.5.1 Entities

* `runs`
* `run_steps`
* `run_events`
* `artifacts`
* `artifact_versions`

### 5.5.2 Functional Requirements

* `POST /runs` creates run and kicks off orchestration
* Run status transitions follow the state machine
* Step execution:

  * queued → running → succeeded/failed/skipped/cancelled
* SSE:

  * stream `run_events` with `seq` for replay
* Idempotency on run create

### 5.5.3 API Units

* `POST /runs`
* `GET /runs/{run_id}`
* `GET /projects/{project_id}/runs`
* `GET /runs/{run_id}/events` (SSE)
* `POST /runs/{run_id}/cancel`
* `POST /runs/{run_id}/approve`
* `POST /runs/{run_id}/regenerate`

### 5.5.4 Orchestrator Unit Spec

* Inputs:

  * run_id
  * workflow spec
* Responsibilities:

  * evaluate `when`
  * ensure prerequisites succeeded
  * create and enqueue step jobs
  * apply retry policies
  * update run status mapping based on step groups
  * handle cancellation signal
* Output:

  * run_steps updates + run_events emits

---

## 5.6 IR Specs (SlideSpec/DocSpec) & Schema Validation

### 5.6.1 Specs

* `SlideSpec v1 (slidespec_v1)` — validated JSON
* `DocSpec v1 (docspec_v1)` — validated JSON
* Repair specs:

  * schema error-driven repair prompt
* Patch specs:

  * `slidespec_patch_v1` operations list

### 5.6.2 Functional Requirements

* Hard validation (JSON Schema) before rendering
* Stable IDs (`s1`, `s1_e1`) for partial regeneration
* Citations:

  * slide-level and element-level references

---

## 5.7 Retrieval (RAG) & Evidence

### 5.7.1 Functional Requirements

* Query formulation from prompt + outline
* Vector search top-k
* Evidence object includes:

  * file_id, chunk_id, title, locator(page), quote
* Ensure evidence is stored and referencable in IR citations

### 5.7.2 Tool Plugin Unit

* `tool.rag.retrieve`
* Input: prompt, file_ids, top_k
* Output: `evidence_list_v1`

---

## 5.8 Layout Engine & QC/Fix Loop (Key Differentiator)

### 5.8.1 LayoutPresetPackage v1

* Built-in layout definitions:

  * `title_center`, `section_header`, `one_column`, `two_column`,
  * `chart_focus`, `table_focus`, `quote_center`, `closing`
* Slot specs:

  * bbox, padding, flow, accept rules, overflow policy, z_base

### 5.8.2 LayoutPlan v1

* Deterministic result of layout computation:

  * element bbox, resolved style, text metrics
  * slide diagnostics: overlap/out_of_bounds
  * summary counts

### 5.8.3 QC v1

* Checks:

  * overflow
  * overlap ratio threshold
  * out_of_bounds
  * min_font violations
  * citations overflow in footer band
* Output: `layout_qc_v1` issues list

### 5.8.4 FixEngine v1

* Deterministic patch generation:

  1. shrink font
  2. recompute wrap
  3. adjust spacing
  4. change layout
  5. split slide (bullets/table)
  6. summarize (LLM) only as last resort
* Output:

  * `slidespec_patch_v1` + updated SlideSpec

### 5.8.5 Workflow Steps

* `render_plan` → compute LayoutPlan
* `quality_check_layout_plan` → QC
* `fix_layout` → patch + updated IR
* loop max: `defaults.max_fix_loops`

---

## 5.9 Renderer Internals (PPTX)

### 5.9.1 PptxOps v1 (Intermediate Rendering Commands)

* `addText`, `addImage`, `addChart`, `addTable`, `addShape`, `addNotes`
* Each op includes:

  * element_id
  * bbox_in
  * style (resolved)
  * z_index
* Stored to S3 for debug and determinism

### 5.9.2 RenderReport v1

* Missing assets list
* Warnings (e.g., chart labels truncated)
* Timing metrics
* QC summary

### 5.9.3 Render Worker Unit Spec

Inputs:

* SlideSpec v1
* Template + Brand kit
* Resolved assets
  Outputs:
* pptx
* preview pdf
* thumbnails
* layout_plan.json (optional if already computed)
* ops.json
* render_report.json

---

## 5.10 Artifacts & Versioning

### 5.10.1 Functional Requirements

* Artifact created per run (or attached to existing artifact for regen)
* `artifact_versions` store:

  * IR snapshot
  * template_id/brand_kit_id
  * pptx/docx/pdf storage keys
  * checksum
* “draft/published/archived” workflow (MVP can default to draft)

### 5.10.2 API Units

* `GET /projects/{project_id}/artifacts`
* `GET /artifacts/{artifact_id}`
* `GET /artifacts/{artifact_id}/versions`
* `POST /artifacts/{artifact_id}/versions/{version_id}:download` (signed URL)

---

## 5.11 Observability & Operations (Production Readiness)

### 5.11.1 Required Telemetry

* Per step:

  * latency, token usage (agent steps), retries, failure codes
* Per run:

  * total duration, fix loop count, QC issue counts

### 5.11.2 Operational Units

* Dead-letter queue for failed steps
* Admin view for runs/steps/events
* Replay tools (re-run step with same inputs)

---

# Deliverable Breakdown (How to Implement in Sprints)

## Sprint 1: Execution Skeleton + One Slide Render

* DB tables: runs/run_steps/run_events, templates, brandkits, file_assets
* API: create run, get run, SSE events
* Worker: render a single `title_center` slide from a minimal SlideSpec
* Save: pptx + ops.json

## Sprint 2: SlideSpec Planning + Schema Validation + Template/Brand

* agent step for SlideSpec generation (basic)
* JSON schema validation + repair step
* template upload + template analyzer skeleton

## Sprint 3: LayoutPlan + QC + Fix Loop

* layout presets
* layout plan computation
* QC + deterministic fix patches
* loop → render

## Sprint 4: RAG + Citations + Partial Regeneration

* chunking + embeddings + evidence retrieval
* citations in SlideSpec + footer rendering
* regen slides 2–3 only