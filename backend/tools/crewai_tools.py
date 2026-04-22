"""
CrewAI-native tool wrappers.
These wrap the existing ML models for use with CrewAI agents.
"""
import json
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from crewai.tools import tool as crewai_tool
from logger import get_logger, log_action

logger = get_logger("crewai_tools")


@crewai_tool("loan_risk_scorer")
def loan_risk_scorer(annual_income: float, credit_score: int, age: int,
                     existing_emi: float, loan_amount: float,
                     loan_type: str = "personal_loan") -> str:
    """Score loan default risk using the Indian Loan Risk Model.

    Args:
        annual_income:  Annual income in INR (e.g. 600000)
        credit_score:   CIBIL score 300-900 (e.g. 720)
        age:            Borrower age in years (e.g. 32)
        existing_emi:   Current monthly EMI obligations in INR (e.g. 15000)
        loan_amount:    Requested loan amount in INR (e.g. 500000)
        loan_type:      Loan type: home_loan / personal_loan / car_loan / business_loan

    Returns:
        JSON with risk_score (0-1), risk_tier (Low/Medium/High), explanation
    """
    from ml_models.fraud_detector import loan_risk_detector
    log_action(logger, "info", "crewai_tools", "TOOL_CALLED",
               f"tool=loan_risk_scorer | income={annual_income} | score={credit_score} | "
               f"loan={loan_amount} | type={loan_type}")

    profile = {
        "annual_income":      max(float(annual_income), 0),
        "credit_score":       max(int(credit_score), 300),
        "age":                max(int(age), 18),
        "existing_emi_amount": max(float(existing_emi), 0),
        "credit_utilization": 30,  # default — not usually available from message
    }
    result = loan_risk_detector.predict(
        user_profile=profile,
        loan_amount=float(loan_amount),
        loan_type=loan_type,
    )
    return json.dumps(result, indent=2)

# Backwards-compatible alias
fraud_risk_scorer = loan_risk_scorer



@crewai_tool("emi_calculator")
def emi_calculator(principal: float, annual_rate_percent: float, tenure_months: int) -> str:
    """Calculate EMI (Equated Monthly Installment) for a loan.
    
    Args:
        principal: Loan amount in INR (e.g. 5000000)
        annual_rate_percent: Annual interest rate percentage (e.g. 8.5)
        tenure_months: Loan tenure in months (e.g. 240)
    
    Returns:
        JSON with monthly_emi, total_interest, total_repayment
    """
    from ml_models.emi_calculator import calculate_emi
    log_action(logger, "info", "crewai_tools", "TOOL_CALLED",
               f"tool=emi_calculator | P={principal} R={annual_rate_percent} T={tenure_months}")
    
    result = calculate_emi(principal, annual_rate_percent, tenure_months)
    return json.dumps(result, indent=2)


@crewai_tool("rate_predictor")
def rate_predictor(loan_type: str, credit_score: int | str) -> str:
    """Predict interest rate range for a loan type based on credit score.
    
    Args:
        loan_type: Type of loan (home_loan, personal_loan, car_loan, business_loan, education_loan)
        credit_score: Borrower's credit score (300-900)
    
    Returns:
        JSON with min_rate, max_rate, personalized_rate, providers
    """
    from ml_models.rate_predictor import predict_rate
    log_action(logger, "info", "crewai_tools", "TOOL_CALLED",
               f"tool=rate_predictor | type={loan_type} score={credit_score}")
    
    result = predict_rate(loan_type, int(credit_score))
    return json.dumps(result, indent=2)


@crewai_tool("policy_search")
def policy_search(query: str) -> str:
    """Search RBI policy documents, PMAY guidelines, MUDRA scheme info, and other financial policies.
    
    Args:
        query: Search query about financial policies or government schemes
    
    Returns:
        Relevant policy excerpts with source attribution
    """
    from rag.pipeline import rag_pipeline
    log_action(logger, "info", "crewai_tools", "TOOL_CALLED",
               f"tool=policy_search | query={query[:60]}")
    
    results = rag_pipeline.search(query, top_k=3)
    output_parts = []
    for r in results:
        source = r["source"].replace("_", " ").replace(".txt", "").title()
        output_parts.append(f"[{source}] (relevance: {r['score']:.0%})\n{r['text'][:400]}")
    
    return "\n---\n".join(output_parts) if output_parts else "No relevant policy information found."
