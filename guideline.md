# AI 업무 산출물 에이전트 플랫폼 설계 문서

## 문서 메타

* 문서명: AI 업무 산출물(문서/PPT) 에이전트 플랫폼 설계
* 버전: v0.1
* 작성일: 2026-01-21
* 범위: MVP(슬라이드 중심) → Docs 확장 → Agent Builder(플랫폼화)까지 고려

---

## 1. 시스템 목적

### 1.1 문제 정의

기업/팀의 지식과 템플릿/브랜드 규칙을 기반으로 **보고서(DOCX/PDF), 제안서, 발표자료(PPTX/PDF)**를 빠르게 만들고, 수정/검수/버전관리를 자동화하고 싶다.

현실의 문제는 다음과 같습니다.

* “내용 생성”보다 **레이아웃/일관성/브랜드 준수/출처(근거) 관리**가 더 어렵다.
* LLM 단독으로 PPT/DOCX 바이너리를 직접 생성하면 품질이 흔들리고 재현이 어렵다.
* 업무 환경은 권한/감사/보안/외부망 정책이 강하게 요구된다.
* 사용자 요구는 “한 번에 끝”이 아니라 “초안 → 편집 → 부분 재생성 → 최종본” 루프다.

### 1.2 시스템 목표(Goals)

이 시스템은 다음을 목표로 한다.

1. **산출물 중심 생성**

* 프롬프트 + 내부 문서/데이터 + 템플릿을 기반으로 **완성도 높은 문서/PPT**를 생성하고 다운로드/공유 가능.

2. **중간 산출물 기반 제어(신뢰/품질)**

* 개요/목차/슬라이드 플랜 등 **중간 결과를 사람이 검토/승인**할 수 있어 품질을 통제.

3. **템플릿/브랜드 일관성**

* 조직의 템플릿(PPTX, DOCX)을 가져와 재사용하며, 폰트/컬러/로고/레이아웃 규칙을 지킨다.

4. **근거 기반 생성(RAG) + 출처 자동 표기**

* 업로드 문서에서 증거를 찾아 문장/수치에 출처를 매핑한다.

5. **플랫폼화(확장)**

* 기본 제공 에이전트(슬라이드/보고서/회의록 등)뿐 아니라,

  * 조직이 자체 워크플로우를 정의(Agent Builder)
  * 커넥터/툴(Drive/Confluence/Jira 등) 추가
  * 평가/정책(외부망 금지, PII 마스킹 등) 확장 가능

### 1.3 Non-Goals(이번 설계에서 “필수는 아닌 것”)

* 완전한 실시간 공동 편집(구글독스급): 초기엔 “생성 후 편집/버전” 중심
* 완전한 디자인 툴(피그마급): 초기엔 템플릿 + 레이아웃 자동화 중심
* 모든 문서 포맷 완벽 지원: MVP는 PPTX/DOCX/PDF 위주

---

## 2. 시스템 아키텍처(먼저 상세히)

이 시스템은 크게 **3개의 엔진 + 2개의 운영 기반**으로 구성됩니다.

### 2.1 핵심 구성 요소(개념)

1. **Workspace/UI**

* 사용자 경험의 중심: 프로젝트/파일/템플릿/산출물 편집/버전관리
* “채팅형 입력 + 중간 결과 검토 + 최종 산출물 에디트” 흐름을 제공

2. **Agentic Engine (에이전트 런타임)**

* 사용자의 요청을 “Run(작업 단위)”로 저장하고,
* 계획(Plan) → 실행(Act) → 검수(Check) → 수정(Iterate) 형태로 진행
* 여러 에이전트/툴을 단계적으로 조합

3. **Artifact Engine (산출물 렌더링 엔진)**

* LLM은 “내용과 구조(IR)”를 만들고,
* 실제 DOCX/PPTX/PDF 생성은 **렌더러(비-LLM)**가 담당
  → 레이아웃 안정성, 재현성, 템플릿 준수 확보

4. **Knowledge Engine (RAG/인덱싱)**

* 업로드 파일에서 텍스트/표/이미지/메타데이터 추출
* chunking, embedding, vector search
* 인용/출처 매핑(문장 ↔ evidence)

5. **Platform Foundation (보안/운영/확장)**

* 멀티테넌시, RBAC, 감사로그, 정책(외부망/PII), 관측(로그/트레이스), 비용/쿼터
* Tool/Connector/Agent 패키지 등록과 버전 관리

---

### 2.2 논리 아키텍처(High-Level)

```
[Web App: Workspace + Editor]
  - Prompt/Chat
  - Outline/Plan Review
  - Slide/Doc Preview & Edit
  - Template/Brand Manager
  - Run history / Versions

        │ (HTTPS + WebSocket/SSE)
        ▼
[API Gateway / BFF]
  - Auth (SSO/OAuth2)
  - Org/RBAC/Policy
  - Project/File APIs
  - Run APIs (start/stop/status)
  - Artifact APIs (preview/download)
  - Admin APIs (templates, quotas)

        │ (async job submit)
        ▼
[Workflow/Queue]
  - job orchestration
  - retries, timeouts, dead-letter

        ▼
[Worker Cluster]
  - Agent Runner (LLM orchestration)
  - Tool Runner (connectors/web/compute)
  - Retrieval/Indexing (RAG)
  - Artifact Renderers (PPTX/DOCX/PDF)
  - Quality Checkers (layout, citations, policy)

Data Stores
  - Postgres: metadata, runs, templates, policies
  - Object Storage(S3): files, artifacts, thumbnails
  - Vector DB(pgvector): embeddings/chunks/evidence
  - Redis: cache, locks, rate limit
  - Observability: logs/metrics/traces, prompt audit
```

---

### 2.3 물리/배포 아키텍처(확장 가능하게)

초기에는 **모듈러 모놀리스 + 워커**가 가장 효율적입니다.

* “API 서버(모놀리스)” 안에 서비스 모듈(Workspace/Run/Template 등)을 두고
* “워커”는 별도 프로세스/파드로 분리하여 비동기 처리

성장 단계에서 다음 기준으로 서비스 분리합니다.

* **RAG/Indexing** (CPU/IO-heavy)
* **Artifact Rendering** (메모리/폰트/렌더링 의존)
* **Tool Runner** (보안 격리 필요)
* **Agent Runner** (LLM 호출/비용 관리 집중)

---

## 3. 핵심 설계 원칙(부족한 부분을 채우는 기준)

### 3.1 “Run 중심 설계”

사용자 요청은 모두 **Run**으로 기록하고, Run은 상태/로그/중간산출물/최종산출물을 가진다.

* 장점:

  * 재현성(같은 입력 → 같은 결과를 더 잘 만들 수 있음)
  * 디버깅(어느 단계에서 품질이 깨졌는지)
  * 비용 최적화(단계별 토큰/시간)
  * 평가 자동화(회귀 테스트)

### 3.2 “IR(Intermediate Representation) 중심 산출물”

LLM이 직접 PPTX/DOCX를 만들지 않게 하고,

* LLM 출력 = **SlideSpec/DocSpec 같은 구조화 IR**
* 렌더러 출력 = **PPTX/DOCX/PDF 바이너리**

### 3.3 “정책/권한/감사”는 엔진에 내장

업무용 플랫폼은 기능보다 이게 더 중요할 때가 많습니다.

* 어떤 문서에 접근했는지
* 외부망을 썼는지
* 누가 어떤 산출물을 생성했는지
  → 모두 감사 로그로 남기고 정책으로 제어

### 3.4 “확장성”은 플러그인 단위로

* Agent Package(워크플로우 묶음)
* Tool Plugin(커넥터/유틸)
* Template Package(브랜드/레이아웃)
  이 3가지를 버전 관리 가능한 단위로 취급하면 확장이 쉬워집니다.

---

# 4. 상세 설계

## 4.1 주요 유즈케이스

### UC1: “자료 기반 슬라이드 자동 생성”

* 입력: 프롬프트 + PDF/엑셀/기존 PPT + 템플릿 선택
* 출력: PPTX + PDF(미리보기) + 썸네일

### UC2: “보고서(DOCX/PDF) 생성”

* 입력: 요구사항 + 참고문서 + 보고서 템플릿
* 출력: DOCX + PDF

### UC3: “부분 재생성”

* 특정 슬라이드만 다시 생성
* 특정 섹션만 다시 작성(문서)

### UC4: “기업 템플릿 가져오기(PPTX/DOCX import)”

* 회사 서식 업로드 → 테마 토큰 추출 → 템플릿 라이브러리 등록

### UC5: “에이전트 빌더로 워크플로우 커스텀”

* 예: “IRB 심사 문서 생성”, “보안 점검 보고서 생성” 같은 도메인 에이전트

---

## 4.2 컴포넌트 설계

### 4.2.1 Workspace Service

* 책임:

  * 프로젝트/폴더/파일 관리
  * 산출물 버전 관리(Generated Artifact Versions)
  * 공유/권한(프로젝트 단위)
* API 예:

  * `POST /projects`
  * `POST /projects/{id}/files` (업로드)
  * `GET /projects/{id}/artifacts`

### 4.2.2 Template & Brand Service

* 책임:

  * 템플릿(PPTX/DOCX) 등록/버전
  * 브랜드 토큰(색상/폰트/로고/여백 규칙)
  * 레이아웃 프리셋 관리(슬라이드 레이아웃, 표 스타일 등)
* 확장:

  * “브랜드 정책” (예: 특정 폰트만 허용, 로고 위치 고정)

### 4.2.3 Agent Run Service (Core)

* 책임:

  * Run 생성/상태 업데이트/취소
  * 단계별 출력 저장(Outline, SlideSpec, DocSpec)
  * 이벤트 스트리밍(진행률/로그)
* 필수 기능:

  * idempotency key 지원(중복 실행 방지)
  * 재시도 정책(LLM/툴 호출 실패 시)
  * run lineage(버전/부분 재생성 추적)

### 4.2.4 Workflow Orchestrator

* 선택지:

  * 간단: Redis Queue(BullMQ/Celery/RQ) + 상태를 DB에 기록
  * 고급: Temporal(권장, 장기적으로 안정)
* 요구:

  * step 단위로 재시작 가능
  * 워커 장애 시에도 진행/복구 가능

### 4.2.5 Tool Runner (Connector/Action)

* 책임:

  * 외부 시스템 커넥터(Drive/Confluence/Jira/Slack 등)
  * 내부 유틸(표 변환, 차트 생성 데이터 준비, 이미지 생성 등)
* 보안:

  * Tool 실행은 **권한/정책** 체크 필수
  * 가능한 경우 격리(컨테이너/샌드박스) 권장

### 4.2.6 Knowledge Engine (RAG)

* 파이프라인:

  1. 파일 업로드 → 텍스트/표 추출
  2. chunking + metadata
  3. embedding 생성
  4. vector store 저장
  5. run 실행 시 retrieval + citations 구성

* 추가(품질 상승):

  * 표/차트 데이터는 “구조화 추출”을 별도 트랙으로
  * 문서의 페이지/섹션 정보를 citation에 포함

### 4.2.7 Artifact Engine (Rendering)

* PPTX Renderer:

  * SlideSpec(IR) + Template(theme) + Assets → PPTX 생성
  * 썸네일/프리뷰 PDF 생성(가능하면)
  * 레이아웃 검사(겹침/오버플로우) + 자동 수정 루프

* DOCX Renderer:

  * DocSpec(IR) + Template → DOCX 생성
  * PDF 변환(옵션)
  * 표 스타일/번호/목차 처리

### 4.2.8 Quality & Policy Service

* 자동 검사:

  * 레이아웃: 텍스트 overflow, 요소 겹침, 폰트 최소 크기
  * 내용: 금칙어, PII/민감정보 포함 여부
  * 신뢰: 숫자/주장에 출처가 있는지
* 정책:

  * 외부망 사용 금지 프로젝트
  * 특정 커넥터만 허용
  * 데이터 보관 기간/내보내기 제한

---

## 4.3 데이터 설계(개념 모델)

### 4.3.1 핵심 엔티티

* `Org` / `User` / `Role`
* `Project`
* `FileAsset` (원본 업로드 파일)
* `Template` (pptx/docx template)
* `BrandKit` (color/font/logo rules)
* `AgentPackage` (워크플로우 정의)
* `Run` (작업 단위)
* `RunStep` (단계 실행 기록)
* `Artifact` (최종 산출물: pptx/docx/pdf)
* `Evidence` / `Citation` (출처 근거)

### 4.3.2 Run 상태 머신(예시)

* `CREATED` → `PLANNING` → `WAITING_APPROVAL` → `EXECUTING` → `RENDERING` → `QUALITY_CHECK` → `COMPLETED`
* 예외:

  * `FAILED` (재시도 가능)
  * `CANCELLED`

**중요**: 단계별 산출물을 DB/스토리지에 저장해서, 실패해도 이어가기 가능해야 함.

---

## 4.4 IR(중간 표현) 스키마 설계

### 4.4.1 SlideSpec v1 (요약)

* Deck 메타:

  * title, subtitle, audience, tone, language
* Theme/Brand:

  * theme_id, brand_tokens(color/font/logo)
* Slides:

  * slide_id, type, layout_id
  * elements: text/bullets/image/chart/table
  * speaker_notes
  * citations: evidence refs

**원칙**

* LLM 출력은 “의도/구조” 중심
* 좌표/박스 계산은 Renderer(또는 Designer 단계)에서 확정

### 4.4.2 DocSpec v1 (요약)

* Document meta: title, author, date
* Sections: heading(level), paragraph, list, table, figure
* References: citations list
* Appendix: glossary, attachments

---

## 4.5 주요 플로우 설계

### 4.5.1 “슬라이드 생성” 시퀀스(텍스트)

1. 사용자: 프로젝트에서 “새 슬라이드 생성” 실행
2. API:

   * Run 생성(`POST /runs`)
   * 파일/템플릿/브랜드/정책 snapshot 저장
3. Workflow:

   * Step A: Retrieval(업로드 파일 기반 근거 수집)
   * Step B: Outline 생성 → (옵션) 사용자 승인
   * Step C: SlideSpec 생성
   * Step D: Rendering(PPTX) + Preview 생성
   * Step E: Quality Check → 필요시 Fix Layout 루프
4. 결과:

   * Artifact 저장(S3)
   * UI는 썸네일/미리보기 표시
   * 사용자는 “부분 재생성” 가능

### 4.5.2 “부분 재생성” 설계 포인트

* Run lineage 기록:

  * 어떤 artifact_version이 어떤 run에서 생성됐는지
  * 어떤 슬라이드/섹션을 재생성했는지 diff 기록
* 재생성 범위:

  * “한 슬라이드만 재생성”은 주변 슬라이드의 스타일/내러티브 일관성이 중요
    → context window로 이전/다음 슬라이드 요약을 함께 입력으로 제공

---

## 4.6 API 설계(초기 MVP 기준)

### Run/Agent

* `POST /runs`

  * body: project_id, agent_id, inputs(prompt, files, template_id, options)
* `GET /runs/{run_id}`

  * status, progress, latest_step, artifacts, preview_urls
* `POST /runs/{run_id}/cancel`
* `GET /runs/{run_id}/events` (SSE/WebSocket)

  * step logs, intermediate outputs(Outline/SlidePlan)

### Files

* `POST /projects/{id}/files` (업로드 시작)
* `GET /files/{file_id}`
* `POST /files/{file_id}/index` (RAG 인덱싱 트리거)

### Templates/Brand

* `POST /templates` (pptx/docx 업로드)
* `GET /templates`
* `POST /brandkits`
* `GET /brandkits/{id}`

### Artifacts

* `GET /artifacts/{artifact_id}/download`
* `GET /artifacts/{artifact_id}/preview`

---

## 4.7 보안/권한/정책(업무용에서 빠지기 쉬운 “부족한 부분” 보완)

### 4.7.1 멀티테넌시

* 모든 테이블에 `org_id` 포함
* 스토리지 경로도 org 단위 prefix
* 기본은 논리 분리(행 수준), 엔터프라이즈는 물리 분리 옵션 가능

### 4.7.2 인증/권한

* SSO(OIDC/SAML) 옵션
* RBAC:

  * Org Admin / Project Owner / Editor / Viewer
* ABAC(정책 기반 접근):

  * “외부망 금지 프로젝트”
  * “특정 커넥터 금지”
  * “내보내기 금지” 등

### 4.7.3 감사 로그(Audit)

* Tool 실행, 파일 접근, 외부 호출, 산출물 다운로드 모두 이벤트로 기록
* 최소 필드:

  * who(user_id), when, action, target, policy_decision, run_id, ip/user_agent

### 4.7.4 데이터 보호

* 저장 시 암호화(S3 SSE/KMS 등)
* 민감정보 탐지/마스킹 옵션(PII)
* 프롬프트/근거/로그에 대한 redaction 규칙(특히 모델 호출 로그)

---

## 4.8 관측/품질/평가(플랫폼 확장에 필수)

### 4.8.1 Observability

* Trace: run_id를 trace root로
* Metrics: step별 latency, 실패율, 재시도율, 비용(토큰/호출)
* Logs: 구조화 로그(JSON) + 검색 가능

### 4.8.2 Evaluation Harness

* “샘플 입력 → 기대 결과” 테스트셋을 만들고,
* release마다 자동으로:

  * 레이아웃 오류율(겹침/오버플로우)
  * 출처 누락율
  * 금칙어 위반율
  * 사용자 수동 수정량(가능하면)
    을 추적
    → 이게 쌓여야 플랫폼이 커져도 품질이 유지됩니다.

---

# 5. 확장 설계(플랫폼화)

## 5.1 Agent Package(버전 관리 가능한 워크플로우 단위)

* `AgentPackage`는 아래를 포함:

  * input schema(폼)
  * workflow steps(에이전트/툴)
  * output schema(SlideSpec/DocSpec)
  * policy requirements(외부망 허용 여부 등)
  * eval rules(출처 필수, 레이아웃 기준 등)

### 장점

* “문서 생성 에이전트”를 제품 내에서 계속 추가/개선 가능
* 고객사별 커스터마이징을 **패키지/버전**으로 관리

## 5.2 Tool Plugin(커넥터/유틸) 확장

* 플러그인 레지스트리:

  * tool_id, permissions, input/output schema
* 실행 정책:

  * org/project 단위 allowlist
  * rate limit
  * network policy(외부 도메인 제한)

## 5.3 Template Package 확장

* PPTX/DOCX import 후 다음을 추출하여 테마 토큰화:

  * 폰트, 색상 팔레트, 마스터 레이아웃, 로고 위치 규칙
* 템플릿 버전 관리:

  * “회사 템플릿 v3.2” 같은 형태로 릴리즈

---

# 6. 기술 스택/언어 추천(구현 현실성 기준)

아래는 “문서+PPT 플랫폼”에서 실제로 개발 속도와 품질이 잘 나오는 조합입니다.

## 추천안(현실적인 1순위)

* Frontend: **TypeScript + Next.js(React)**
* Backend(API/BFF): **Python + FastAPI**
* Queue/Workflow: 초기 **Redis Queue(Celery/RQ/BullMQ)** → 성장 시 **Temporal**
* Rendering:

  * PPTX: **Node.js(TypeScript) 기반 렌더러**(템플릿/레이아웃 처리에 유리)
  * DOCX: Python(docx 계열) 또는 Node 둘 중 팀 역량에 맞춤
* Storage/DB:

  * Postgres(+pgvector)
  * S3 호환 Object Storage
  * Redis(캐시/락/레이트리밋)

**이유**

* 파이썬은 RAG/파일 처리/LLM 오케스트레이션 생태계가 강함
* PPTX는 Node 생태계가 생산성이 좋은 경우가 많아 렌더 워커를 분리하면 깔끔
* 서비스 전체는 “Run 기반”으로 관리되므로 언어 혼합에도 일관성이 유지됨

---

# 7. 단계별 구현 로드맵(설계에 맞춘 개발 순서)

## Phase 1: AI Slides MVP

* Run 서비스 + 워커 + PPTX 렌더링
* Outline → SlideSpec → PPTX 생성
* 템플릿 3종 + 브랜드 토큰 최소 적용
* 레이아웃 체크(오버플로우/겹침) + Fix 루프

## Phase 2: RAG + 출처

* 파일 인덱싱 파이프라인
* citations 모델링
* 숫자/주장에 출처 요구 정책

## Phase 3: 편집/부분 재생성/버전

* 슬라이드 단위 재생성
* artifact versioning + diff
* 프리뷰/다운로드 안정화

## Phase 4: AI Docs

* DocSpec + DOCX/PDF 렌더링
* 보고서 템플릿/스타일

## Phase 5: Agent Builder(플랫폼화)

* AgentPackage/ToolPlugin 레지스트리
* 테스트/평가 harness
* 정책/권한 고도화

