import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch, MagicMock
from app import app
from services.database import get_db_session, Document, User
from services.auth import create_access_token
from agents.query_classifier import QueryType
import uuid

@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture
def test_user():
    db = get_db_session()
    user_id = 1000
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        u = User(id=user_id, email="doc_user@test.com", display_name="Doc User", hashed_password="pw")
        db.add(u)
        db.commit()
    db.close()
    return u

@pytest.fixture
def auth_headers(test_user):
    token = create_access_token(test_user.id, test_user.email)
    return {"Authorization": f"Bearer {token}"}

@pytest.fixture
def mock_storage():
    with patch("api.documents.storage") as mock:
        mock.upload = AsyncMock()
        mock.download_to_file = AsyncMock()
        mock.delete = AsyncMock()
        mock.exists = AsyncMock(return_value=True)
        # For streaming, we can mock it to return a basic async generator
        async def mock_stream(*args, **kwargs):
            yield b"test content"
        mock.stream = mock_stream
        yield mock

def test_upload_document_success(client, auth_headers, mock_storage):
    # We also mock extract_text_from_file and deps to avoid real extraction and ML calls
    with patch("api.documents.extract_text_from_file", return_value="Extracted text"), \
         patch("api.documents.deps.query_classifier") as mock_classifier, \
         patch("api.documents.deps.query_reformulator") as mock_reformulator, \
         patch("api.documents.deps.feedback_evaluator") as mock_evaluator, \
         patch("api.documents.call_llm", new_callable=AsyncMock) as mock_call_llm:
        
        mock_classification = MagicMock()
        mock_classification.query_type = QueryType.LEGAL_INFO
        mock_classifier.classify = AsyncMock(return_value=mock_classification)
        mock_reformulated = MagicMock()
        mock_reformulated.enhanced_query = "reformulated test query"
        mock_reformulator.reformulate = MagicMock(return_value=mock_reformulated)
        
        mock_evaluator.evaluate = MagicMock()
        mock_call_llm.return_value = "Mocked LLM answer"
        
        files = {"file": ("test_doc.txt", b"Hello World", "text/plain")}
        data = {"query": "test query", "mode": "auto", "document_type": "OTHER"}
        
        response = client.post("/upload-document", files=files, data=data, headers=auth_headers)
        
        assert response.status_code == 200, response.text
        res_data = response.json()
        assert res_data["document_name"] == "test_doc.txt"
        
        # Verify storage was called
        mock_storage.upload.assert_called_once()
        
        # Verify DB persistence
        db = get_db_session()
        doc = db.query(Document).filter(Document.session_id == res_data["session_id"]).first()
        assert doc is not None
        assert doc.filename == "test_doc.txt"
        db.close()

def test_upload_document_storage_failure(client, auth_headers, mock_storage):
    # ObjectStorage upload fails -> No DB metadata should be created
    mock_storage.upload.side_effect = Exception("S3 bucket down")
    
    files = {"file": ("fail_storage.txt", b"Hello World", "text/plain")}
    data = {"query": "test query", "mode": "auto"}
    
    response = client.post("/upload-document", files=files, data=data, headers=auth_headers)
    assert response.status_code == 500
    assert "S3 bucket down" in response.text
    
    # Verify no DB records
    db = get_db_session()
    docs = db.query(Document).filter(Document.filename == "fail_storage.txt").all()
    assert len(docs) == 0
    db.close()

def test_upload_document_db_failure(client, auth_headers, mock_storage):
    # DB persistence fails -> Storage object should be deleted
    with patch("api.documents.get_db_session") as mock_db:
        mock_session = MagicMock()
        mock_session.commit.side_effect = Exception("DB connection lost")
        mock_db.return_value = mock_session
        
        files = {"file": ("fail_db.txt", b"Hello World", "text/plain")}
        data = {"query": "test query", "mode": "auto"}
        
        response = client.post("/upload-document", files=files, data=data, headers=auth_headers)
        assert response.status_code == 500
        assert "DB connection lost" in response.text
        
        # Verify rollback was attempted on storage
        mock_storage.delete.assert_called_once()

def test_upload_document_processing_failure(client, auth_headers, mock_storage):
    # Object uploaded, DB persisted, but processing (download_to_file/extract) fails
    mock_storage.download_to_file.side_effect = Exception("Download corrupted")
    
    files = {"file": ("fail_proc.txt", b"Hello World", "text/plain")}
    data = {"query": "test query", "mode": "auto"}
    
    response = client.post("/upload-document", files=files, data=data, headers=auth_headers)
    
    # Should report 422 processing failure
    assert response.status_code == 422
    assert "Document stored, but processing failed" in response.text
    
    # Verify DB record WAS persisted and not deleted
    db = get_db_session()
    doc = db.query(Document).filter(Document.filename == "fail_proc.txt").first()
    assert doc is not None
    db.close()

def test_document_download_and_ownership(client, auth_headers, mock_storage, test_user):
    # Create a dummy document
    db = get_db_session()
    session_id = str(uuid.uuid4())
    doc_id = str(uuid.uuid4())
    doc = Document(
        id=doc_id,
        user_id=test_user.id,
        session_id=session_id,
        filename="own_doc.txt",
        object_key=f"documents/{uuid.uuid4()}/own_doc.txt",
        document_type="OTHER",
        content_type="text/plain",
        file_size=10
    )
    db.add(doc)
    
    other_doc_id = str(uuid.uuid4())
    other_doc = Document(
        id=other_doc_id,
        user_id=9999, # Another user
        session_id=session_id,
        filename="other_doc.txt",
        object_key=f"documents/{uuid.uuid4()}/other_doc.txt",
        document_type="OTHER",
        content_type="text/plain",
        file_size=10
    )
    db.add(other_doc)
    db.commit()
    db.close()
    
    # Download own document (Success)
    resp = client.get(f"/session/{session_id}/document/{doc_id}/download", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.content == b"test content"
    
    # Download other user's document (403 Forbidden)
    resp = client.get(f"/session/{session_id}/document/{other_doc_id}/download", headers=auth_headers)
    assert resp.status_code == 403
