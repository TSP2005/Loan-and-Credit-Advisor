"""
Guest mode router — no authentication required.
Provides EMI calculator, rate estimates, and policy search.
"""
from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import Optional
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ml_models.emi_calculator import calculate_emi
from ml_models.rate_predictor import predict_rate, get_all_rates
from rag.pipeline import rag_pipeline
from logger import get_logger, log_action

logger = get_logger("guest_router")
router = APIRouter(prefix="/guest", tags=["Guest Mode"])


class EMIRequest(BaseModel):
    principal: float = Field(..., gt=0, description="Loan amount in INR")
    annual_rate_percent: float = Field(..., gt=0, description="Annual interest rate %")
    tenure_months: int = Field(..., gt=0, description="Loan tenure in months")


class RateRequest(BaseModel):
    loan_type: str = Field(..., description="Type of loan")
    credit_score: int = Field(700, ge=300, le=900, description="Credit score")


class PolicySearchRequest(BaseModel):
    query: str = Field(..., min_length=3, description="Search query")
    top_k: int = Field(5, ge=1, le=10, description="Number of results")


@router.post("/emi-calculate")
async def calculate_emi_endpoint(request: EMIRequest):
    """Calculate EMI for given loan parameters. No login required."""
    log_action(logger, "info", "guest_router", "ENDPOINT_HIT",
               f"POST /guest/emi-calculate | P={request.principal} | R={request.annual_rate_percent}% | T={request.tenure_months}mo")

    result = calculate_emi(request.principal, request.annual_rate_percent, request.tenure_months)

    log_action(logger, "info", "guest_router", "EMI_RESULT",
               f"monthly_emi={result.get('monthly_emi', 0)}")

    return {"success": True, "data": result}


@router.post("/rate-estimate")
async def rate_estimate_endpoint(request: RateRequest):
    """Get interest rate estimates for a loan type. No login required."""
    log_action(logger, "info", "guest_router", "ENDPOINT_HIT",
               f"POST /guest/rate-estimate | loan_type={request.loan_type} | credit_score={request.credit_score}")

    result = predict_rate(request.loan_type, request.credit_score)

    return {"success": True, "data": result}


@router.get("/all-rates")
async def all_rates_endpoint(credit_score: int = 700):
    """Get rate estimates for all loan types. No login required."""
    log_action(logger, "info", "guest_router", "ENDPOINT_HIT",
               f"GET /guest/all-rates | credit_score={credit_score}")

    results = get_all_rates(credit_score)
    return {"success": True, "data": results}


@router.post("/policy-search")
async def policy_search_endpoint(request: PolicySearchRequest):
    """Search policy documents. No login required."""
    log_action(logger, "info", "guest_router", "ENDPOINT_HIT",
               f"POST /guest/policy-search | query={request.query[:80]}")

    results = rag_pipeline.search(request.query, top_k=request.top_k)

    formatted = []
    for r in results:
        formatted.append({
            "text": r["text"][:500],
            "source": r["source"],
            "score": round(r["score"], 4)
        })

    log_action(logger, "info", "guest_router", "POLICY_SEARCH_RESULT",
               f"query={request.query[:50]} | results={len(formatted)}")

    return {"success": True, "data": {"results": formatted, "total": len(formatted)}}
