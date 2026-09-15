import pytest
import uuid
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app import app
from services.chat_memory import (
    save_message, get_history, get_recent_conversations, clear_history,
)
from services.database import get_db_session, ChatMessage
from core.exceptions import ConversationOwnershipError
from services.auth import create_access_token

@pytest.fixture(autouse=True)
def clean_db():
    db = get_db_session()
    db.query(ChatMessage).delete()
    db.commit()
    db.close()
    yield

def test_persistence_basic():
    # Save user message
    msg1 = save_message(user_id=1, role="user", content="Hello", session_id="s1")
    assert msg1.id is not None
    assert msg1.conversation_id is not None
    assert msg1.role == "user"
    assert msg1.session_id == "s1"
    
    # Save assistant message
    msg2 = save_message(
        user_id=1, role="assistant", content="Hi there",
        conversation_id=msg1.conversation_id,
        query_type="legal",
        confidence_score=0.9,
        grounding_status="pass",
        agents_used=["Agent1"],
        sources_used=["Source1"]
    )
    
    assert msg2.id is not None
    assert msg2.conversation_id == msg1.conversation_id
    assert msg2.query_type == "legal"
    assert msg2.confidence_score == 0.9
    assert msg2.grounding_status == "pass"
    assert "Agent1" in msg2.agents_used
    assert "Source1" in msg2.sources_used

def test_conversation_continuity():
    # First message generates ID
    msg1 = save_message(user_id=1, role="user", content="Q1")
    assert msg1.conversation_id is not None
    
    # Subsequent keeps ID
    msg2 = save_message(user_id=1, role="user", content="Q2", conversation_id=msg1.conversation_id)
    assert msg2.conversation_id == msg1.conversation_id
    
    # Different conversation
    msg3 = save_message(user_id=1, role="user", content="Q3")
    assert msg3.conversation_id != msg1.conversation_id

def test_isolation():
    msg_a = save_message(user_id=1, role="user", content="A")
    msg_b = save_message(user_id=2, role="user", content="B")
    
    # User 1 cannot retrieve User 2
    hist_a = get_history(user_id=1)
    assert len(hist_a) == 1
    assert hist_a[0]["content"] == "A"
    
    # Cannot retrieve B's convo by ID
    hist_b_by_a = get_history(user_id=1, conversation_id=msg_b.conversation_id)
    assert len(hist_b_by_a) == 0
    
    # Cannot save into B's convo
    with pytest.raises(ConversationOwnershipError):
        save_message(user_id=1, role="user", content="Hacked", conversation_id=msg_b.conversation_id)
        
    # Cannot delete B's history
    clear_history(user_id=1)
    hist_b = get_history(user_id=2)
    assert len(hist_b) == 1

def test_history_ordering_and_pagination():
    cid = "test-conv"
    for i in range(5):
        save_message(user_id=1, role="user", content=str(i), conversation_id=cid)
        
    hist = get_history(user_id=1, conversation_id=cid, limit=3, offset=0)
    assert len(hist) == 3
    # Ordered chronologically means newest are at the end, but the query returns descending offset.
    # Actually if we have 0,1,2,3,4. Descending limit 3 is 4,3,2. Reversed is 2,3,4
    assert [m["content"] for m in hist] == ["2", "3", "4"]
    
    hist_next = get_history(user_id=1, conversation_id=cid, limit=3, offset=3)
    assert len(hist_next) == 2
    assert [m["content"] for m in hist_next] == ["0", "1"]

def test_recent_conversations():
    import time
    save_message(user_id=1, role="user", content="Old Q", conversation_id="c1")
    time.sleep(0.1)
    save_message(user_id=1, role="user", content="New Q", conversation_id="c2")
    time.sleep(0.1)
    save_message(user_id=1, role="user", content="Old Q follow", conversation_id="c1")
    
    # Should order by last active (c1 is newer active, even though c2 was created later)
    recent = get_recent_conversations(user_id=1)
    assert len(recent) == 2
    assert recent[0]["conversation_id"] == "c1"
    assert recent[0]["preview"] == "Old Q" # The TRUE chronological first message
    assert recent[0]["message_count"] == 2
    
    assert recent[1]["conversation_id"] == "c2"
    assert recent[1]["preview"] == "New Q"

def test_transaction_rollback():
    db = get_db_session()
    count_before = db.query(ChatMessage).count()
    db.close()
    
    with patch("services.chat_memory.get_db_session") as mock_get_db:
        mock_db = MagicMock()
        mock_db.commit.side_effect = Exception("DB Error")
        mock_get_db.return_value = mock_db
        
        with pytest.raises(Exception, match="DB Error"):
            save_message(user_id=1, role="user", content="Fail")
            
        assert mock_db.rollback.called
        
def test_duplicate_suppression():
    msg1 = save_message(user_id=1, role="user", content="Dup", conversation_id="c1")
    msg2 = save_message(user_id=1, role="user", content="Dup", conversation_id="c1")
    assert msg1.id == msg2.id # Same ID due to suppression
    
    # Different role shouldn't suppress
    msg3 = save_message(user_id=1, role="assistant", content="Dup", conversation_id="c1")
    assert msg1.id != msg3.id

def test_session_id_vs_conversation_id(mock_lifespan_dependencies):
    """Explicit regression test for session_id vs conversation_id"""
    db = get_db_session()
    from services.database import User
    u = db.query(User).filter(User.id == 999).first()
    if not u:
        u = User(id=999, email="test999@test.com", display_name="Test", hashed_password="pw")
        db.add(u)
        db.commit()
    db.close()
    
    with TestClient(app) as client:
        # We need a user context for chat history to be saved
        token = create_access_token(999, "test999@test.com")
        headers = {"Authorization": f"Bearer {token}"}
        
        # We pass BOTH session_id and conversation_id
        req = {
            "query": "Test session vs convo",
            "session_id": "upload_session_99",
            "conversation_id": "thread_88"
        }
        
        # Assuming mock_lifespan_dependencies makes the agent orchestrator return a dummy response
        # Wait, the endpoint uses AgentOrchestrator, so we need to mock it.
        with patch("api.query.deps.agent_orchestrator") as mock_orchestrator:
            mock_state = MagicMock()
            mock_state.query = "Test session vs convo"
            mock_state.query_type = "legal"
            mock_state.final_answer = "Answer"
            mock_state.citations = []
            mock_state.confidence_score = 0.9
            mock_state.bail_assessment = None
            mock_state.grounding_status = "pass"
            mock_state.kanoon_cases = []
            mock_state.news_context = []
            mock_state.sources_used = []
            mock_state.processing_info = {}
            mock_state.agents_used = []
            
            from unittest.mock import AsyncMock
            mock_orchestrator.run = AsyncMock(return_value=mock_state)
            
            client.post("/query", json=req, headers=headers)
            
        hist = get_history(user_id=999, conversation_id="thread_88")
        assert len(hist) == 2 # User and assistant
        for h in hist:
            assert h["conversation_id"] == "thread_88"
            # We can't fetch session_id from API currently, so we fetch directly from DB to verify
            
        db = get_db_session()
        db_msgs = db.query(ChatMessage).filter(ChatMessage.conversation_id == "thread_88").all()
        assert len(db_msgs) == 2
        for msg in db_msgs:
            assert msg.session_id == "upload_session_99"
        db.close()
