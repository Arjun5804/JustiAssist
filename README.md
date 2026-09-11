# JustiAssist v2.0

**Intelligent Legal AI for Indian Bail Jurisprudence**

A RAG-based legal assistant that provides grounded answers on Indian law, with specialized support for bail queries, document drafting, and real-time legal news.

---

## 🚀 Quick Start (From Scratch)

### Prerequisites

- **Python 3.10+**
- **Node.js 18+** (for React frontend)
- **API Keys**: OpenAI (GPT-4) + Groq (fallback)

### Step 1: Clone & Setup Environment

```powershell
cd "d:\project folder\justiassist"

# Create virtual environment (if not exists)
python -m venv venv

# Activate venv
.\venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
```

### Step 2: Configure Environment

```powershell
# Copy example config
copy .env.example .env

# Edit .env with your settings:
# - INDIAN_KANOON_API_KEY (optional, from api.indiankanoon.org)
# - LITELLM_MODEL (default: ollama/llama3.2)
```

### Step 3: Configure LLM (GPT-4 + Groq Fallback)

The system uses:
- **Primary**: GPT-4 (via LiteLLM)
- **Fallback**: Llama 3.1 via Groq API

```powershell
# Edit .env with your API keys:
LITELLM_MODEL=gpt-4
LITELLM_API_KEY=sk-your-openai-key
GROQ_API_KEY=gsk_your-groq-key
```

Get your Groq API key from: https://console.groq.com/keys

### Step 4: Build Vector Indices

```powershell
# Activate venv first
.\venv\Scripts\Activate.ps1

# Build indices (takes 5-15 minutes first time)
python vector_store.py
```

You should see output like:
```
=== Processing STATUTORY Documents ===
Loaded 1234 statutory documents
Created 5678 statutory chunks

=== Processing CASE LAW Documents ===
Loaded 456 case law documents
Created 2345 case law chunks

INDEX BUILDING COMPLETE
Statutory: 5678 vectors
Case Law: 2345 vectors
```

### Step 5: Start Backend

```powershell
.\venv\Scripts\Activate.ps1
python -m uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

Backend runs at: **http://localhost:8000**

### Step 6: Start Frontend

```powershell
# In a new terminal
cd frontend
npm install  # First time only
npm run dev
```

Frontend runs at: **http://localhost:3000**

---

## 📁 Project Structure

```
justiassist/
├── app.py                    # FastAPI main application
├── vector_store.py           # FAISS vector store & index building
├── config.py                 # Configuration & constants
├── llm_provider.py           # LLM integration (Ollama/OpenAI/Gemini)
├── confidence_scorer.py      # Retrieval confidence scoring
├── reranker.py               # Result reranking
├── context_builder.py        # Context construction for prompts
│
├── agents/
│   ├── query_classifier.py   # Query type classification
│   ├── query_reformulator.py # Query expansion & reformulation
│   ├── bail_evaluator.py     # Bail eligibility assessment
│   └── feedback_evaluator.py # Response quality evaluation
│
├── services/
│   ├── indian_kanoon.py      # Indian Kanoon API client
│   ├── news_scraper.py       # Legal news fetching
│   ├── document_drafter.py   # Bail application generator
│   └── pipeline_events.py    # SSE event emitter
│
├── frontend/                 # React + Vite frontend
│   ├── src/
│   │   ├── App.jsx           # Main app component
│   │   └── components/       # React components
│   └── vite.config.js        # Vite config with API proxy
│
├── data/
│   ├── bail_provisions.csv   # IPC bailability reference
│   └── bns_provisions.csv    # BNS to IPC mapping
│
├── static/                   # Legacy HTML frontend
├── vector_stores/            # FAISS indices (generated)
├── draft_templates/          # Document templates
├── prompts/                  # LLM prompt templates
└── requirements.txt          # Python dependencies
```

---

## 🔧 Debugging Guide

### Common Issues

#### 1. "No module named 'numpy'" or similar import errors

**Problem:** Running Python without activating venv.

**Solution:**
```powershell
.\venv\Scripts\Activate.ps1
python ...  # Your command
```

#### 2. "Vector store not initialized" error

**Problem:** Indices not built or not found.

**Solution:**
```powershell
.\venv\Scripts\Activate.ps1
python vector_store.py  # Rebuild indices
```

#### 3. "Ollama connection refused" error

**Problem:** Ollama server not running.

**Solution:**
```powershell
# Terminal 1
ollama serve

# Verify it's running
curl http://localhost:11434/api/tags
```

#### 4. Frontend shows blank or API errors

**Problem:** Backend not running or CORS issue.

**Solution:**
1. Ensure backend is running on port 8000
2. Check vite.config.js has correct proxy settings
3. Check browser console for specific errors

#### 5. Low confidence scores on specific section queries

**Problem:** Section not found in index.

**Debug steps:**
```powershell
.\venv\Scripts\Activate.ps1
python -c "
from vector_store import VectorStore
vs = VectorStore()
vs.load()
results = vs.search_statutory('IPC 297', k=5)
for r in results:
    print(f'{r.section_number}: {r.score:.3f}')
"
```

#### 6. Indian Kanoon API returns error

**Problem:** API key not set or invalid.

**Solution:**
1. Get API key from https://api.indiankanoon.org/
2. Add to `.env`: `INDIAN_KANOON_API_KEY=your_key`
3. Restart backend

---

## 🧪 Testing Endpoints

### Health Check
```bash
curl http://localhost:8000/health
```

### Query API
```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"query": "What is IPC 302?", "mode": "auto"}'
```

### News API
```bash
curl http://localhost:8000/api/news
```

### Bail Draft API
```bash
curl -X POST http://localhost:8000/api/draft/bail \
  -H "Content-Type: application/json" \
  -d '{
    "petitioner_name": "John Doe",
    "case_number": "FIR 123/2024",
    "offense_sections": ["IPC 420"],
    "case_facts": "The accused is charged with cheating..."
  }'
```

### Indian Kanoon Search
```bash
curl "http://localhost:8000/api/kanoon/search?query=bail%20murder"
```

---

## 📊 Monitoring

### View Metrics
```bash
curl http://localhost:8000/metrics
```

### View Statistics
```bash
curl http://localhost:8000/stats
```

### Audit Logs
Check `audit_logs/` directory for query logs and evaluations.

---

## 🔄 Rebuilding Indices

If you add new datasets or need to rebuild:

```powershell
.\venv\Scripts\Activate.ps1

# Option 1: Direct script
python vector_store.py

# Option 2: API endpoint (when server running)
curl -X POST http://localhost:8000/build-indices
```

---

## 📝 Configuration Options (.env)

```env
# LLM Provider
LITELLM_MODEL=ollama/llama3.2          # Local Ollama
# LITELLM_MODEL=gpt-4                   # OpenAI (needs OPENAI_API_KEY)
# LITELLM_MODEL=gemini/gemini-pro       # Google (needs GOOGLE_API_KEY)

# API Keys
INDIAN_KANOON_API_KEY=                  # For case law search
OPENAI_API_KEY=                         # For GPT-4 fallback
GOOGLE_API_KEY=                         # For Gemini

# Ollama
OLLAMA_BASE_URL=http://localhost:11434
```

---

## 🆘 Getting Help

1. Check `audit_logs/` for detailed error traces
2. Run with `--reload` for hot reloading during development
3. Enable debug logging in `config.py`

For architecture details, see the walkthrough documentation.
