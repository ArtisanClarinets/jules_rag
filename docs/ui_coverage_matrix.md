# UI Coverage Matrix

| Capability | Backend Source | UI Location | Inputs | Output/State | Status | Notes/Tech Debt |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Search** | `POST /api/v1/query/search` | `apps/web/src/app/page.tsx` | query, collection_name, limit, rerank | Results List | **Partial** | UI hardcodes `test_collection`, limit=10, rerank=True. Need controls. |
| **Ingest Code** | `POST /api/v1/ingest/code` -> `ingest_repo` | `apps/web/src/app/admin/ingestion/page.tsx` | repo_url, source_id, collection_name | Job Enqueued | **Partial** | UI hardcodes `test_collection`, `default_source`. Need controls. Job visibility missing. |
| **Ingest Doc** | `POST /api/v1/ingest/doc` -> `ingest_doc` | `apps/web/src/app/admin/ingestion/page.tsx` | file_path, source_id, collection_name | Job Enqueued | **Missing** | UI is placeholder. No file upload mechanism. No API call. |
| **Create Tenant** | `POST /api/v1/tenants/` | `apps/web/src/app/admin/tenants/page.tsx` | name | Tenant Object | **OK** | - |
| **List Tenants** | `GET /api/v1/tenants/` | `apps/web/src/app/admin/tenants/page.tsx` | - | List of Tenants | **OK** | - |
| **View Settings** | `GET /api/v1/settings/` | `apps/web/src/app/admin/settings/page.tsx` | - | Key/Value Dict | **Partial** | UI only looks for `opensearch_heap` and `worker_concurrency`. Hides others. |
| **Update Settings** | `POST /api/v1/settings/` | `apps/web/src/app/admin/settings/page.tsx` | dict | Restart Triggered | **Partial** | UI only sends the 2 hardcoded keys. |
| **Job Status** | `IngestionJob` (DB) | - | - | Job Status/Logs | **Missing** | No API endpoint or UI to view async worker job status. |

## Missing/Partial Items
1.  **Search**: Add controls for Collection, Limit, Rerank.
2.  **Ingestion**:
    *   Code: Add Collection and Source ID inputs.
    *   Doc: Implement File Upload and `ingest_doc` call.
    *   Jobs: Implement API and UI for job tracking.
3.  **Settings**: Make UI dynamic to handle arbitrary key/value pairs.
