# Vantus Architecture

## Components

1.  **Frontend (Web)**: Next.js + React + Tailwind. Serves the UI for Search Console and Admin.
2.  **Backend (API)**: FastAPI. Handles Auth, Ingestion coordination, Retrieval logic, and Settings.
3.  **Worker**: Python (Arq). Handles background ingestion tasks (Git clone, PDF parsing).
4.  **Vector DB**: Qdrant. Stores dense vectors.
5.  **Sparse DB**: OpenSearch. Stores sparse vectors (BM25) and metadata.
6.  **Storage**: MinIO. Stores raw artifacts (PDFs) and backups.
7.  **Database**: PostgreSQL. Stores relational data (Tenants, Users, Jobs).
8.  **Queue**: Redis. Task queue for Arq.
9.  **Proxy**: NGINX. TLS termination and routing.

## Retrieval Pipeline

1.  **Query**: User submits query.
2.  **Embed**: Query is embedded using configured provider (Local CPU/GPU or API).
3.  **Search**:
    *   Dense Search (Qdrant): Cosine similarity.
    *   Sparse Search (OpenSearch): BM25 match.
4.  **Fusion**: RRF (Reciprocal Rank Fusion) combines results.
5.  **Rerank**: Top K results are reranked using Cross-Encoder (Local/API).
6.  **Return**: Final results returned with citations.

## Ingestion Pipeline

1.  **Code**:
    *   Clone Repo.
    *   Parse with Tree-sitter.
    *   Chunk by function/class or sliding window.
    *   Embed and Index.
2.  **Docs**:
    *   Upload PDF.
    *   Extract Text (PyMuPDF/OCR).
    *   Chunk by page/heading.
    *   Embed and Index.
