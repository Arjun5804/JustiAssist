"""
JustiAssist Configuration - 2026-Ready MVP
"""
from pathlib import Path
from typing import Dict, List, Tuple, Literal
from enum import Enum
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, model_validator, SecretStr
from typing_extensions import Self


# ==================== Application Settings ====================

class Settings(BaseSettings):
    """Authoritative Application Settings"""
    
    # Application
    APP_NAME: str = "JustiAssist v2.0"
    APP_ENV: Literal["development", "production", "testing"] = "development"
    DEBUG: bool = False
    
    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    
    # Security
    JWT_SECRET_KEY: SecretStr = Field(default="justiassist-secret-change-in-production-2026")
    JWT_EXPIRY_HOURS: int = 24
    
    # Database
    DATABASE_URL: str = Field(default="sqlite:///justiassist.db")
    
    # Storage
    STORAGE_PROVIDER: Literal["local", "s3"] = "local"
    LOCAL_STORAGE_ROOT: str = ".data/storage"
    S3_ENDPOINT: str | None = None
    S3_ACCESS_KEY: SecretStr | None = None
    S3_SECRET_KEY: SecretStr | None = None
    S3_BUCKET: str | None = None
    S3_REGION: str | None = None
    
    # Caching
    REDIS_ENABLED: bool = False
    REDIS_URL: str = Field(default="redis://localhost:6379")
    REDIS_DEFAULT_TTL: int = 3600
    
    # Rate Limiting
    RATE_LIMIT_AUTH: str = "5/minute"
    RATE_LIMIT_LLM: str = "10/minute"
    RATE_LIMIT_SSE_TICKET: str = "15/minute"
    RATE_LIMIT_UPLOAD: str = "20/minute"
    RATE_LIMIT_STANDARD: str = "60/minute"
    
    # LLM (Groq Primary)
    GROQ_API_KEY: SecretStr | None = None
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    
    # LLM (Ollama Optional)
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3.2"
    
    # External APIs
    FIRECRAWL_API_KEY: SecretStr | None = None
    INDIAN_KANOON_API_KEY: SecretStr | None = None
    
    # CORS
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:8000,http://127.0.0.1:8000"
    
    # Embedding Configuration
    EMBEDDING_MODEL: str = "BAAI/bge-m3"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )
    
    @model_validator(mode="after")
    def validate_production_security(self) -> Self:
        if self.APP_ENV == "production":
            val = self.JWT_SECRET_KEY.get_secret_value() if self.JWT_SECRET_KEY else ""
            if not val or val == "justiassist-secret-change-in-production-2026":
                raise ValueError("JWT_SECRET_KEY must be set to a secure value in production.")
            if len(val) < 32:
                raise ValueError("JWT_SECRET_KEY must be at least 32 characters long in production.")
            
            if self.DATABASE_URL.startswith("sqlite"):
                raise ValueError("PostgreSQL is required in production. DATABASE_URL cannot use sqlite.")
                
        return self


# The single authoritative configuration object
settings = Settings()


# ==================== Path Configuration ====================

PROJECT_ROOT = Path(__file__).parent
DATASETS_ROOT = PROJECT_ROOT
CSV_DATASETS_PATH = DATASETS_ROOT / "data"
JSON_DATASETS_PATH = DATASETS_ROOT / "data"

# Vector store paths
VECTOR_STORE_PATH = PROJECT_ROOT / "vector_stores"
STATUTORY_INDEX_PATH = VECTOR_STORE_PATH / "statutory"
CASE_LAW_INDEX_PATH = VECTOR_STORE_PATH / "case_law"


# ==================== Dataset Classification ====================

class DatasetType(Enum):
    """Dataset content type classification"""
    STATUTORY = "statutory"      # Laws, sections, statutes
    CASE_LAW = "case_law"        # Judgments, precedents
    QA = "qa"                    # Question-answer datasets
    UNKNOWN = "unknown"


# Classification rules by filename patterns
DATASET_CLASSIFICATION_RULES = {
    # CASE_LAW patterns (checked first - more specific)
    "case_law": [
        "*_judgments*",
        "*_judgement*", 
        "*judgment*",
        "*bail_judgment*",
        "supreme_court*",
        "*_precedent*",
    ],
    # QA patterns
    "qa": [
        "*_qa*",
        "*qa_*",
        "*QA*",
        "*indiclegal*",
        "*glossary*",
    ],
    # STATUTORY patterns (default for legal content)
    "statutory": [
        "*_sections*",
        "*_dataset*",
        "*_laws*",
        "*crpc*",
        "*bns*",
        "*history*",
        "*constitution*",
        "*acts*",
        "*cpc*",
        "*civil*",
        "*commercial*",
        "*limitation*",
        "*relief*",
        "*arbitration*",
        "*labour*",
        "*property*",
        "*bail*",
        "*bnss*",
        "*bsa*",
        "*ndps*",
        "*pocso*",
        "*scst*",
        "*pmla*",
        "*uapa*",
        "*_articles*",
        "*_provisions*",
    ],
}


def classify_dataset(filename: str) -> DatasetType:
    """Classify dataset by filename pattern"""
    filename_lower = filename.lower()
    
    # Check case law first (more specific)
    for pattern in DATASET_CLASSIFICATION_RULES["case_law"]:
        pattern_lower = pattern.lower().replace("*", "")
        if pattern_lower in filename_lower:
            return DatasetType.CASE_LAW
    
    # Check QA patterns
    for pattern in DATASET_CLASSIFICATION_RULES["qa"]:
        pattern_lower = pattern.lower().replace("*", "")
        if pattern_lower in filename_lower:
            return DatasetType.QA
    
    # Check statutory patterns
    for pattern in DATASET_CLASSIFICATION_RULES["statutory"]:
        pattern_lower = pattern.lower().replace("*", "")
        if pattern_lower in filename_lower:
            return DatasetType.STATUTORY
    
    return DatasetType.UNKNOWN


def discover_datasets() -> Dict[str, List[Tuple[Path, DatasetType]]]:
    """
    Auto-discover all datasets in priority order:
    1. 'project datasets' (Full versions)
    2. 'data' (Support/Specialized versions, skipping redundant small copies)
    
    Returns dict with 'csv' and 'json' keys.
    """
    discovered = {"csv": [], "json": []}
    
    # Priority folders (Full datasets)
    PRIORITY_CSV = PROJECT_ROOT / "project datasets" / "csv datasets"
    PRIORITY_JSON = PROJECT_ROOT / "project datasets" / "json datasets"
    REGULAR_DATA = PROJECT_ROOT / "data"
    
    # Files to skip: Redundant copies, API caches, and dynamic news/live data
    REDUNDANT_FILES = {
        # Small copies of static law
        "ipc_sections_dataset.csv", "ipc_sections.csv",
        "crpc_sections_dataset.csv", "crpc_sections.csv",
        "bns_provisions.csv", "bnss_provisions.csv", "bsa_provisions.csv",
        "bail_judgments.csv", "bail_provisions.csv",
        "constitution_qa.json", "ipc_qa.json", "crpc_qa.json",
        "bail_qa.json",
        
        # Dynamic Add-ons (Fetched from APIs, should NOT be in static KB)
        "legal_news.json",
        "kanoon_results.json",
        "IndicLegalQA Dataset_10K.json" # Use Revised instead
    }
    
    print("\n--- Scanning Priority Datasets ---")
    
    # 1. Scan Priority CSV
    if PRIORITY_CSV.exists():
        for file_path in PRIORITY_CSV.glob("*.csv"):
            dtype = classify_dataset(file_path.name)
            discovered["csv"].append((file_path, dtype))
            print(f"  [PRIORITY CSV] {file_path.name} -> {dtype.value}")
            
    # 2. Scan Priority JSON
    if PRIORITY_JSON.exists():
        for file_path in PRIORITY_JSON.glob("*.json"):
            # Only use the Revised version if both exist
            if "Dataset_10K.json" in file_path.name and not "Revised" in file_path.name:
                revised_path = file_path.parent / file_path.name.replace(".json", "_Revised.json")
                if revised_path.exists():
                    print(f"  [SKIPPED] {file_path.name} (Using Revised version)")
                    continue
                    
            dtype = classify_dataset(file_path.name)
            discovered["json"].append((file_path, dtype))
            print(f"  [PRIORITY JSON] {file_path.name} -> {dtype.value}")

    print("\n--- Scanning Secondary/Unique Data ---")

    # 3. Scan regular 'data' folder for UNIQUE datasets
    if REGULAR_DATA.exists():
        # CSV
        for file_path in REGULAR_DATA.glob("*.csv"):
            if file_path.name in REDUNDANT_FILES:
                print(f"  [SKIPPED] {file_path.name} (Secondary/Duplicate copy)")
                continue
            dtype = classify_dataset(file_path.name)
            discovered["csv"].append((file_path, dtype))
            print(f"  [DATA] {file_path.name} -> {dtype.value}")
            
        # JSON
        for file_path in REGULAR_DATA.glob("*.json"):
            if file_path.name in REDUNDANT_FILES:
                print(f"  [SKIPPED] {file_path.name} (Secondary/Duplicate copy)")
                continue
            dtype = classify_dataset(file_path.name)
            discovered["json"].append((file_path, dtype))
            print(f"  [DATA] {file_path.name} -> {dtype.value}")
            
    return discovered


# ==================== Embedding Configuration ====================

class EmbeddingModel(Enum):
    """Available embedding models"""
    MINILM = "sentence-transformers/all-MiniLM-L6-v2"  # Default, fast
    BGE_M3 = "BAAI/bge-m3"  # Higher quality, slower

# Embedding selection (config-driven)
# Map backward-compatible constant to the new settings object
EMBEDDING_MODEL_NAME = settings.EMBEDDING_MODEL
EMBEDDING_MODEL = EMBEDDING_MODEL_NAME


# ==================== Domain-Aware Chunking ====================

# Chunking parameters by content type
CHUNKING_CONFIG = {
    DatasetType.STATUTORY: {
        "chunk_size": 380,      # 350-400 range
        "chunk_overlap": 65,    # 60-70 range
        "top_k": 5,
    },
    DatasetType.CASE_LAW: {
        "chunk_size": 550,      # 500-600 range
        "chunk_overlap": 100,   # 90-110 range
        "top_k": 3,
    },
    DatasetType.QA: {
        "chunk_size": 280,      # 250-300 range
        "chunk_overlap": 35,    # 30-40 range
        "top_k": 4,
    },
    DatasetType.UNKNOWN: {
        "chunk_size": 400,
        "chunk_overlap": 50,
        "top_k": 4,
    },
}

# Default chunking (backward compatibility)
CHUNK_SIZE = 400
CHUNK_OVERLAP = 50

# Retrieval configuration
# Increased for better coverage with 85K+ documents
TOP_K_STATUTORY = 15  # Up from 5
TOP_K_CASE_LAW = 10   # Up from 3
TOP_K_BAIL = 10       # Backward compatibility

# Context limits
MAX_CONTEXT_TOKENS = 3000

# Trim priority (1 = trim first, 3 = trim last)
CONTEXT_TRIM_PRIORITY = {
    "session_docs": 1,    # Trim first
    "case_law": 2,        # Trim second
    "statutory": 3,       # Trim last (never below 3 chunks)
}
MIN_STATUTORY_CHUNKS = 3


# ==================== LLM Configuration (Groq Primary) ====================

# Map old global variables to settings to preserve compatibility for existing consumers
GROQ_MODEL = settings.GROQ_MODEL
OLLAMA_BASE_URL = settings.OLLAMA_BASE_URL
OLLAMA_MODEL = settings.OLLAMA_MODEL

# LLM Parameters
LLM_TEMPERATURE = 0.3
LLM_MAX_TOKENS = 2000


# ==================== Answer Modes ====================

class AnswerMode(Enum):
    """LLM answer generation modes"""
    GROUNDED = "grounded"       # Use ONLY retrieved context
    FALLBACK = "fallback"       # Use general knowledge (labeled)


class ConfidenceLevel(Enum):
    """Confidence tiers for retrieval-grounded responses"""
    HIGH = "high"           # >= 0.75: Full grounded response
    MEDIUM = "medium"       # 0.50-0.75: Grounded with caution markers
    LOW = "low"             # 0.30-0.50: GPT-4 fallback with disclaimers
    VERY_LOW = "very_low"   # < 0.30: GPT-4 fallback with strong warnings


CONFIDENCE_THRESHOLDS = {
    ConfidenceLevel.HIGH: 0.75,
    ConfidenceLevel.MEDIUM: 0.50,
    ConfidenceLevel.LOW: 0.30,
}


def get_confidence_level(score: float) -> ConfidenceLevel:
    """Map confidence score to level"""
    if score >= CONFIDENCE_THRESHOLDS[ConfidenceLevel.HIGH]:
        return ConfidenceLevel.HIGH
    elif score >= CONFIDENCE_THRESHOLDS[ConfidenceLevel.MEDIUM]:
        return ConfidenceLevel.MEDIUM
    elif score >= CONFIDENCE_THRESHOLDS[ConfidenceLevel.LOW]:
        return ConfidenceLevel.LOW
    else:
        return ConfidenceLevel.VERY_LOW


# GPT-4 fallback labels by confidence level
FALLBACK_LABELS = {
    ConfidenceLevel.LOW: (
        "⚠️ **Limited Context Retrieved** - Using general legal knowledge to supplement.\n"
        "Some information below may be from AI training data, not retrieved sources."
    ),
    ConfidenceLevel.VERY_LOW: (
        "⚠️ **Insufficient Context Retrieved** - Primarily using general legal knowledge.\n"
        "This response draws heavily from AI training data. Please verify all information "
        "with authoritative legal sources before relying on it."
    ),
}


# Answer mode configuration
DEFAULT_ANSWER_MODE = AnswerMode.GROUNDED
RETRIEVAL_CONFIDENCE_THRESHOLD = 0.5  # Legacy - use get_confidence_level() instead

# Mode labels for responses
ANSWER_MODE_LABELS = {
    AnswerMode.GROUNDED: None,  # No label needed
    AnswerMode.FALLBACK: "⚠️ General legal knowledge (not from retrieved sources)"
}

# Insufficient context response
INSUFFICIENT_CONTEXT_RESPONSE = "Insufficient information in the provided context."


# ==================== Feedback Loop ====================

MAX_FEEDBACK_ITERATIONS = 3
CONFIDENCE_THRESHOLD = 0.7


# ==================== Logging ====================

def log_config():
    """Log current configuration for transparency"""
    print("=" * 60)
    print("JUSTIASSIST CONFIGURATION")
    print("=" * 60)
    print(f"Environment: {settings.APP_ENV}")
    print(f"Primary LLM: Groq ({settings.GROQ_MODEL})")
    print(f"Fallback LLM: Ollama ({settings.OLLAMA_MODEL})")
    print(f"Embedding Model: {settings.EMBEDDING_MODEL}")
    print(f"Max Context Tokens: {MAX_CONTEXT_TOKENS}")
    print(f"Default Answer Mode: {DEFAULT_ANSWER_MODE.value}")
    print("=" * 60)


if __name__ == "__main__":
    print("\nDiscovering datasets...")
    datasets = discover_datasets()
    print(f"\nFound {len(datasets['csv'])} CSV files, {len(datasets['json'])} JSON files")
    log_config()
