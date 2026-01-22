# Product Requirements Document: Vantus Vector Platform

**Version:** 2.0 (Next-Gen)
**Status:** Draft
**Target Release:** Q3 2025

---

## 1. Executive Summary

### 1.1 Vision
To build the world's most advanced, production-grade retrieval platform ("The Operating System for Enterprise RAG"). Vantus aims to democratize the retrieval infrastructure capabilities possessed by tech giants like Google, Meta, and OpenAI, providing a self-hosted, vendor-agnostic, and privacy-first solution that scales from a single developer to a Fortune 500 enterprise.

### 1.2 Value Proposition
*   **For CTOs:** No vendor lock-in. Run entirely on-prem or in your own VPC. Compliance ready (SOC2, HIPAA capable).
*   **For Engineers:** "It just works." Pre-configured state-of-the-art hybrid search, reranking, and ingestion pipelines.
*   **For Data Scientists:** Pluggable embedding models, evaluation frameworks, and observability built-in.

---

## 2. Technology Stack

This platform requires a cutting-edge stack designed for performance, developer experience, and long-term maintainability.

### 2.1 Frontend (The "Vantus Console")
*   **Framework:** **Next.js 16** (RC/Stable)
    *   Utilizing **App Router** for nested layouts and streaming.
    *   **Server Actions** for all data mutations.
    *   **Partial Prerendering (PPR)** for instant initial loads with dynamic shells.
*   **Library:** **React 19**
    *   **React Compiler** (No more manual `useMemo`/`useCallback`).
    *   **Server Components** by default for reduced bundle size.
    *   **Suspense** for granular loading states.
*   **Styling:** Tailwind CSS 4.0 (Oxide engine for speed).
*   **State Management:** Nuqs (URL-based state) + TanStack Query (Server state).
*   **Authentication:** **Better Auth**
    *   Features: Passkeys, 2FA, Magic Links, Social Logins, SSO (SAML/OIDC) for Enterprise.
    *   Session Management: Secure, HTTP-only cookies.

### 2.2 Backend (The "Vantus Core")
*   **API Layer:** **FastAPI** (Python 3.12+)
    *   Async architecture.
    *   Pydantic V2 for high-performance validation.
    *   OpenAPI 3.1 generation.
*   **Worker Layer:** **Arq** (Redis-backed job queue)
    *   Handling long-running tasks: Ingestion, OCR, Re-indexing.
*   **Orchestration:** Docker Compose (Dev/Single-node) / Kubernetes (Helm Charts provided).

### 2.3 Data Infrastructure (Production Ready)
*   **Metadata Store:** **PostgreSQL 16+**
    *   Relational data: Tenants, Users, Document Metadata, API Keys.
    *   JSONB support for flexible metadata schemas.
*   **Vector Store:** **Qdrant** (Distributed Mode)
    *   HNSW index for dense vectors.
    *   Payload filtering for RBAC and metadata filtering.
    *   Snapshot/Restore capabilities.
*   **Sparse/Lexical Store:** **OpenSearch**
    *   BM25 implementation for keyword search.
    *   Exact matching for technical terms/IDs.
*   **Object Storage:** **MinIO** (S3 Compatible)
    *   Storing raw documents (PDFs, Images), parsed chunks, and backups.
*   **Caching & Queues:** **Redis 7**

---

## 3. Core Capabilities & Feature Requirements

### 3.1 Ingestion Engine ("Vantus Ingest")
A modular, DAG-based ingestion pipeline.

*   **Multi-Source Connectors:**
    *   **File Upload:** PDF, DOCX, TXT, MD, CSV, PPTX.
    *   **Code Repositories:** GitHub, GitLab (Tree-sitter based semantic chunking).
    *   **Web:** Recursive crawler, Sitemap ingestion.
    *   **SaaS:** Slack, Notion, Google Drive, Confluence.
*   **Processing Pipeline:**
    *   **Unstructured Data:** Integrated OCR (Tesseract/Surya/PaddleOCR) for scanned PDFs.
    *   **Image Understanding:** VLM (Vision Language Model) support for captioning images.
    *   **Chunking:**
        *   Fixed Size (Token/Character).
        *   Recursive Character.
        *   **Semantic Chunking:** Break by meaning using embedding similarity.
        *   **Agentic Chunking:** Using LLM to verify chunk coherence.
    *   **PII Redaction:** Microsoft Presidio integration to mask sensitive data before storage.

### 3.2 Retrieval Engine ("Vantus Search")
A state-of-the-art retrieval pipeline superior to vanilla vector search.

*   **Hybrid Search:**
    *   Combine Dense (Qdrant) and Sparse (OpenSearch/BM25) scores.
    *   **Reciprocal Rank Fusion (RRF):** Algorithm to merge ranked lists normalized by rank.
*   **Query Expansion:**
    *   **Hypothetical Document Embeddings (HyDE):** Generate an answer, embed it, search for similar ground truth.
    *   **Multi-Query:** Break complex queries into sub-questions.
*   **Reranking:**
    *   Cross-Encoder integration (Cohere Rerank or Local BGE-Reranker) to re-score top-K results.
*   **Graph RAG (Advanced):**
    *   Extract entities and relationships during ingestion.
    *   Traverse knowledge graph for "multi-hop" reasoning questions.
*   **Context Assembly:**
    *   Token-budget aware context window construction.
    *   Source citation tracking (File path, page number, line range).

### 3.3 Management Plane
*   **Multi-Tenancy:**
    *   Logical isolation of data per "Tenant" or "Project".
    *   Usage quotas per tenant (Storage limits, Request limits).
*   **API Management:**
    *   Issue scoped API Keys (Read-only, Write-only, Admin).
    *   Rate limiting per key.
*   **RBAC (Role-Based Access Control):**
    *   Roles: Owner, Admin, Editor, Viewer.
    *   Document-level security (User X can only retrieve docs matching `access_group=X`).

### 3.4 Observability & Evaluation
*   **Traceability:** OpenTelemetry instrumentation for every request.
*   **Feedback Loop:** "Thumbs up/down" API for capturing user feedback on retrieval quality.
*   **Evaluation Dashboard:**
    *   Golden Dataset management.
    *   Automated metrics: Context Precision, Context Recall, Faithfulness (using Ragas).
    *   Latency p95/p99 tracking.

---

## 4. Site Map (Frontend Architecture)

### 4.1 Authentication Flow (`/auth/*`)
*   `/auth/login`: Email/Password, Socials (Google/GitHub), Passkey.
*   `/auth/register`: Org creation flow.
*   `/auth/sso`: Enterprise SAML login.

### 4.2 Application Shell (Layout)
*   Sidebar Navigation.
*   Tenant Switcher.
*   User Profile / Settings.

### 4.3 Dashboard (`/`)
*   **Metrics Cards:** Total Documents, Total Vectors, API Calls (24h), Storage Used.
*   **System Health:** Status of Qdrant, Redis, Workers.
*   **Recent Activity Stream.**

### 4.4 Data Explorer (`/data`)
*   **`/data/collections`**: List vector collections.
*   **`/data/browser`**: Faceted search interface to browse indexed chunks.
    *   *Feature:* "Explain this chunk" (View vector values, payload).
*   **`/data/upload`**: Drag-and-drop ingestion wizard.

### 4.5 Playground (`/playground`)
*   **Interactive Chat:** Test RAG pipelines in real-time.
*   **Configuration Panel:** Adjust `top_k`, `temperature`, `reranker_enabled`, `system_prompt`.
*   **Debug View:** See intermediate steps (Raw Search Results -> Reranked Results -> LLM Context).

### 4.6 Developers (`/developers`)
*   **`/developers/api-keys`**: Create/Revoke keys.
*   **`/developers/webhooks`**: Configure callbacks for ingestion events.
*   **`/developers/docs`**: Embedded OpenAPI Swagger UI.

### 4.7 Settings (`/settings`)
*   **General:** Branding, Timezone.
*   **Team:** Invite members, Manage Roles.
*   **Models:** Configure Embedding Models (Ollama, OpenAI, HuggingFace) and LLMs.
*   **Billing:** Stripe integration for Enterprise usage.

---

## 5. Non-Functional Requirements

### 5.1 Performance
*   **Latency:**
    *   Simple Vector Search: < 50ms (p95).
    *   Hybrid + Rerank: < 200ms (p95).
    *   Ingestion: < 5s per page for PDF processing.
*   **Throughput:** 100 concurrent queries per second (single node baseline).

### 5.2 Scalability
*   **Horizontal Scaling:**
    *   Stateless API layer scales via Kubernetes HPA.
    *   Worker layer scales based on Redis queue depth.
    *   Qdrant scales via Sharding.
*   **Storage:** Support for 100M+ vectors.

### 5.3 Security
*   **Encryption:** TLS 1.3 everywhere. AES-256 at rest (Postgres/MinIO/Qdrant).
*   **Secrets:** Never stored in plain text.
*   **Compliance:** Audit logs for all data access (Who accessed What and When).

---

## 6. Implementation Roadmap

### Phase 1: Foundation (Current)
*   Docker Compose setup.
*   Basic Ingestion (Text/PDF).
*   Hybrid Search (Qdrant + BM25).
*   FastAPI Backend + Basic Next.js Frontend.

### Phase 2: Next-Gen Experience (The "Vantus" Upgrade)
*   **Frontend Rewrite:** Migrate `apps/web` to Next.js 16 + React 19.
*   **Auth Migration:** Implement Better Auth.
*   **Playground 2.0:** Add Debug/Trace view.

### Phase 3: Enterprise Scale
*   **Distributed Ingestion:** Parallelize worker processing.
*   **RBAC Deep Dive:** Row-level security propagation to vector store.
*   **Connectors:** Add Slack, Notion, Drive integrations.

---

## 7. Developer Experience (DX)

### 7.1 Local Development
*   `make dev`: Starts the entire stack (CPU mode).
*   Hot Reloading for Frontend (Next.js) and Backend (FastAPI).
*   Seeding scripts to populate dummy data.

### 7.2 CI/CD
*   GitHub Actions for Linting (Ruff/ESLint), Type Checking (MyPy/TypeScript), and Testing (Pytest/Playwright).
*   Automatic container builds pushed to GHCR.

---

*This document serves as the single source of truth for the Vantus Vector Platform product direction.*
