[Web App / Editor]
   │  (REST/GraphQL, WebSocket for progress)
   ▼
[API Gateway / BFF]
   │
   ├─ Auth/RBAC/Org (SSO, roles)
   ├─ Workspace Service (projects, files, templates)
   ├─ Agent Run Service (runs, state, logs)
   └─ Billing/Quota/RateLimit

                (async jobs)
                     ▼
              [Queue / Workflow]
            (Redis+BullMQ / Celery / Temporal)

   ┌──────────────────────────────────────────────┐
   │                Worker Cluster                │
   │  - Tool Runner (web, connectors, code exec)  │
   │  - Retrieval/Indexing (RAG pipeline)         │
   │  - Artifact Renderers (PPTX/DOCX/PDF)        │
   └──────────────────────────────────────────────┘

[Postgres] (metadata, runs, templates) 
[Object Store(S3)] (uploaded files, generated artifacts)
[Vector DB(pgvector)] (embeddings, chunks)
[Redis] (cache, locks, sessions)
[Observability] (traces, prompt logs, eval)
