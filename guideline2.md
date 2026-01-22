
# 1) Postgres 스키마 초안 (MVP + 확장 고려)

## 1.1 설계 원칙

* **멀티테넌시:** 거의 모든 테이블에 `org_id` 포함(엔터프라이즈 확장 시 RLS 적용 가능)
* **Run 중심:** 생성 과정(계획/도구 호출/중간산출물/최종 산출물)을 전부 `runs/run_steps/run_events`에 기록
* **바이너리/대용량은 Object Storage(S3)에 저장**하고 DB에는 메타데이터+키만 저장
* **유연성:** 중간산출물/IR/툴입출력은 `jsonb`로 저장(스키마 버전과 함께)
* **추적/감사:** `audit_events`로 “누가/언제/무엇을/어떤 정책결정으로” 했는지 남김

---

## 1.2 확장/필수 확장 (Postgres extensions)

```sql
-- UUID 생성
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- pgvector를 쓰면(권장)
CREATE EXTENSION IF NOT EXISTS vector;

-- 텍스트 검색이 필요하면(선택)
CREATE EXTENSION IF NOT EXISTS pg_trgm;
```

---

## 1.3 공통 컬럼/컨벤션

* PK: `id uuid primary key default gen_random_uuid()`
* 시간: `created_at`, `updated_at`, (소프트삭제) `deleted_at`
* 낙관적 락(선택): `lock_version int default 0`
* `jsonb` 저장 시: `schema_version` 또는 `ir_version` 같이 기록

---

## 1.4 인증/조직/권한 (최소 RBAC)

### orgs

```sql
CREATE TABLE orgs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL,
  slug text UNIQUE,
  plan text NOT NULL DEFAULT 'free',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  deleted_at timestamptz
);
```

### users

```sql
CREATE TABLE users (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email citext UNIQUE NOT NULL,
  display_name text,
  picture_url text,
  last_login_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  deleted_at timestamptz
);
```

### org_memberships (Org 단위 역할)

```sql
CREATE TABLE org_memberships (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES orgs(id),
  user_id uuid NOT NULL REFERENCES users(id),
  role text NOT NULL CHECK (role IN ('org_admin','member','billing_admin','viewer')),
  status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','invited','suspended')),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(org_id, user_id)
);
CREATE INDEX org_memberships_org_id_idx ON org_memberships(org_id);
```

> 확장: Project 단위 RBAC가 필요하면 `project_memberships` 추가(아래에 포함).

---

## 1.5 Workspace: 프로젝트/파일/템플릿

### projects

```sql
CREATE TABLE projects (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES orgs(id),
  name text NOT NULL,
  description text,
  policy_profile_id uuid, -- 정책 묶음(아래 policy_profiles 참조)
  created_by uuid REFERENCES users(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  deleted_at timestamptz,
  UNIQUE(org_id, name)
);
CREATE INDEX projects_org_id_idx ON projects(org_id);
```

### project_memberships (Project 단위 역할)

```sql
CREATE TABLE project_memberships (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES orgs(id),
  project_id uuid NOT NULL REFERENCES projects(id),
  user_id uuid NOT NULL REFERENCES users(id),
  role text NOT NULL CHECK (role IN ('owner','editor','viewer')),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(project_id, user_id)
);
CREATE INDEX project_memberships_project_idx ON project_memberships(project_id);
```

### file_assets (업로드 파일 메타)

```sql
CREATE TABLE file_assets (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES orgs(id),
  project_id uuid NOT NULL REFERENCES projects(id),

  -- 원본 파일
  filename text NOT NULL,
  content_type text NOT NULL,
  byte_size bigint NOT NULL,
  sha256 text NOT NULL,               -- 중복 감지/무결성
  storage_key text NOT NULL,          -- S3 key
  storage_bucket text,                -- 멀티버킷일 때

  -- 분류/태그
  source_type text NOT NULL DEFAULT 'upload' CHECK (source_type IN ('upload','connector','generated')),
  connector_ref jsonb,                -- ex) {provider:"gdrive", fileId:"..."}
  tags text[],

  uploaded_by uuid REFERENCES users(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  deleted_at timestamptz,

  UNIQUE(org_id, sha256)              -- 조직 내 중복 방지(원하면 project scope로 변경)
);
CREATE INDEX file_assets_project_idx ON file_assets(project_id);
CREATE INDEX file_assets_org_id_idx ON file_assets(org_id);
```

### file_processing_jobs (추출/인덱싱 상태)

```sql
CREATE TABLE file_processing_jobs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES orgs(id),
  file_id uuid NOT NULL REFERENCES file_assets(id),

  status text NOT NULL CHECK (status IN ('queued','running','completed','failed')),
  job_type text NOT NULL CHECK (job_type IN ('extract','index','thumbnail')),
  attempt int NOT NULL DEFAULT 0,
  error_code text,
  error_message text,
  started_at timestamptz,
  ended_at timestamptz,

  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),

  UNIQUE(file_id, job_type)
);
CREATE INDEX file_processing_jobs_file_idx ON file_processing_jobs(file_id);
```

---

## 1.6 템플릿/브랜드 킷

### templates (PPTX/DOCX 템플릿)

```sql
CREATE TABLE templates (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES orgs(id),
  name text NOT NULL,
  template_type text NOT NULL CHECK (template_type IN ('pptx','docx')),
  storage_key text NOT NULL,
  byte_size bigint NOT NULL,
  sha256 text NOT NULL,
  extracted_theme jsonb, -- 템플릿에서 뽑은 폰트/컬러/레이아웃 메타(초기엔 비워도 됨)
  created_by uuid REFERENCES users(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  deleted_at timestamptz,
  UNIQUE(org_id, name)
);
CREATE INDEX templates_org_idx ON templates(org_id);
```

### brand_kits (브랜드 토큰)

```sql
CREATE TABLE brand_kits (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES orgs(id),
  name text NOT NULL,
  tokens jsonb NOT NULL,     -- {colors:{...}, fonts:{...}, logo:{...}, spacing:{...}}
  rules jsonb,               -- 제약(예: 로고 위치 고정, 특정 폰트만)
  created_by uuid REFERENCES users(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  deleted_at timestamptz,
  UNIQUE(org_id, name)
);
CREATE INDEX brand_kits_org_idx ON brand_kits(org_id);
```

---

## 1.7 Agent 패키지/툴 플러그인 (플랫폼화 대비)

### agent_packages / agent_package_versions

```sql
CREATE TABLE agent_packages (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES orgs(id),
  key text NOT NULL,                    -- e.g. "slides.deck_builder"
  display_name text NOT NULL,
  description text,
  created_by uuid REFERENCES users(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  deleted_at timestamptz,
  UNIQUE(org_id, key)
);

CREATE TABLE agent_package_versions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES orgs(id),
  agent_package_id uuid NOT NULL REFERENCES agent_packages(id),
  version text NOT NULL,                -- semver
  spec jsonb NOT NULL,                  -- workflow, tools, input/output schema refs
  is_published boolean NOT NULL DEFAULT false,
  created_by uuid REFERENCES users(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(agent_package_id, version)
);
CREATE INDEX agent_package_versions_pkg_idx ON agent_package_versions(agent_package_id);
```

### tool_plugins (레지스트리)

```sql
CREATE TABLE tool_plugins (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES orgs(id),
  key text NOT NULL,                 -- e.g. "connector.gdrive.read"
  display_name text NOT NULL,
  category text NOT NULL DEFAULT 'internal',
  schema jsonb NOT NULL,             -- input/output schema + permissions
  runtime text NOT NULL DEFAULT 'worker', -- worker/sandbox/remote
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  deleted_at timestamptz,
  UNIQUE(org_id, key)
);
```

---

## 1.8 Run / Step / Event / Artifact (핵심)

### runs

```sql
CREATE TABLE runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES orgs(id),
  project_id uuid NOT NULL REFERENCES projects(id),
  created_by uuid REFERENCES users(id),

  agent_package_version_id uuid REFERENCES agent_package_versions(id),

  status text NOT NULL CHECK (status IN (
    'created','planning','waiting_approval','executing',
    'rendering','quality_check','completed',
    'failed','cancelled'
  )),
  progress numeric(5,2) NOT NULL DEFAULT 0.0, -- 0~100
  title text,                                 -- UI 표시용
  input_json jsonb NOT NULL,                  -- prompt, files, template_id, options...
  policy_snapshot jsonb,                      -- 실행 시점 정책 스냅샷
  idempotency_key text,                       -- 중복 요청 방지
  cancel_requested boolean NOT NULL DEFAULT false,

  parent_run_id uuid REFERENCES runs(id),     -- 부분 재생성 lineage
  lineage jsonb,                              -- {artifact_version_id, slide_ids, ...}

  error_code text,
  error_message text,

  started_at timestamptz,
  completed_at timestamptz,

  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),

  UNIQUE(org_id, created_by, idempotency_key)
);
CREATE INDEX runs_project_idx ON runs(project_id);
CREATE INDEX runs_status_idx ON runs(status);
```

### run_steps

```sql
CREATE TABLE run_steps (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES orgs(id),
  run_id uuid NOT NULL REFERENCES runs(id),

  step_key text NOT NULL, -- e.g. "retrieve", "outline", "render_pptx"
  step_type text NOT NULL CHECK (step_type IN (
    'tool','agent','system','approval','render','quality'
  )),
  status text NOT NULL CHECK (status IN (
    'queued','running','succeeded','failed','skipped','cancelled','waiting_approval'
  )),
  attempt int NOT NULL DEFAULT 0,

  -- 재현/디버깅
  input_json jsonb,
  output_json jsonb,
  metrics_json jsonb,     -- tokens, cost, latency, model, etc.
  error_code text,
  error_message text,

  started_at timestamptz,
  ended_at timestamptz,

  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX run_steps_run_idx ON run_steps(run_id);
CREATE INDEX run_steps_key_idx ON run_steps(run_id, step_key);
```

### run_events (SSE/WebSocket 스트리밍용)

```sql
CREATE TABLE run_events (
  id bigserial PRIMARY KEY,
  org_id uuid NOT NULL REFERENCES orgs(id),
  run_id uuid NOT NULL REFERENCES runs(id),
  seq bigint NOT NULL,              -- run 내 순번(서버가 증가)
  event_type text NOT NULL,         -- "log","progress","intermediate","error"
  payload jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(run_id, seq)
);
CREATE INDEX run_events_run_idx ON run_events(run_id, seq);
```

### artifacts / artifact_versions

```sql
CREATE TABLE artifacts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES orgs(id),
  project_id uuid NOT NULL REFERENCES projects(id),
  artifact_type text NOT NULL CHECK (artifact_type IN ('ppt_deck','doc','other')),
  name text,
  created_by uuid REFERENCES users(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE artifact_versions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES orgs(id),
  artifact_id uuid NOT NULL REFERENCES artifacts(id),
  run_id uuid REFERENCES runs(id),            -- 어떤 run이 만들었는지

  version int NOT NULL,
  status text NOT NULL CHECK (status IN ('draft','published','archived')),
  ir_type text NOT NULL CHECK (ir_type IN ('slidespec_v1','docspec_v1')),
  ir_json jsonb NOT NULL,                     -- 최종 IR 스냅샷(렌더 전/후 동일하게)
  template_id uuid REFERENCES templates(id),
  brand_kit_id uuid REFERENCES brand_kits(id),

  -- 생성물 파일
  pptx_storage_key text,
  docx_storage_key text,
  pdf_storage_key text,
  preview_storage_key text,                   -- 썸네일/프리뷰

  checksum text,
  created_at timestamptz NOT NULL DEFAULT now(),
  created_by uuid REFERENCES users(id),

  UNIQUE(artifact_id, version)
);
CREATE INDEX artifact_versions_artifact_idx ON artifact_versions(artifact_id, version DESC);
```

> 확장(권장): “슬라이드 단위 부분 재생성”을 깔끔히 하려면 `artifact_parts`(slide_id별 IR/렌더 결과) 테이블을 추가해, 변경된 슬라이드만 교체 후 전체 덱 재패키징 가능하게 합니다.

---

## 1.9 RAG / Evidence / Citation

### document_chunks (텍스트 조각)

```sql
CREATE TABLE document_chunks (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES orgs(id),
  project_id uuid NOT NULL REFERENCES projects(id),
  file_id uuid NOT NULL REFERENCES file_assets(id),

  chunk_index int NOT NULL,
  text text NOT NULL,
  metadata jsonb,        -- {page:3, section:"...", bbox:..., table:...}
  created_at timestamptz NOT NULL DEFAULT now(),

  UNIQUE(file_id, chunk_index)
);
CREATE INDEX document_chunks_file_idx ON document_chunks(file_id);
```

### chunk_embeddings (벡터)

```sql
-- embedding_dim은 시스템 설정으로 고정(예: 1536). MVP는 고정이 가장 단순합니다.
CREATE TABLE chunk_embeddings (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES orgs(id),
  chunk_id uuid NOT NULL REFERENCES document_chunks(id) ON DELETE CASCADE,
  embedding vector(1536) NOT NULL,
  model text NOT NULL,             -- 임베딩 모델명/버전
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(chunk_id, model)
);

-- 검색 인덱스 (데이터량/쿼리 패턴 따라 ivfflat/hnsw 선택)
-- ivfflat 예시:
CREATE INDEX chunk_embeddings_ivfflat_idx
ON chunk_embeddings USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);
```

### evidences (근거 스냅샷)

```sql
CREATE TABLE evidences (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES orgs(id),
  project_id uuid NOT NULL REFERENCES projects(id),
  file_id uuid REFERENCES file_assets(id),
  chunk_id uuid REFERENCES document_chunks(id),

  -- citation에 직접 쓰기 좋은 형태로 스냅샷
  quote text,                 -- 짧은 인용(필요 시)
  locator jsonb,              -- {page:3, start:..., end:...}
  url text,                   -- 외부 링크 근거도 가능
  title text,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX evidences_project_idx ON evidences(project_id);
```

---

## 1.10 정책/감사

### policy_profiles (프로젝트 정책 묶음)

```sql
CREATE TABLE policy_profiles (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES orgs(id),
  name text NOT NULL,
  rules jsonb NOT NULL, -- {external_web:false, allowed_connectors:[...], pii_masking:true, ...}
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(org_id, name)
);
```

### audit_events

```sql
CREATE TABLE audit_events (
  id bigserial PRIMARY KEY,
  org_id uuid NOT NULL REFERENCES orgs(id),
  project_id uuid REFERENCES projects(id),
  user_id uuid REFERENCES users(id),
  run_id uuid REFERENCES runs(id),

  action text NOT NULL,          -- "file.read", "tool.invoke", "artifact.download"...
  target_type text,              -- "file","run","artifact","template"...
  target_id uuid,
  decision text,                 -- "allow","deny"
  reason text,
  ip inet,
  user_agent text,
  payload jsonb,                 -- 추가 맥락(도메인, tool args 해시 등)
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX audit_events_org_time_idx ON audit_events(org_id, created_at DESC);
```

---

## 1.11 MVP에서 생략 가능하지만 “곧 필요해지는” 테이블

* `connector_accounts` (OAuth 토큰/연결 상태)
* `quotas_usage` (토큰/렌더링/스토리지 사용량)
* `eval_runs` / `eval_metrics` (품질 회귀테스트)
* `artifact_comments` (검수 코멘트/승인 이력)

---

# 2) Run 상태머신 상세 (단계/재시도/승인/취소/부분 재생성)

## 2.1 Run 상태 정의

### Run.status

* `created`: run 레코드 생성됨(아직 워크플로우 시작 전)
* `planning`: 개요/계획/IR 초안 생성 단계(대개 LLM)
* `waiting_approval`: 사용자 승인이 필요한 게이트
* `executing`: 리서치/도구 실행/RAG retrieval 등 수행
* `rendering`: PPTX/DOCX 생성, 프리뷰 생성 등
* `quality_check`: 레이아웃/정책/출처 검사 및 fix 루프
* `completed`: 성공적으로 artifact_version 생성됨
* `failed`: 회복 불가능한 실패(또는 재시도 한도 초과)
* `cancelled`: 사용자가 취소

### Run의 “취소 요청”

* `cancel_requested=true`로 표시(즉시 `cancelled`로 바꾸지 않음)
* 워커는 **스텝 경계** 또는 **툴 호출 전**에 취소 플래그를 확인하고 안전하게 중단

---

## 2.2 Step(단계) 카탈로그 (슬라이드 생성 예시)

각 Step은 `run_steps.step_key`로 기록하고, 아래 표준을 갖습니다.

| step_key               | step_type    | 목적                        | 성공 산출물             |
| ---------------------- | ------------ | ------------------------- | ------------------ |
| `ingest_inputs`        | system       | 입력 검증(파일/템플릿/정책 snapshot) | validated_inputs   |
| `index_if_needed`      | system       | 파일 인덱싱 필요 시 enqueue       | indexing job ref   |
| `retrieve_evidence`    | tool/system  | RAG 검색으로 근거 수집            | evidence list      |
| `outline`              | agent        | 목차/스토리라인 생성               | outline JSON       |
| `approval_outline`     | approval     | 사용자 승인 대기                 | approved outline   |
| `plan_slidespec`       | agent        | SlideSpec(IR) 생성          | SlideSpec v1       |
| `design_layout`        | agent/system | 레이아웃 힌트 강화(옵션)            | enriched SlideSpec |
| `render_pptx`          | render       | PPTX 생성 + 썸네일             | storage keys       |
| `quality_check_layout` | quality      | overflow/overlap 검사       | qc report          |
| `fix_layout`           | system/agent | 자동 수정 루프                  | updated SlideSpec  |
| `finalize`             | system       | artifact_version 생성/게시    | version id         |

> Docs는 `plan_docspec`, `render_docx`, `render_pdf`로 바뀌는 정도입니다.

---

## 2.3 상태 전이(정식 규칙)

### 핵심 전이

* `created → planning` : 워크플로우 시작
* `planning → waiting_approval` : 승인 게이트가 있으면
* `waiting_approval → executing` : 승인 완료 이벤트 수신 시
* `planning/executing → rendering` : IR 확정 후
* `rendering → quality_check`
* `quality_check → rendering` : fix 후 재렌더 필요 시
* `quality_check → completed`
* 어디서든 오류 발생 시:

  * 재시도 가능하면 같은 상태 유지(스텝만 attempt++)
  * 재시도 불가/한도 초과면 `failed`
* 사용자가 취소하면:

  * 안전 지점에서 `cancelled`

### 승인 이벤트 처리

* 승인 UI 액션 → `POST /runs/{id}/approve` 같은 엔드포인트
* 서버는:

  * `run_steps`의 `approval_outline`를 `succeeded`로 업데이트
  * `runs.status`를 `executing`으로 전이
  * 다음 스텝 enqueue

---

## 2.4 재시도 정책(현실적인 기준)

스텝마다 재시도와 타임아웃을 **명확히 분리**합니다.

### 권장 기본값

* LLM 호출(agent step):

  * timeout: 60~120s
  * retry: 2~3회, exponential backoff(예: 2s, 8s, 20s)
  * 실패 유형 구분: rate limit/timeout만 재시도, schema validation 실패는 “수정 루프”(다른 처리)로
* 외부 커넥터(tool step):

  * timeout: 30~60s
  * retry: 2회(일시 오류만)
* 렌더링(render step):

  * timeout: 120~300s(덱 규모에 따라)
  * retry: 1회(환경 문제일 때만)
* quality check:

  * timeout: 10~30s
  * retry: 보통 불필요

### 스키마 검증 실패 처리(중요)

* `SlideSpec`/`DocSpec`가 JSON Schema를 통과하지 못하면,

  * 단순 재시도보다 “**Repair Step**”로 분리하는 것이 안정적
  * 예: `plan_slidespec` 실패 → `repair_slidespec` 실행(에러 메시지와 함께 재생성)

---

## 2.5 Idempotency(중복 실행 방지)

### Run 단위

* `runs`에 `idempotency_key` 저장
* 유니크: `(org_id, created_by, idempotency_key)`
* 같은 키로 요청이 오면:

  * 기존 run_id 반환(또는 상태/결과 반환)

### Step 단위(옵션)

* 같은 run에서 동일 step을 중복 실행하지 않게 `run_steps(run_id, step_key)`로 최신 성공 결과 재사용 가능
* 단, “부분 재생성”은 lineage가 달라지므로 step 재사용 조건을 엄격히(입력 해시 동일할 때만)

---

## 2.6 부분 재생성(슬라이드 단위) 설계

### 요구

* “슬라이드 5장 중 2장만 다시 생성”
* 나머지는 유지(일관성 유지)

### 데이터 모델

* 새 `run`을 만들되:

  * `parent_run_id` = 원 run
  * `lineage`에 변경 대상(`slide_ids`, `artifact_version_id`) 기록
* 실행 시:

  * 기존 SlideSpec를 불러와 “대상 슬라이드만 교체”하는 형태로 IR 업데이트
  * 렌더링은 전체 덱을 다시 패키징하되, 내부적으로는 변경된 슬라이드만 재계산 가능(추후 최적화)

---

# 3) SlideSpec/DocSpec JSON Schema v1

아래 스키마는 **“검증 가능한 IR”**로 설계했습니다.

* LLM은 이 스키마를 만족하는 JSON만 출력하도록 유도
* 렌더러는 이 IR을 입력으로 PPTX/DOCX를 생성
* 이후 v2 확장 시 `spec_version`으로 호환성 유지

> JSON Schema는 Draft 2020-12 기준 형태로 작성합니다(검증 라이브러리 선택은 자유).

---

## 3.1 SlideSpec v1 (JSON Schema)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://example.com/schemas/slidespec-v1.json",
  "title": "SlideSpec v1",
  "type": "object",
  "additionalProperties": false,
  "required": ["spec_version", "deck", "theme"],
  "properties": {
    "spec_version": { "type": "string", "const": "slidespec_v1" },

    "deck": {
      "type": "object",
      "additionalProperties": false,
      "required": ["title", "slides"],
      "properties": {
        "title": { "type": "string", "minLength": 1, "maxLength": 200 },
        "subtitle": { "type": "string", "maxLength": 300 },
        "language": { "type": "string", "default": "ko" },
        "audience": { "type": "string", "maxLength": 80 },
        "tone": { "type": "string", "maxLength": 80 },
        "tags": { "type": "array", "items": { "type": "string" }, "maxItems": 30 },
        "slides": {
          "type": "array",
          "minItems": 1,
          "maxItems": 200,
          "items": { "$ref": "#/$defs/slide" }
        }
      }
    },

    "theme": {
      "type": "object",
      "additionalProperties": false,
      "required": ["template_ref", "brand"],
      "properties": {
        "template_ref": {
          "type": "object",
          "additionalProperties": false,
          "required": ["template_id"],
          "properties": {
            "template_id": { "type": "string", "minLength": 1 },
            "template_version": { "type": "string" }
          }
        },
        "brand": {
          "type": "object",
          "additionalProperties": true,
          "required": ["brand_kit_id"],
          "properties": {
            "brand_kit_id": { "type": "string", "minLength": 1 },
            "tokens": { "type": "object" }
          }
        },
        "slide_size": {
          "type": "string",
          "enum": ["widescreen_16_9", "standard_4_3"],
          "default": "widescreen_16_9"
        }
      }
    },

    "assets": {
      "type": "array",
      "items": { "$ref": "#/$defs/assetRef" },
      "maxItems": 500
    },

    "extensions": { "type": "object" }
  },

  "$defs": {
    "slide": {
      "type": "object",
      "additionalProperties": false,
      "required": ["slide_id", "type", "layout", "elements"],
      "properties": {
        "slide_id": { "type": "string", "minLength": 1, "maxLength": 80 },
        "type": {
          "type": "string",
          "enum": ["title", "section", "content", "chart", "table", "image", "quote", "closing", "custom"]
        },
        "layout": {
          "type": "object",
          "additionalProperties": false,
          "required": ["layout_id"],
          "properties": {
            "layout_id": { "type": "string", "minLength": 1, "maxLength": 80 },
            "layout_hints": { "type": "object" }
          }
        },
        "elements": {
          "type": "array",
          "minItems": 1,
          "maxItems": 50,
          "items": { "$ref": "#/$defs/element" }
        },
        "speaker_notes": { "type": "string", "maxLength": 5000 },

        "citations": {
          "type": "array",
          "maxItems": 50,
          "items": { "$ref": "#/$defs/citation" }
        },

        "extensions": { "type": "object" }
      }
    },

    "element": {
      "type": "object",
      "additionalProperties": false,
      "required": ["element_id", "kind"],
      "properties": {
        "element_id": { "type": "string", "minLength": 1, "maxLength": 80 },
        "kind": { "type": "string", "enum": ["text", "bullets", "image", "chart", "table", "shape", "divider"] },
        "role": { "type": "string", "maxLength": 80 },

        "content": { "type": "object" },

        "style": {
          "type": "object",
          "additionalProperties": true,
          "properties": {
            "variant": { "type": "string" },
            "emphasis": { "type": "string", "enum": ["none", "low", "medium", "high"], "default": "none" }
          }
        },

        "data_ref": { "type": "string" },

        "constraints": {
          "type": "object",
          "additionalProperties": true,
          "properties": {
            "priority": { "type": "integer", "minimum": 0, "maximum": 100, "default": 50 },
            "allow_shrink": { "type": "boolean", "default": true },
            "min_font_pt": { "type": "number", "minimum": 8, "maximum": 28, "default": 12 }
          }
        },

        "citations": {
          "type": "array",
          "maxItems": 20,
          "items": { "$ref": "#/$defs/citationRef" }
        },

        "extensions": { "type": "object" }
      },

      "allOf": [
        {
          "if": { "properties": { "kind": { "const": "text" } } },
          "then": { "$ref": "#/$defs/textElement" }
        },
        {
          "if": { "properties": { "kind": { "const": "bullets" } } },
          "then": { "$ref": "#/$defs/bulletsElement" }
        },
        {
          "if": { "properties": { "kind": { "const": "image" } } },
          "then": { "$ref": "#/$defs/imageElement" }
        },
        {
          "if": { "properties": { "kind": { "const": "chart" } } },
          "then": { "$ref": "#/$defs/chartElement" }
        },
        {
          "if": { "properties": { "kind": { "const": "table" } } },
          "then": { "$ref": "#/$defs/tableElement" }
        }
      ]
    },

    "textElement": {
      "type": "object",
      "required": ["content"],
      "properties": {
        "content": {
          "type": "object",
          "additionalProperties": false,
          "required": ["text"],
          "properties": {
            "text": { "type": "string", "minLength": 1, "maxLength": 2000 }
          }
        }
      }
    },

    "bulletsElement": {
      "type": "object",
      "required": ["content"],
      "properties": {
        "content": {
          "type": "object",
          "additionalProperties": false,
          "required": ["items"],
          "properties": {
            "items": {
              "type": "array",
              "minItems": 1,
              "maxItems": 30,
              "items": { "type": "string", "minLength": 1, "maxLength": 300 }
            }
          }
        }
      }
    },

    "imageElement": {
      "type": "object",
      "required": ["content"],
      "properties": {
        "content": {
          "type": "object",
          "additionalProperties": false,
          "required": ["asset_id"],
          "properties": {
            "asset_id": { "type": "string", "minLength": 1 },
            "alt_text": { "type": "string", "maxLength": 300 },
            "crop": {
              "type": "string",
              "enum": ["contain", "cover", "center_crop"],
              "default": "center_crop"
            }
          }
        }
      }
    },

    "chartElement": {
      "type": "object",
      "required": ["content"],
      "properties": {
        "content": {
          "type": "object",
          "additionalProperties": false,
          "required": ["chart_type", "series"],
          "properties": {
            "chart_type": { "type": "string", "enum": ["bar", "line", "pie", "area", "stacked_bar"] },
            "title": { "type": "string", "maxLength": 150 },
            "x_label": { "type": "string", "maxLength": 80 },
            "y_label": { "type": "string", "maxLength": 80 },
            "series": {
              "type": "array",
              "minItems": 1,
              "maxItems": 10,
              "items": {
                "type": "object",
                "additionalProperties": false,
                "required": ["name", "data"],
                "properties": {
                  "name": { "type": "string", "maxLength": 80 },
                  "data": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 200,
                    "items": {
                      "type": "object",
                      "additionalProperties": false,
                      "required": ["x", "y"],
                      "properties": {
                        "x": { "type": ["string", "number"] },
                        "y": { "type": "number" }
                      }
                    }
                  }
                }
              }
            },
            "notes": { "type": "string", "maxLength": 1000 }
          }
        }
      }
    },

    "tableElement": {
      "type": "object",
      "required": ["content"],
      "properties": {
        "content": {
          "type": "object",
          "additionalProperties": false,
          "required": ["columns", "rows"],
          "properties": {
            "title": { "type": "string", "maxLength": 150 },
            "columns": {
              "type": "array",
              "minItems": 1,
              "maxItems": 20,
              "items": { "type": "string", "minLength": 1, "maxLength": 80 }
            },
            "rows": {
              "type": "array",
              "minItems": 1,
              "maxItems": 200,
              "items": {
                "type": "array",
                "minItems": 1,
                "maxItems": 20,
                "items": { "type": ["string", "number", "null"] }
              }
            }
          }
        }
      }
    },

    "assetRef": {
      "type": "object",
      "additionalProperties": false,
      "required": ["asset_id", "type", "source"],
      "properties": {
        "asset_id": { "type": "string", "minLength": 1 },
        "type": { "type": "string", "enum": ["image", "icon", "data"] },
        "source": {
          "type": "object",
          "additionalProperties": false,
          "required": ["kind"],
          "properties": {
            "kind": { "type": "string", "enum": ["file", "url", "generated"] },
            "file_id": { "type": "string" },
            "url": { "type": "string" }
          }
        }
      }
    },

    "citation": {
      "type": "object",
      "additionalProperties": false,
      "required": ["id", "kind"],
      "properties": {
        "id": { "type": "string", "minLength": 1, "maxLength": 80 },
        "kind": { "type": "string", "enum": ["evidence", "url"] },
        "evidence_id": { "type": "string" },
        "url": { "type": "string" },
        "title": { "type": "string", "maxLength": 200 },
        "locator": { "type": "object" }
      }
    },

    "citationRef": {
      "type": "object",
      "additionalProperties": false,
      "required": ["citation_id"],
      "properties": {
        "citation_id": { "type": "string", "minLength": 1, "maxLength": 80 },
        "note": { "type": "string", "maxLength": 200 }
      }
    }
  }
}
```

### SlideSpec v1 운영 규칙(권장)

* `slide_id`, `element_id`는 **항상 안정적으로 유지**(부분 재생성/ diff/재렌더에 필수)
* 텍스트가 길어질 가능성이 크므로, `constraints.min_font_pt`, `allow_shrink` 같은 힌트는 렌더러가 반드시 존중
* citations는 “슬라이드 단위 + 요소 단위” 둘 다 지원(최소는 슬라이드 단위만 써도 됨)

---

## 3.2 DocSpec v1 (JSON Schema)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://example.com/schemas/docspec-v1.json",
  "title": "DocSpec v1",
  "type": "object",
  "additionalProperties": false,
  "required": ["spec_version", "doc", "theme"],
  "properties": {
    "spec_version": { "type": "string", "const": "docspec_v1" },

    "doc": {
      "type": "object",
      "additionalProperties": false,
      "required": ["title", "blocks"],
      "properties": {
        "title": { "type": "string", "minLength": 1, "maxLength": 200 },
        "subtitle": { "type": "string", "maxLength": 300 },
        "language": { "type": "string", "default": "ko" },
        "author": { "type": "string", "maxLength": 120 },
        "created_date": { "type": "string", "format": "date" },
        "blocks": {
          "type": "array",
          "minItems": 1,
          "maxItems": 5000,
          "items": { "$ref": "#/$defs/block" }
        }
      }
    },

    "theme": {
      "type": "object",
      "additionalProperties": false,
      "required": ["template_ref", "brand"],
      "properties": {
        "template_ref": {
          "type": "object",
          "additionalProperties": false,
          "required": ["template_id"],
          "properties": {
            "template_id": { "type": "string", "minLength": 1 },
            "template_version": { "type": "string" }
          }
        },
        "brand": {
          "type": "object",
          "additionalProperties": true,
          "required": ["brand_kit_id"],
          "properties": {
            "brand_kit_id": { "type": "string", "minLength": 1 },
            "tokens": { "type": "object" }
          }
        }
      }
    },

    "references": {
      "type": "array",
      "maxItems": 200,
      "items": { "$ref": "#/$defs/citation" }
    },

    "extensions": { "type": "object" }
  },

  "$defs": {
    "block": {
      "type": "object",
      "additionalProperties": false,
      "required": ["block_id", "type"],
      "properties": {
        "block_id": { "type": "string", "minLength": 1, "maxLength": 80 },
        "type": { "type": "string", "enum": ["heading", "paragraph", "list", "table", "figure", "quote", "page_break"] },
        "content": { "type": "object" },
        "style": { "type": "object", "additionalProperties": true },
        "citations": {
          "type": "array",
          "maxItems": 20,
          "items": { "$ref": "#/$defs/citationRef" }
        },
        "extensions": { "type": "object" }
      },
      "allOf": [
        { "if": { "properties": { "type": { "const": "heading" } } }, "then": { "$ref": "#/$defs/headingBlock" } },
        { "if": { "properties": { "type": { "const": "paragraph" } } }, "then": { "$ref": "#/$defs/paragraphBlock" } },
        { "if": { "properties": { "type": { "const": "list" } } }, "then": { "$ref": "#/$defs/listBlock" } },
        { "if": { "properties": { "type": { "const": "table" } } }, "then": { "$ref": "#/$defs/tableBlock" } },
        { "if": { "properties": { "type": { "const": "figure" } } }, "then": { "$ref": "#/$defs/figureBlock" } }
      ]
    },

    "headingBlock": {
      "type": "object",
      "required": ["content"],
      "properties": {
        "content": {
          "type": "object",
          "additionalProperties": false,
          "required": ["level", "text"],
          "properties": {
            "level": { "type": "integer", "minimum": 1, "maximum": 6 },
            "text": { "type": "string", "minLength": 1, "maxLength": 300 }
          }
        }
      }
    },

    "paragraphBlock": {
      "type": "object",
      "required": ["content"],
      "properties": {
        "content": {
          "type": "object",
          "additionalProperties": false,
          "required": ["text"],
          "properties": {
            "text": { "type": "string", "minLength": 1, "maxLength": 10000 }
          }
        }
      }
    },

    "listBlock": {
      "type": "object",
      "required": ["content"],
      "properties": {
        "content": {
          "type": "object",
          "additionalProperties": false,
          "required": ["items"],
          "properties": {
            "ordered": { "type": "boolean", "default": false },
            "items": {
              "type": "array",
              "minItems": 1,
              "maxItems": 200,
              "items": { "type": "string", "minLength": 1, "maxLength": 500 }
            }
          }
        }
      }
    },

    "tableBlock": {
      "type": "object",
      "required": ["content"],
      "properties": {
        "content": {
          "type": "object",
          "additionalProperties": false,
          "required": ["columns", "rows"],
          "properties": {
            "title": { "type": "string", "maxLength": 200 },
            "columns": {
              "type": "array",
              "minItems": 1,
              "maxItems": 30,
              "items": { "type": "string", "minLength": 1, "maxLength": 120 }
            },
            "rows": {
              "type": "array",
              "minItems": 1,
              "maxItems": 2000,
              "items": {
                "type": "array",
                "minItems": 1,
                "maxItems": 30,
                "items": { "type": ["string", "number", "null"] }
              }
            }
          }
        }
      }
    },

    "figureBlock": {
      "type": "object",
      "required": ["content"],
      "properties": {
        "content": {
          "type": "object",
          "additionalProperties": false,
          "required": ["asset_id", "caption"],
          "properties": {
            "asset_id": { "type": "string", "minLength": 1 },
            "caption": { "type": "string", "maxLength": 500 },
            "alt_text": { "type": "string", "maxLength": 300 }
          }
        }
      }
    },

    "citation": {
      "type": "object",
      "additionalProperties": false,
      "required": ["id", "kind"],
      "properties": {
        "id": { "type": "string", "minLength": 1, "maxLength": 80 },
        "kind": { "type": "string", "enum": ["evidence", "url"] },
        "evidence_id": { "type": "string" },
        "url": { "type": "string" },
        "title": { "type": "string", "maxLength": 200 },
        "locator": { "type": "object" }
      }
    },

    "citationRef": {
      "type": "object",
      "additionalProperties": false,
      "required": ["citation_id"],
      "properties": {
        "citation_id": { "type": "string", "minLength": 1, "maxLength": 80 },
        "note": { "type": "string", "maxLength": 200 }
      }
    }
  }
}
```

---

# 4) PPTX 렌더링 레이아웃 규칙 (Renderer Spec)

이 부분이 “문서/PPT 업무 에이전트” 품질을 좌우합니다. 핵심은:

* **SlideSpec(의도/구조) → 레이아웃 계산(박스/폰트) → PPTX 생성**
* 품질 검사(QC)로 **겹침/오버플로우를 탐지**하고
* 자동 수정(Fix Layout) 루프로 **재현 가능한 개선**을 수행

아래는 “MVP에서 바로 구현 가능한 규칙 + 확장 방향”입니다.

---

## 4.1 좌표/기본 단위/슬라이드 크기

* 기본 슬라이드: **16:9 widescreen**
* 내부 계산 단위:

  * 렌더러 내부는 `pt` 또는 `px`로 계산하고,
  * PPTX는 라이브러리가 요구하는 단위(예: inch/EMU)에 맞춰 변환
* 안전 영역(Safe Area):

  * 좌/우/상/하 기본 마진 `M = 0.5in`(템플릿에 따라 오버라이드)
  * 하단은 citations/footer용으로 추가 예약 영역 `F = 0.3~0.4in`

> 템플릿에 placeholder가 있으면 **placeholder 박스를 우선 사용**하고, 없을 때만 계산 기반 레이아웃을 사용합니다.

---

## 4.2 레이아웃 템플릿(권장 최소 세트)

`layout_id`는 템플릿의 마스터 레이아웃 이름과 1:1로 매핑하거나, 템플릿이 없을 때는 아래 프리셋으로 처리합니다.

* `title_center`
* `section_header`
* `one_column`
* `two_column`
* `chart_focus`
* `table_focus`
* `image_full_bleed`
* `quote_center`
* `closing`

각 레이아웃은 “슬롯(slot)”을 정의합니다.

예) `two_column` 슬롯:

* Title 영역: 상단 15%
* Left content box: 좌 55%
* Right content box: 우 45%
* Footer/citations: 하단 예약

---

## 4.3 텍스트 레이아웃 규칙(가장 중요)

### 4.3.1 텍스트 측정(Measure)

PPTX 생성에서 가장 흔한 버그는 “줄바꿈/높이 계산 오차”입니다. 그래서 렌더러에 `measureText()`가 반드시 필요합니다.

**권장 구현 방식(우선순위)**

1. 템플릿 폰트를 실제로 로드해 **폰트 메트릭 기반 측정** (가장 정확)
2. Canvas 기반 측정(대부분 충분)
3. 근사치(평균 글자 폭) + 안전 여유(least recommended)

**CJK(한글) 대응 팁**

* 영문보다 글자 폭/줄높이 오차가 크므로,

  * lineHeight를 `fontSize * 1.25~1.35`로 잡고
  * 박스 높이의 5~8%는 안전 여유로 남겨둡니다.

---

### 4.3.2 줄바꿈(Wrapping) 규칙

* 기본: 단어 기준(공백) 줄바꿈
* 한글/중국어/일본어: “문자 단위 끊기”를 허용하되,

  * 조사/괄호 앞뒤는 가능한 붙이기(간단한 룰만 적용해도 개선됨)

---

### 4.3.3 오버플로우 처리(폰트 축소 → 요약 → 분할)

모든 텍스트 박스는 다음 정책을 따릅니다.

1. **지정 fontSize로 배치**
2. 높이 초과 시:

   * `allow_shrink=true`면 `fontSize`를 단계적으로 축소(예: 2pt씩)
   * 최소값은 `min_font_pt`(기본 12, 제목은 20 이상 권장)
3. 최소 폰트에서도 초과 시(여기서 품질 갈림):

   * 옵션 A(MVP): **자동 분할**

     * bullets면: 다음 슬라이드로 넘기거나 2열 bullets로 전환
     * paragraph면: 요약(step) 호출로 문장 줄이기
   * 옵션 B(고급): **레이아웃 변경**

     * `two_column → one_column` 전환
     * `chart_focus`에서 차트 영역 축소, 텍스트 확대 등

> 추천: MVP는 A를 먼저 구현하고, B는 점진 도입.

---

## 4.4 Bullets 규칙(업무 슬라이드 핵심)

* bullet 최대 줄 수(가이드):

  * `two_column`에서 한 컬럼: 6~9줄
  * `one_column`: 8~12줄
* 아이템 수가 많거나 문장이 길면:

  * 1차: 폰트 축소
  * 2차: **2열 분할**(left/right)
  * 3차: **다음 슬라이드로 자동 분할** (슬라이드 제목에 “(계속)” 표시)

---

## 4.5 이미지 규칙

* 기본 crop: `center_crop`
* 목표:

  * 레이아웃 슬롯을 채우되 왜곡 금지(비율 유지)
* 작은 이미지(아이콘/로고):

  * `contain`로 처리 + 여백 허용
* 이미지가 부족하거나 깨질 때:

  * placeholder(회색 박스 + alt_text)로 fallback
  * QC에서 “missing asset”로 경고

---

## 4.6 차트 규칙(데이터 → 차트 스타일)

* Chart Element는 `series` 기반으로 렌더
* 규칙:

  * 범주가 10개 초과면 bar 대신 **top-N + 기타(Other)** 고려(또는 다음 슬라이드 분할)
  * line chart는 x축 라벨 과밀하면 샘플링(예: 1/2, 1/3 표시)
  * pie는 항목 6개 초과면 지양(자동으로 bar로 변경 가능)

> MVP: 일단 “그려주기 + 라벨 겹침 최소화”까지만 하고, 고급 축소/집계는 후순위.

---

## 4.7 표(Table) 규칙

표는 PPT에서 가장 깨지기 쉬운 요소입니다.

* 최대 권장:

  * 열 ≤ 8, 행 ≤ 12 (슬라이드 1장 기준)
* 초과 시:

  * 행 페이지네이션(2장 이상으로 분할)
  * 또는 “핵심 행만 남기고 나머지 부록(appendix) 슬라이드로”

렌더링 규칙:

* 헤더 행은 굵게 + 배경색(브랜드 톤)
* 셀 padding 고정(예: 6pt)
* 숫자 정렬: 우측 정렬, 텍스트는 좌측

---

## 4.8 Citations/Footnote 규칙(신뢰성)

* 하단 예약 영역(Footer band)을 두고 citations를 렌더
* 표시 방식:

  * 슬라이드 내 숫자/주장에 `[1] [2]`처럼 짧은 키만 표시
  * footer에는 `1. 출처명(페이지)` 정도로 짧게
  * 상세 URL/긴 텍스트는 speaker_notes에 넣기(슬라이드 미관 유지)

---

## 4.9 레이아웃 QC(자동 검사) 규칙

렌더링 후(또는 렌더 전 계산 단계에서) 다음을 검사합니다.

### 4.9.1 필수 검사

* **Out-of-bounds:** 요소 bounding box가 safe area 밖으로 나가는지
* **Overlap:** 서로 다른 요소 bbox가 겹치는지(임계치 예: 2% 이상 겹치면 fail)
* **Overflow:** 텍스트가 박스 높이를 초과하는지(측정 기반)
* **Min font:** 폰트가 `min_font_pt` 미만인지
* **Citations overflow:** footer 영역을 넘어가는지

### 4.9.2 QC 결과 포맷(예시)

QC는 `run_steps.output_json`에 아래처럼 남기면 좋습니다.

```json
{
  "pass": false,
  "issues": [
    {"type":"overflow", "slide_id":"s3", "element_id":"e2", "severity":"high", "details":{"needed_lines":12,"box_lines":8}},
    {"type":"overlap", "slide_id":"s5", "severity":"medium", "details":{"a":"e1","b":"e4","overlap_ratio":0.07}}
  ]
}
```

---

## 4.10 Fix Layout(자동 수정) 루프 규칙

QC에서 fail이 나오면 “수정 루프”를 돌립니다.

### 4.10.1 수정 우선순위(Deterministic)

1. 텍스트 폰트 축소(허용 범위 내)
2. 줄바꿈 재계산(폭/lineHeight 조정)
3. 슬롯 재배치(여백/간격 조정)
4. 레이아웃 변환(two_column ↔ one_column)
5. 슬라이드 분할(표/불릿)
6. 마지막: 요약(step 호출)로 텍스트 자체를 줄이기

> 여기서 1~5는 “비-LLM 결정론적”으로 처리 가능해서 재현성이 좋고 비용이 낮습니다.
> 6은 비용이 들지만 “품질 보장”에 필요할 때만 사용합니다.

### 4.10.2 루프 상한

* Fix 루프는 무한 루프 방지 필요

  * 예: max 3회
* 3회 후에도 fail이면:

  * “needs_human_edit”로 표시하고,
  * UI에서 해당 슬라이드 하이라이트 + 수정 가이드 제공

---

## 4.11 Speaker Notes 규칙(디버깅 + 신뢰)

각 슬라이드 speaker notes에 아래를 자동 삽입하는 것을 추천합니다.

* 생성 요약(이 슬라이드의 핵심 메시지)
* 사용한 근거 목록(증거 id/페이지)
* 데이터 변환 내역(표→차트 가공 등)

이렇게 하면:

* 사용자 신뢰가 올라가고
* QA/디버깅이 쉬워집니다.

---

# 다음 구현 단계를 바로 시작하려면(권장)

이 4개 설계를 토대로, 실제 개발에서는 보통 다음이 “첫 주차 핵심”입니다.

1. **runs/run_steps/run_events + 워커 큐**부터 붙여서
2. SlideSpec(JSON) 한 장짜리(`title_center`)라도 렌더링하고
3. QC(overflow/overlap) 결과를 run_events로 스트리밍