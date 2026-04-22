"""
Main FastAPI application — entry point for the Agentic AI Loan & Credit Advisor.
"""
import os
import sys
import time
from contextlib import asynccontextmanager

# Ensure backend dir is in path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import settings
from logger import get_logger, log_action

logger = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    log_action(logger, "info", "main", "APP_STARTING", "Initializing Agentic AI Loan & Credit Advisor")

    # Load Indian Loan Risk Model (pre-trained, no retraining needed at startup)
    try:
        from ml_models.fraud_detector import loan_risk_detector
        log_action(logger, "info", "main", "LOAN_RISK_MODEL_READY",
                   f"trained={loan_risk_detector.is_trained} | model=xgboost_indian_loan")
    except Exception as e:
        log_action(logger, "error", "main", "LOAN_RISK_MODEL_FAILED", f"error={str(e)}")

    # Build RAG index if needed
    try:
        from rag.pipeline import rag_pipeline
        rag_pipeline.ingest_documents()
        log_action(logger, "info", "main", "RAG_PIPELINE_READY",
                   f"chunks={len(rag_pipeline.chunks)} | index_size={rag_pipeline.index.ntotal if rag_pipeline.index else 0}")
    except Exception as e:
        log_action(logger, "error", "main", "RAG_INIT_FAILED", f"error={str(e)}")

    # Initialize graph
    try:
        from orchestrator.graph import orchestrator_graph
        log_action(logger, "info", "main", "ORCHESTRATOR_READY", "LangGraph orchestrator compiled")
    except Exception as e:
        log_action(logger, "error", "main", "ORCHESTRATOR_INIT_FAILED", f"error={str(e)}")

    log_action(logger, "info", "main", "APP_STARTED",
               f"CORS_ORIGINS={settings.CORS_ORIGINS} | LOG_LEVEL={settings.LOG_LEVEL}")

    yield

    log_action(logger, "info", "main", "APP_SHUTDOWN", "Application shutting down")


app = FastAPI(
    title="Agentic AI Loan & Credit Advisor",
    description="AI-powered loan eligibility assessment, credit analysis, and financial advisory system",
    version="1.0.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration = round((time.time() - start_time) * 1000, 2)

    log_action(logger, "info", "main", "HTTP_REQUEST",
               f"{request.method} {request.url.path} | status={response.status_code} | duration={duration}ms")

    return response


# Include routers
from routers.auth_router import router as auth_router
from routers.profile_router import router as profile_router
from routers.guest_router import router as guest_router
from routers.chat_router import router as chat_router
from routers.document_router import router as document_router
from routers.logs_router import router as logs_router

app.include_router(auth_router)
app.include_router(profile_router)
app.include_router(guest_router)
app.include_router(chat_router)
app.include_router(document_router)
app.include_router(logs_router)


# Health check
@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint."""
    log_action(logger, "debug", "main", "HEALTH_CHECK", "status=200")

    components = {}
    try:
        from ml_models.fraud_detector import loan_risk_detector
        components["loan_risk_model"] = "trained" if loan_risk_detector.is_trained else "not_trained"
    except:
        components["loan_risk_model"] = "error"

    try:
        from rag.pipeline import rag_pipeline
        components["rag_pipeline"] = f"{len(rag_pipeline.chunks)} chunks"
    except:
        components["rag_pipeline"] = "error"

    try:
        from auth.service import user_service
        components["chromadb"] = f"{user_service.users_collection.count()} users"
    except:
        components["chromadb"] = "error"

    return {
        "status": "healthy",
        "service": "Agentic AI Loan & Credit Advisor",
        "version": "1.0.0",
        "components": components
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
