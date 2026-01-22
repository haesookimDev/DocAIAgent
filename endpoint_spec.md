# A) API 엔드포인트 상세 스펙 (v1)

## A.1 공통 규칙

### Base

* Base URL: `/v1`
* Content-Type: `application/json; charset=utf-8`

### 인증/조직 선택

* 인증: `Authorization: Bearer <JWT/OIDC Access Token>`
* 한 사용자가 여러 org에 속할 수 있으므로 **현재 org 컨텍스트 선택** 필요:

  * 권장: `X-Org-Id: <uuid>` (또는 토큰에 active org 포함)
* 프로젝트 권한은 `project_memberships` 기준(RBAC).

### 멱등성(Idempotency)

* 생성성 API(특히 `POST /runs`, `POST /files:initiate`)는 헤더로 멱등성 지원:

  * `Idempotency-Key: <string>`
* 서버는 `(org_id, user_id, idempotency_key)`가 같으면 기존 결과를 반환.

### 표준 응답 포맷(권장)

성공:

```json
{
  "data": { },
  "meta": { "request_id": "req_...", "server_time": "2026-01-21T12:34:56Z" }
}
```

에러:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "template_id is required",
    "details": { "field": "template_id" }
  },
  "meta": { "request_id": "req_..." }
}
```

### 에러 코드(초기 MVP 권장 세트)

* `AUTH_REQUIRED` / `FORBIDDEN` / `NOT_FOUND`
* `VALIDATION_ERROR` (입력 검증)
* `CONFLICT` (멱등성 충돌, 상태 전이 불가 등)
* `POLICY_DENIED` (외부망 금지 등 정책 위반)
* `RATE_LIMITED`
* `RUN_NOT_APPROVABLE` (승인 단계가 아닌데 approve 호출)
* `RUN_CANCELLED` (취소된 run에 작업 요청)

### 비동기 작업 모델

* “생성”은 대부분 비동기:

  * `POST /runs` → 즉시 `run_id` 반환
  * 진행 상황은 `GET /runs/{id}` 폴링 또는 `GET /runs/{id}/events` SSE로 수신

---

## A.2 Projects

### GET /v1/projects

내 프로젝트 목록

* Query: `limit`, `cursor`
* Response `data.items[]`: `{project_id, name, role, created_at}`

### POST /v1/projects

프로젝트 생성

```json
{
  "name": "ACME Sales Deck",
  "description": "Q1 영업자료",
  "policy_profile_id": "uuid(optional)"
}
```

---

## A.3 Files (업로드 + 처리 파이프라인)

> 브라우저 업로드/대용량을 고려해 “initiate/complete” 2단계 권장

### POST /v1/projects/{project_id}/files:initiate

업로드 세션 생성(프리사인 URL 발급)
Headers:

* `Idempotency-Key: ...`

Body:

```json
{
  "filename": "market.pdf",
  "content_type": "application/pdf",
  "byte_size": 1234567,
  "sha256": "hex..."
}
```

Response:

```json
{
  "data": {
    "file_id": "uuid",
    "upload": {
      "method": "PUT",
      "url": "https://s3-presigned-url...",
      "headers": { "Content-Type": "application/pdf" }
    }
  }
}
```

### POST /v1/projects/{project_id}/files/{file_id}:complete

업로드 완료 처리(서버가 파일 메타 확정)

```json
{ "uploaded": true }
```

Response:

```json
{
  "data": {
    "file_id": "uuid",
    "status": "ready",
    "processing": {
      "extract": "queued",
      "index": "queued"
    }
  }
}
```

### GET /v1/projects/{project_id}/files

파일 목록

### GET /v1/files/{file_id}

파일 메타 조회(권한 체크)

### POST /v1/files/{file_id}:index

인덱싱(재)실행 트리거

```json
{ "force_reindex": false }
```

---

## A.4 Templates / Brand Kits

### POST /v1/templates:initiate

템플릿 업로드 세션 생성(pptx/docx)

```json
{
  "name": "ACME Default Template",
  "template_type": "pptx",
  "filename": "acme_template.pptx",
  "content_type": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
  "byte_size": 999999,
  "sha256": "hex..."
}
```

### POST /v1/templates/{template_id}:complete

완료 처리 후 (선택) theme 추출 job enqueue

### GET /v1/templates

템플릿 목록

---

### POST /v1/brandkits

브랜드 킷 생성

```json
{
  "name": "ACME Brand v1",
  "tokens": {
    "colors": { "primary": "#123456", "accent": "#FF9900" },
    "fonts": { "heading": "Pretendard", "body": "Pretendard" },
    "logo": { "asset": { "type": "file", "file_id": "uuid" }, "position": "top_right" },
    "spacing": { "page_margin_in": 0.5 }
  },
  "rules": {
    "allow_external_web": false,
    "min_body_font_pt": 12
  }
}
```

### GET /v1/brandkits

목록

### GET /v1/brandkits/{id}

상세

---

## A.5 Runs (핵심)

### POST /v1/runs

슬라이드 생성 run 시작

Headers:

* `Idempotency-Key: ...`

Body (Slides MVP):

```json
{
  "project_id": "uuid",
  "agent": { "key": "slides.deck_builder", "version": "1.0.0" },

  "inputs": {
    "prompt": "2026 사업계획 발표자료를 만들어줘. 임원 보고용, 10장 내외.",
    "language": "ko",
    "audience": "임원진",
    "tone": "간결하고 수치 기반",
    "file_ids": ["uuid1", "uuid2"],
    "template_id": "uuid",
    "brand_kit_id": "uuid",
    "options": {
      "slide_count": 10,
      "require_outline_approval": true,
      "include_citations": true,
      "allow_external_web": false
    }
  },

  "artifact": {
    "mode": "create", 
    "name": "2026 사업계획(초안)"
  }
}
```

Response:

```json
{
  "data": {
    "run_id": "uuid",
    "status": "planning",
    "progress": 0.0,
    "created_at": "2026-01-21T12:00:00Z"
  }
}
```

---

### GET /v1/runs/{run_id}

run 상태 조회

Response(예시):

```json
{
  "data": {
    "run_id": "uuid",
    "project_id": "uuid",
    "status": "waiting_approval",
    "progress": 22.5,
    "title": "2026 사업계획 발표자료",
    "current_step": { "step_key": "approval_outline", "status": "waiting_approval" },

    "intermediate": {
      "outline": {
        "schema_version": "outline_v1",
        "sections": [
          { "title": "시장/환경", "slides": 2 },
          { "title": "전략", "slides": 4 },
          { "title": "로드맵", "slides": 2 },
          { "title": "재무/리스크", "slides": 2 }
        ]
      }
    },

    "artifacts": null,
    "errors": null
  }
}
```

---

### GET /v1/projects/{project_id}/runs

프로젝트 run 목록(히스토리)

Query:

* `status=completed|failed|...`
* `limit`, `cursor`

---

### POST /v1/runs/{run_id}/cancel

취소 요청

```json
{ "reason": "잘못된 템플릿 선택" }
```

---

### POST /v1/runs/{run_id}/approve

승인 게이트 통과(Outline 승인)

Body:

```json
{
  "approval_key": "outline",
  "approved": true,
  "edited_outline": {
    "schema_version": "outline_v1",
    "sections": [
      { "title": "핵심 요약", "slides": 1 },
      { "title": "시장/환경", "slides": 2 },
      { "title": "전략", "slides": 4 },
      { "title": "로드맵", "slides": 2 },
      { "title": "재무/리스크", "slides": 1 }
    ]
  }
}
```

서버 동작:

* `run_steps(step_key=approval_outline)` → `succeeded`
* `runs.status` → `executing`로 전이
* 다음 step enqueue

에러:

* 승인 단계가 아니면 `RUN_NOT_APPROVABLE`

---

### POST /v1/runs/{run_id}/regenerate

부분 재생성(슬라이드 단위)

Body:

```json
{
  "scope": { "type": "slides", "slide_ids": ["s3", "s4"] },
  "instruction": "s3는 경쟁사 비교를 표가 아니라 차트로 바꾸고, s4는 더 공격적인 성장전략을 포함해줘.",
  "keep_style_consistent": true
}
```

Response:

```json
{
  "data": {
    "new_run_id": "uuid",
    "parent_run_id": "uuid",
    "status": "planning"
  }
}
```

---

## A.6 Run Events Streaming (SSE)

### GET /v1/runs/{run_id}/events

* 기본: 서버가 `run_events` 테이블을 기반으로 SSE로 푸시
* Query:

  * `after_seq` (옵션): 이 seq 이후 이벤트만
* Header:

  * `Accept: text/event-stream`

SSE 메시지 예:

```
event: progress
id: 12
data: {"progress":35.0,"status":"executing","step_key":"retrieve_evidence"}

event: intermediate
id: 15
data: {"kind":"outline","outline":{...}}

event: log
id: 16
data: {"level":"info","message":"Rendering started","step_key":"render_pptx"}

event: error
id: 21
data: {"code":"RENDER_OVERFLOW","message":"Slide s5 text overflow"}
```

클라이언트 재연결:

* `Last-Event-ID: 16` 또는 `after_seq=16`

---

## A.7 Artifacts (결과물 접근)

### GET /v1/projects/{project_id}/artifacts

아티팩트(덱/문서) 목록

### GET /v1/artifacts/{artifact_id}

아티팩트 메타 + 최신 버전

### GET /v1/artifacts/{artifact_id}/versions

버전 목록

### GET /v1/artifacts/{artifact_id}/versions/{version_id}

버전 상세(저장된 IR 포함 가능)

### POST /v1/artifacts/{artifact_id}/versions/{version_id}:download

다운로드용 Signed URL 발급(권장: 직접 바이너리 스트리밍 대신)

```json
{ "format": "pptx" }
```

Response:

```json
{
  "data": {
    "url": "https://signed-url...",
    "expires_in_seconds": 600
  }
}
```

### GET /v1/artifacts/{artifact_id}/versions/{version_id}/preview

프리뷰(PDF/썸네일) URL 발급

---

# B) 워커 잡 Payload 규격 (Queue/Workflow Contract)

워커는 언어/런타임이 달라도 되지만, **job envelope는 통일**해야 운영/디버깅이 쉬워집니다.

## B.1 공통 Envelope (모든 job 공통)

```json
{
  "job_id": "uuid",
  "job_type": "run.step.render_pptx",
  "trace_id": "trace_...", 
  "org_id": "uuid",
  "project_id": "uuid",
  "run_id": "uuid",
  "step_id": "uuid",
  "step_key": "render_pptx",
  "attempt": 1,
  "enqueued_at": "2026-01-21T12:00:00Z",

  "policy_snapshot": {
    "allow_external_web": false,
    "pii_masking": true
  },

  "inputs": {
    "artifact_version_id": "uuid(optional)",
    "template_id": "uuid",
    "brand_kit_id": "uuid",
    "file_ids": ["uuid..."],
    "ir": { }
  },

  "dedupe": {
    "input_hash": "sha256...",
    "idempotency_key": "optional"
  }
}
```

### 워커의 필수 동작(계약)

1. 시작 시:

* `run_steps.status = running`
* `run_steps.started_at = now()`
* `run_events`에 `log/progress` emit

2. 성공 시:

* `run_steps.status = succeeded`
* `run_steps.output_json` 저장
* 다음 step enqueue는 **Orchestrator가 담당**(권장)

  * 워커가 직접 enqueue하면 사이드이펙트 관리가 어려움
  * 다만 MVP는 워커가 다음 step enqueue해도 됨(초기 단순화)

3. 실패 시:

* `run_steps.status = failed`
* `error_code`, `error_message`
* 재시도 가능 오류면 “raise → queue retry”로 위임(또는 워커가 판단)

4. 취소 체크:

* 작업 시작/장시간 루프 전마다 `runs.cancel_requested` 확인
* 취소면 `run_steps.status=cancelled`, `runs.status=cancelled` 전이(오케스트레이터 규칙에 따름)

---

## B.2 Job Type 카탈로그(슬라이드 MVP)

### 1) run.step.retrieve_evidence

**목적:** RAG 검색으로 evidence 목록 구성

inputs:

```json
{
  "query": {
    "prompt": "...",
    "outline": { "...": "..." }
  },
  "file_ids": ["..."],
  "top_k": 30
}
```

output_json 예:

```json
{
  "evidences": [
    {
      "evidence_id": "ev_001",
      "file_id": "uuid",
      "chunk_id": "uuid",
      "title": "시장 보고서 2025",
      "locator": { "page": 12 },
      "quote": "…"
    }
  ]
}
```

---

### 2) run.step.outline (agent)

**목적:** 목차/슬라이드 구성 초안 생성

inputs:

* prompt, audience/tone, 제한 슬라이드 수, evidence 요약

output_json:

* outline_v1

---

### 3) run.step.plan_slidespec (agent)

**목적:** SlideSpec v1 생성(스키마 준수)

inputs:

* approved outline
* evidence list
* template/brand constraints
* slide_count target

output_json:

* SlideSpec JSON

---

### 4) run.step.render_pptx (render)

**목적:** SlideSpec + template + assets → PPTX 생성(+ preview)

inputs:

```json
{
  "ir": { "spec_version": "slidespec_v1", "...": "..." },
  "template": { "template_id": "uuid" },
  "brand": { "brand_kit_id": "uuid" },
  "assets": [
    { "asset_id": "img_1", "resolved_storage_key": "s3://..." }
  ]
}
```

output_json:

```json
{
  "pptx_storage_key": "s3://.../deck.pptx",
  "preview_pdf_storage_key": "s3://.../deck.pdf",
  "thumbnails": [
    { "slide_id": "s1", "storage_key": "s3://.../s1.png" }
  ],
  "render_metrics": { "time_ms": 12000, "slide_count": 10 }
}
```

---

### 5) run.step.quality_check_layout (quality)

**목적:** overflow/overlap/out-of-bounds 검사

inputs:

* 렌더 전 계산 결과 또는 렌더 결과(썸네일/레이아웃 메타)

output_json:

```json
{
  "pass": false,
  "issues": [
    { "type": "overflow", "slide_id": "s5", "element_id": "s5_e2", "severity": "high" }
  ]
}
```

---

### 6) run.step.fix_layout (system/agent 혼합)

**목적:** 결정론적 수정(1~5) + 필요 시 텍스트 요약(LLM)

inputs:

```json
{
  "ir": { "...": "..." },
  "qc": { "issues": [ ... ] },
  "policy": { "max_fix_loops": 3 }
}
```

output_json:

* 수정된 SlideSpec (또는 patch)

---

### 7) run.step.finalize (system)

**목적:** artifact_version 생성/게시(draft), run 완료 처리

inputs:

* 렌더 결과 storage keys
* 최종 IR 스냅샷

output_json:

```json
{
  "artifact_id": "uuid",
  "artifact_version_id": "uuid",
  "version": 1,
  "status": "draft"
}
```

---

## B.3 Retry/Timeout 권장값(코드로 박아두기 좋게)

job_type별 기본 정책(예시):

```yaml
run.step.retrieve_evidence:
  timeout_sec: 60
  max_attempts: 3
  retry_on: [TIMEOUT, TRANSIENT_DB, RATE_LIMIT]

run.step.plan_slidespec:
  timeout_sec: 120
  max_attempts: 2
  retry_on: [TIMEOUT, RATE_LIMIT]
  on_schema_fail: enqueue(run.step.repair_slidespec)

run.step.render_pptx:
  timeout_sec: 300
  max_attempts: 1
  retry_on: [WORKER_CRASH, TRANSIENT_IO]

run.step.quality_check_layout:
  timeout_sec: 30
  max_attempts: 1
```

---

# C) SlideSpec 생성 프롬프트 템플릿 (스키마 준수 강제 + Repair)

여기서는 “모델이 JSON을 헛소리로 내지 않게” **강제력이 높은 템플릿**을 제공합니다.

## C.0 입력으로 전달할 컨텍스트(권장 포맷)

### Evidence 입력 포맷(LLM에 전달)

```json
{
  "evidences": [
    {
      "evidence_id": "ev_001",
      "title": "ACME 2025 시장 보고서",
      "file_id": "uuid",
      "locator": { "page": 12 },
      "quote": "2025년 시장 규모는 ...",
      "url": null
    }
  ]
}
```

### Template/Brand 제약 입력(LLM에 전달)

```json
{
  "template_constraints": {
    "allowed_layout_ids": [
      "title_center","section_header","one_column","two_column",
      "chart_focus","table_focus","quote_center","closing"
    ],
    "slide_size": "widescreen_16_9"
  },
  "brand_constraints": {
    "min_body_font_pt": 12,
    "min_heading_font_pt": 20,
    "avoid_dense_text": true,
    "max_bullets_per_slide": 8
  }
}
```

---

## C.1 Outline 생성 프롬프트(승인용)

```text
[SYSTEM]
너는 기업용 발표자료를 기획하는 시니어 컨설턴트다.
사용자의 요구, 목표 슬라이드 수, 청중, 톤을 고려해 '슬라이드 목차(Outline)'를 만든다.
출력은 반드시 JSON만 출력한다. 마크다운/설명/주석 금지.

[USER]
요구사항:
- 주제: {{prompt}}
- 청중: {{audience}}
- 톤: {{tone}}
- 목표 슬라이드 수: {{slide_count}}

제약:
- 섹션은 4~7개 사이
- 각 섹션에 할당할 슬라이드 수를 정수로 제시하고 총합은 목표 슬라이드 수와 같아야 한다.
- 첫 슬라이드는 "핵심 요약", 마지막은 "결론/요청사항" 포함

출력 JSON 스키마:
{
  "schema_version": "outline_v1",
  "title": string,
  "sections": [
    {"section_id":"sec1", "title": string, "slides": number, "key_points":[string, ...]}
  ]
}

이제 JSON만 출력해라.
```

---

## C.2 SlideSpec 생성 프롬프트(핵심)

> 포인트:
>
> 1. “JSON만” 강제
> 2. `spec_version=slidespec_v1` 강제
> 3. ID 규칙 강제(s1… / s1_e1…)
> 4. layout_id allowlist 강제
> 5. citations 규칙 강제(증거 없으면 “일반적 주장”으로 표현하고 수치/사실 단정 피하기)

```text
[SYSTEM]
너는 "SlideSpec v1" JSON을 생성하는 엔진이다.
반드시 아래 규칙을 지켜야 한다.

규칙(중요):
1) 출력은 반드시 단 하나의 JSON 객체만. 마크다운, 설명, 여는/닫는 문장 금지.
2) JSON은 SlideSpec v1 스키마를 만족해야 한다.
3) spec_version은 반드시 "slidespec_v1".
4) slide_id는 "s1", "s2", ... 순서대로.
5) 각 슬라이드의 element_id는 "s{n}_e1", "s{n}_e2"... 순서대로.
6) layout.layout_id는 allowed_layout_ids 중 하나만 사용.
7) 한 슬라이드에 elements는 2~8개 권장(최대 50이지만 과밀 금지).
8) 본문(bullets/paragraph)은 과밀하게 쓰지 말고, bullets는 슬라이드당 최대 8개 권장.
9) 숫자/통계/인용은 가능한 evidences로 뒷받침해야 한다.
   - 근거가 있으면 slide.citations에 citation 객체를 만들고,
   - 해당 element.citations에서 citation_id를 참조하라.
   - 근거가 없으면 단정적 수치를 만들지 말고, "추정/가정"으로 표현하라.
10) 템플릿/브랜드 제약을 준수하라(최소 폰트 등).

[USER]
입력:
- outline(JSON): {{outline_json}}
- evidences(JSON): {{evidences_json}}
- template_constraints(JSON): {{template_constraints_json}}
- brand_constraints(JSON): {{brand_constraints_json}}
- template_id: {{template_id}}
- brand_kit_id: {{brand_kit_id}}
- 언어: {{language}}
- 청중: {{audience}}
- 톤: {{tone}}

아래 SlideSpec v1 형태로 생성하라:
- theme.template_ref.template_id = template_id
- theme.brand.brand_kit_id = brand_kit_id
- deck.title은 outline.title 사용
- deck.slides는 outline 섹션 슬라이드 수를 반영하여 총 슬라이드 수를 맞춰라
- 섹션 시작에는 section_header 타입 슬라이드를 배치해도 된다(필요 시)

반드시 allowed_layout_ids:
{{allowed_layout_ids}}

출력은 오직 JSON.
```

---

## C.3 “스키마 검증 실패” Repair 프롬프트 (필수)

LLM이 스키마를 어기거나 누락하면 **재시도**보다 “Repair”가 훨씬 안정적입니다.

```text
[SYSTEM]
너는 JSON 스키마 오류를 수정하는 리페어 엔진이다.
입력으로 주어진 "원본 JSON"을 가능한 한 유지하면서, 오류를 고쳐 "유효한 SlideSpec v1" JSON만 출력한다.
설명 금지. 오직 JSON만 출력.

[USER]
다음은 SlideSpec v1 스키마 검증 오류 목록이다:
{{schema_errors}}

다음은 원본 JSON이다:
{{invalid_json}}

수정 규칙:
- spec_version, deck, theme, slides 구조를 반드시 맞춰라.
- slide_id/element_id 규칙을 지켜라 (s1.., s1_e1..).
- layout_id는 allowed_layout_ids 중 하나로만 수정하라.
- 누락된 required 필드는 합리적으로 채워라(의미가 크게 바뀌지 않게).
- 불필요하거나 스키마에 없는 필드는 제거하라.
- 출력은 반드시 JSON 1개.

allowed_layout_ids:
{{allowed_layout_ids}}
```

---

## C.4 “텍스트 과밀/오버플로우” 요약 프롬프트(선택, Fix Layout 루프의 6번)

결정론적 수정(폰트 축소/분할)로 해결 안 될 때만 호출하세요.

```text
[SYSTEM]
너는 발표자료 문장을 간결하게 줄이는 에디터다.
의미를 유지하면서 문장을 짧게 만들고, 불릿은 핵심 키워드 중심으로 재작성한다.
출력은 JSON만.

[USER]
문제:
- slide_id: {{slide_id}}
- 원본 텍스트/불릿:
{{content_json}}

제약:
- 총 글자수 30~40% 감소 목표
- 불릿은 최대 6개
- 숫자/고유명사는 유지
- 과장/추가 사실 생성 금지

출력 형식:
{
  "slide_id": "...",
  "updated_elements": [
    {"element_id":"...", "kind":"text|bullets", "content": {...}}
  ]
}
```

---

# (보너스) 바로 개발에 붙이기 좋은 “최소 OpenAPI 형태” 힌트(간단)

* `/runs`는 **비동기**이므로 202가 아니라 200/201로 run_id를 주고, 상태는 별도 조회/이벤트로 관리하는 방식이 구현이 단순합니다.
* SSE는 프론트에서 구현이 쉬워서 MVP에 적합하고, 나중에 WebSocket으로 확장하면 됩니다.

---

# 다음으로 내가 바로 이어서 설계해줄 것(추천 순서)

지금 단계에서 실제 구현이 막히는 지점은 보통 2가지예요:

1. **RunStep 실행 순서/워크플로우 정의를 코드로 어떻게 표현할지** (step graph / config-driven)
2. **Renderer 내부 레이아웃 계산 결과를 어떤 메타로 저장해서 QC/Fix가 반복 가능하게 할지** (bbox/line metrics)