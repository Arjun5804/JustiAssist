
from pathlib import Path
import tempfile
from agents.query_classifier import QueryType
from config import TOP_K_STATUTORY, TOP_K_BAIL
from prompts.templates import build_prompt_with_documents, format_document_citation
from llm_provider import call_llm
from api.query import QueryRequest

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form
from typing import Optional, List, Dict, Any
from core.dependencies import deps
from document_session import session_manager

def extract_text_from_file(file_path: Path, filename: str) -> str:
    """Extract text from uploaded file"""
    content = ""
    
    if filename.endswith('.txt'):
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    elif filename.endswith('.pdf'):
        try:
            import PyPDF2
            with open(file_path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    content += page.extract_text() + "\n"
        except ImportError:
            # Fallback if PyPDF2 not installed
            content = "[PDF extraction requires PyPDF2. Install with: pip install PyPDF2]"
        except Exception as e:
            content = f"[Error extracting PDF: {str(e)}]"
    elif filename.endswith('.docx'):
        try:
            from docx import Document
            doc = Document(str(file_path))
            paragraphs = [para.text for para in doc.paragraphs if para.text.strip()]
            content = "\n".join(paragraphs)
        except ImportError:
            content = "[DOCX extraction requires python-docx. Install with: pip install python-docx]"
        except Exception as e:
            content = f"[Error extracting DOCX: {str(e)}]"
    else:
        # Try reading as text
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        except:
            content = "[Unable to extract text from this file format]"
    
    return content

router = APIRouter()

@router.post("/upload-document")
async def upload_document(
    file: UploadFile = File(...),
    query: str = Form(...),
    mode: str = Form(default="auto"),
    session_id: str = Form(default=None),
    document_type: str = Form(default="OTHER")
):
    """
    Upload a document (FIR, charge sheet, case summary) for case-specific analysis.
    
    Documents are:
    - Parsed and chunked
    - Indexed in session-level vector store
    - Clearly marked as NON-STATUTORY evidence
    
    Documents may be used for:
    - Fact extraction
    - Case-specific reasoning
    - Bail evaluation context
    
    Documents will NEVER:
    - Override statutory law
    - Be treated as authoritative legislation
    """
    # Validate file
    allowed_extensions = ['.txt', '.pdf', '.doc', '.docx']
    file_ext = Path(file.filename).suffix.lower()
    
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Allowed: {', '.join(allowed_extensions)}"
        )
    
    # Size limit (5MB)
    max_size = 5 * 1024 * 1024
    contents = await file.read()
    if len(contents) > max_size:
        raise HTTPException(status_code=400, detail="File too large. Maximum 5MB allowed.")
    
    # Save temporarily and extract text
    with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp:
        tmp.write(contents)
        tmp_path = Path(tmp.name)
    
    try:
        document_text = extract_text_from_file(tmp_path, file.filename)
    finally:
        tmp_path.unlink()  # Clean up temp file
    
    if not document_text or len(document_text) < 10:
        raise HTTPException(status_code=400, detail="Could not extract text from document.")
    
    # Get or create session
    session = session_manager.get_or_create_session(session_id)
    
    # Add document to session (chunked and indexed)
    uploaded_doc = session.add_document(
        filename=file.filename,
        text=document_text,
        document_type=document_type
    )
    
    processing_info = {
        "steps": [
            f"Uploaded document: {file.filename}",
            f"Document type: {document_type} (NON-STATUTORY)",
            f"Created {len(uploaded_doc.chunks)} chunks",
            f"Session ID: {session.session_id}"
        ]
    }
    
    # Classify query
    if mode == "auto":
        classification = await deps.query_classifier.classify(query)
        query_type = classification.query_type
    elif mode == "bail":
        query_type = QueryType.BAIL_QUERY
    else:
        query_type = QueryType.LEGAL_INFO
    
    processing_info["steps"].append(f"Query type: {query_type.value}")
    
    # Reformulate query
    reformulated = deps.query_reformulator.reformulate(query)
    
    # Search session documents (NON-STATUTORY)
    doc_results = session.search(reformulated.enhanced_query, top_k=3)
    processing_info["steps"].append(f"Retrieved {len(doc_results)} chunks from uploaded documents")
    
    # Search statutory index (AUTHORITATIVE)
    statutory_results = deps.vector_store.search_statutory(
        reformulated.enhanced_query,
        top_k=TOP_K_STATUTORY
    ) if deps.vector_store and deps.vector_store.statutory_index else []
    processing_info["steps"].append(f"Retrieved {len(statutory_results)} statutory provisions")
    
    bail_results = []
    if query_type == QueryType.BAIL_QUERY and deps.vector_store and deps.vector_store.bail_index:
        bail_results = deps.vector_store.search_bail(
            reformulated.enhanced_query,
            top_k=TOP_K_BAIL
        )
        processing_info["steps"].append(f"Retrieved {len(bail_results)} bail precedents")
    
    # Format contexts
    statutory_context = [
        {
            "section_number": r.section_number,
            "law_type": r.law_type,
            "text": r.text,
            "source": r.source_dataset,
            "is_statutory": True,
            "is_authoritative": True
        }
        for r in statutory_results
    ]
    
    # Format document context with NON-STATUTORY markers
    document_context = [
        {
            "filename": r.filename,
            "text": r.text,
            "document_type": r.document_type,
            "is_statutory": False,  # EXPLICIT
            "is_authoritative": False,  # EXPLICIT
            "citation_prefix": r.citation_prefix
        }
        for r in doc_results
    ]
    
    bail_context = [
        {"section_number": r.section_number, "law_type": r.law_type, "text": r.text, "metadata": r.metadata}
        for r in bail_results
    ]
    
    # Build prompt with proper document handling
    if query_type == QueryType.BAIL_QUERY:
        # If document is uploaded, use enhanced document-aware prompt instead of rule-based evaluator
        if document_context:
            # Build enhanced prompt that prioritizes document analysis
            prompt = build_prompt_with_documents(
                query=query,
                statutory_context=statutory_context,
                document_context=document_context,
                bail_context=bail_context,
                is_bail_query=True
            )
            
            answer = await call_llm(prompt)
            confidence_score = 0.85  # High confidence when document is available
            
            # Create assessment from document analysis
            bail_assessment = {
                "likelihood": "See Document Analysis Above",
                "status": "Document-Based Analysis",
                "max_punishment": "See document sections",
                "severity_score": 0,
                "applicable_provisions": ["Based on uploaded document"],
                "explanation": "Analysis based on uploaded court document/FIR."
            }
        else:
            # No documents - use rule-based evaluator
            combined_context = statutory_context
            
            evaluation = await deps.bail_evaluator.evaluate(
                query=query,
                statutory_context=combined_context,
                bail_precedents=bail_context,
                custody_duration_days=None,
                offence_sections=None
            )
            
            answer = evaluation.explanation
            confidence_score = evaluation.confidence_score
            bail_assessment = evaluation.to_dict()
    else:
        # Build prompt with document constraints
        prompt = build_prompt_with_documents(
            query=query,
            statutory_context=statutory_context,
            document_context=document_context,
            bail_context=bail_context,
            is_bail_query=False
        )
        
        answer = await call_llm(prompt)
        confidence_score = 0.7
        bail_assessment = None
    
    processing_info["steps"].append("Generated response with document + statutory context")
    
    # Grounding evaluation (checks both sources)
    all_context = statutory_context + [{"text": d["text"]} for d in document_context]
    grounding_eval = deps.feedback_evaluator.evaluate(answer, all_context, query)
    
    # Format citations - STATUTORY first (authoritative), then documents
    citations = []
    
    # Statutory citations (authoritative)
    for r in statutory_results:
        citations.append({
            "section": r.section_number,
            "law_type": r.law_type,
            "text_preview": r.text[:200] + "..." if len(r.text) > 200 else r.text,
            "source": r.source_dataset,
            "relevance_score": round(r.score, 3),
            "is_authoritative": True,
            "is_statutory": True
        })
    
    # Document citations (non-statutory evidence)
    for r in doc_results:
        citations.append(format_document_citation(
            filename=r.filename,
            text_preview=r.text,
            relevance_score=r.score
        ))
    
    return {
        "query": query,
        "session_id": session.session_id,
        "document_name": file.filename,
        "document_type": document_type,
        "document_chunks": len(uploaded_doc.chunks),
        "document_preview": document_text[:500] + "..." if len(document_text) > 500 else document_text,
        "query_type": query_type.value,
        "answer": answer,
        "citations": citations,
        "confidence_score": round(confidence_score, 2),
        "bail_assessment": bail_assessment,
        "grounding_status": grounding_eval.status.value,
        "processing_info": processing_info,
        "document_notice": "⚠️ Uploaded documents are treated as case evidence, NOT statutory law. Citations clearly distinguish between authoritative legal provisions and user-uploaded evidence."
    }


@router.get("/session/{session_id}/documents")
async def list_session_documents(session_id: str):
    """List all documents in a session"""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or expired")
    
    return {
        "session_id": session_id,
        "documents": session.list_documents(),
        "total_chunks": len(session.chunk_metadata)
    }


@router.delete("/session/{session_id}/documents")
async def clear_session_documents(session_id: str):
    """Clear all documents from a session"""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or expired")
    
    doc_count = len(session.documents)
    session.clear()
    
    return {
        "session_id": session_id,
        "message": f"Cleared {doc_count} document(s) from session",
        "documents_cleared": doc_count
    }


@router.delete("/session/{session_id}/document/{document_id}")
async def delete_document(session_id: str, document_id: str):
    """Delete a specific document from session"""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or expired")
    
    if document_id not in session.documents:
        raise HTTPException(status_code=404, detail="Document not found in session")
    
    # Remove document and rebuild index
    del session.documents[document_id]
    
    # Rebuild index without deleted document chunks
    session.chunk_metadata = [c for c in session.chunk_metadata if c['document_id'] != document_id]
    
    # Rebuild FAISS index
    if session.chunk_metadata:
        session.index = None  # Reset
        texts = [c['text'] for c in session.chunk_metadata]
        model = session._get_embedding_model()
        embeddings = model.encode(texts, convert_to_numpy=True, normalize_embeddings=True).astype('float32')
        import faiss
        session.index = faiss.IndexFlatIP(session._embedding_dim)
        session.index.add(embeddings)
    else:
        session.index = None
    
    return {
        "session_id": session_id,
        "document_id": document_id,
        "message": "Document deleted successfully",
        "remaining_documents": len(session.documents)
    }


@router.post("/session/{session_id}/query")
async def query_with_session(
    session_id: str,
    request: QueryRequest
):
    """
    Query using existing session documents.
    Documents from previous uploads in this session are automatically included.
    """
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or expired")
    
    query = request.query.strip()
    
    # Classify and reformulate
    if request.mode == "auto":
        classification = await deps.query_classifier.classify(query)
        query_type = classification.query_type
    elif request.mode == "bail":
        query_type = QueryType.BAIL_QUERY
    else:
        query_type = QueryType.LEGAL_INFO
    
    reformulated = deps.query_reformulator.reformulate(query)
    
    # Search session documents
    doc_results = session.search(reformulated.enhanced_query, top_k=3)
    
    # Search statutory
    statutory_results = deps.vector_store.hybrid_search_statutory(
        reformulated.enhanced_query,
        top_k=TOP_K_STATUTORY
    ) if deps.vector_store and deps.vector_store.statutory_index else []
    
    bail_results = []
    if query_type == QueryType.BAIL_QUERY and deps.vector_store and deps.vector_store.bail_index:
        bail_results = deps.vector_store.search_bail(
            reformulated.enhanced_query,
            top_k=TOP_K_BAIL
        )
    
    # Format contexts
    statutory_context = [
        {"section_number": r.section_number, "law_type": r.law_type, "text": r.text, "source": r.source_dataset}
        for r in statutory_results
    ]
    
    document_context = [
        {"filename": r.filename, "text": r.text, "document_type": r.document_type}
        for r in doc_results
    ]
    
    # Generate response
    prompt = build_prompt_with_documents(
        query=query,
        statutory_context=statutory_context,
        document_context=document_context,
        bail_context=[{"text": r.text} for r in bail_results] if bail_results else None,
        is_bail_query=(query_type == QueryType.BAIL_QUERY)
    )
    
    answer = await call_llm(prompt)
    
    # Format citations
    citations = []
    for r in statutory_results:
        citations.append({
            "section": r.section_number,
            "law_type": r.law_type,
            "text_preview": r.text[:200] + "...",
            "is_authoritative": True
        })
    for r in doc_results:
        citations.append(format_document_citation(r.filename, r.text, r.score))
    
    return {
        "query": query,
        "session_id": session_id,
        "documents_searched": len(session.documents),
        "query_type": query_type.value,
        "answer": answer,
        "citations": citations,
        "confidence_score": 0.75
    }


