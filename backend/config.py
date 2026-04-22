"""
Application configuration - loads from .env file
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from backend directory
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


class Settings:
    """Application settings loaded from environment variables."""

    # API Keys
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")

    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "default_secret_key_change_me")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours

    # Paths
    BASE_DIR: Path = BASE_DIR
    CHROMADB_PATH: str = str(BASE_DIR / os.getenv("CHROMADB_PATH", "./chromadb_storage"))
    FAISS_PATH: str = str(BASE_DIR / os.getenv("FAISS_PATH", "./rag/faiss_index"))
    MODEL_SAVE_PATH: str = str(BASE_DIR / os.getenv("MODEL_SAVE_PATH", "./ml_models/saved"))
    UPLOAD_DIR: str = str(BASE_DIR / os.getenv("UPLOAD_DIR", "./uploads"))
    DATA_DIR: str = str(BASE_DIR / "data")
    RAG_DOCS_DIR: str = str(BASE_DIR / "rag" / "documents")
    LOG_DIR: str = str(BASE_DIR / "logs")

    # CORS
    CORS_ORIGINS: list = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")

    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "DEBUG")

    # ML Models — Indian Loan Risk (XGBoost, trained on Indian loan data)
    LOAN_RISK_MODEL_FILE:  str = "loan_risk_model.joblib"
    LOAN_RISK_SCALER_FILE: str = "loan_risk_scaler.joblib"
    LOAN_RISK_FEATURES_FILE: str = "loan_risk_features.joblib"

    # RAG
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
    CHUNK_SIZE: int = 600
    CHUNK_OVERLAP: int = 100
    RAG_TOP_K: int = 5

    # LLM Models
    CREDIT_ANALYST_MODEL: str = "llama-3.1-8b-instant"
    LOAN_ADVISOR_MODEL: str = "llama-3.3-70b-versatile"
    RISK_COMPLIANCE_MODEL: str = "llama-3.3-70b-versatile"
    INTENT_CLASSIFIER_MODEL: str = "llama-3.1-8b-instant"


settings = Settings()

# Ensure directories exist
for dir_path in [settings.CHROMADB_PATH, settings.FAISS_PATH, settings.MODEL_SAVE_PATH,
                 settings.UPLOAD_DIR, settings.DATA_DIR, settings.RAG_DOCS_DIR, settings.LOG_DIR]:
    os.makedirs(dir_path, exist_ok=True)
