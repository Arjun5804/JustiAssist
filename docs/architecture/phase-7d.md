# Phase 7D: Object Storage for Documents

## Overview
JustiAssist has migrated its document storage mechanism from implicit local filesystem assumptions to a robust, provider-agnostic **Object Storage Abstraction**. This enables the application to store uploaded document bytes (FIRs, charge sheets, etc.) in S3-compatible object storage while keeping document metadata and ownership strictly within the PostgreSQL database.

## Architecture
```text
Authenticated User
       ↓
Document API
       ↓
Document Service
       ↓
ObjectStorage interface (core/storage.py)
       ↓
S3-compatible implementation (boto3) / LocalObjectStorage
       ↓
Object Storage (S3 / Local .data/storage)

Document Metadata
       ↓
PostgreSQL
```

## Storage Interface
The `ObjectStorage` abstraction defines the following asynchronous contract:
* `upload(key: str, data: bytes, content_type: str = None)`
* `download_to_file(key: str, destination: Path)`: Enables streaming large files to a local temp file to avoid in-memory bloat.
* `delete(key: str)`
* `exists(key: str) -> bool`

For development and testing, `LocalObjectStorage` implements this interface using a configurable local directory (`.data/storage`). For production, `S3ObjectStorage` implements this interface using `boto3` wrapped in `asyncio.to_thread` for non-blocking asynchronous execution.

## Upload Flow
The document upload process (`/upload-document`) follows a strict ordering to ensure consistency:
1. **Authentication:** The user is authenticated (`Depends(get_current_user)`). Unauthenticated uploads are rejected.
2. **Validation:** The uploaded file is validated (extension and 5MB size limit).
3. **Identification:** A unique `document_id` and a safe `object_key` (`documents/{user_id}/{document_id}/{filename}`) are generated.
4. **Storage Upload:** The object is uploaded to `ObjectStorage`.
5. **Database Persistence:** The `Document` metadata is persisted to PostgreSQL. (If this fails, the previously uploaded object is deleted).
6. **Processing:** The object is downloaded to a temporary file via `download_to_file()` and processed (text extraction, vector indexing). If processing fails, the document remains stored, but the error is surfaced to the user.

## Security and Ownership
* Endpoints accessing or modifying user documents strictly require authentication.
* Documents are stored under an object key namespace that includes the `user_id` to prevent cross-tenant access.

## Dependencies Added
* `boto3`: Used for the `S3ObjectStorage` implementation.

## Database Schema
A new `Document` model was added to `services/database.py` and a corresponding Alembic migration (`17bd0743e571_add_documents_table`) was generated and applied to track:
* `id`
* `user_id`
* `session_id`
* `filename`
* `object_key`
* `upload_date`
* `content_type`
* `size_bytes`
