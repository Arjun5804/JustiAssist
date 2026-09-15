import pytest
from datetime import datetime, timezone
from services.database import Document

def test_document_to_dict():
    now = datetime.now(timezone.utc)
    doc = Document(
        id="test-doc-id-123",
        user_id=1,
        session_id="test-session-id",
        filename="test.pdf",
        object_key="documents/1/test-doc-id-123/test.pdf",
        document_type="FIR",
        content_type="application/pdf",
        file_size=1024,
        created_at=now
    )
    
    result = doc.to_dict()
    
    assert result["id"] == "test-doc-id-123"
    assert result["user_id"] == 1
    assert result["session_id"] == "test-session-id"
    assert result["filename"] == "test.pdf"
    assert result["object_key"] == "documents/1/test-doc-id-123/test.pdf"
    assert result["document_type"] == "FIR"
    assert result["content_type"] == "application/pdf"
    assert result["file_size"] == 1024
    assert result["created_at"] == now.isoformat()
    
    # Ensure no unrelated User fields exist
    assert "email" not in result
    assert "display_name" not in result
    assert "is_active" not in result
    assert "last_login" not in result
