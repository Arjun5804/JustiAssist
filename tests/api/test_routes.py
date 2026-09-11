from app import app

EXPECTED_ROUTES = {
    # Auth
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/signup"),
    ("GET", "/api/auth/me"),
    
    # Query (RAG)
    ("POST", "/api/v2/query"),
    ("GET", "/api/v2/query/stream"),
    ("POST", "/query"),  # Legacy
    
    # Documents
    ("POST", "/upload-document"),
    ("GET", "/session/{session_id}/documents"),
    ("DELETE", "/session/{session_id}/documents"),
    
    # Features
    ("POST", "/api/predict/case"),
    ("POST", "/api/counter-arguments"),
    
    # Admin / System
    ("GET", "/health"),
    ("GET", "/stats"),
    ("POST", "/build-indices"),
    ("GET", "/api/news"),
    
    # Kanoon
    ("GET", "/api/kanoon/search"),
    ("GET", "/api/kanoon/doc/{doc_id}"),
}

def test_critical_routes_registered():
    """Verify that all critical endpoints from Phase 0B are still registered."""
    registered_routes = set()
    
    for route in app.routes:
        if hasattr(route, 'methods') and route.methods:
            for method in route.methods:
                if method != "HEAD":
                    registered_routes.add((method, route.path))
                    
    missing_routes = EXPECTED_ROUTES - registered_routes
    
    assert not missing_routes, f"Missing critical routes: {missing_routes}"
