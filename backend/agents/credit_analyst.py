"""
Credit Analyst Agent - CrewAI agent that analyzes credit profiles,
computes DTI, and assesses fraud risk.
"""
import json
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings
from logger import get_logger, log_action

logger = get_logger("credit_analyst")

def run_credit_analysis(user_profile: dict) -> dict:
    """
    Run credit analysis on a user profile.
    Uses CrewAI with Groq LLM when available, falls back to deterministic analysis.
    
    Args:
        user_profile: dict with income, credit_score, employment_months, etc.
    
    Returns:
        dict with credit_profile including DTI, risk_tier, analysis_summary
    """
    log_action(logger, "info", "credit_analyst", "AGENT_TASK_STARTED",
               f"task=analyze_credit_profile | income={user_profile.get('annual_income', 0)} | "
               f"credit_score={user_profile.get('credit_score', 0)}")

    try:
        result = _crew_analysis(user_profile)
        log_action(logger, "info", "credit_analyst", "AGENT_TASK_COMPLETE",
                   f"method=crewai | dti={result.get('dti_ratio', 'N/A')}% | risk_tier={result.get('risk_tier', 'N/A')}")
        return result
    except Exception as e:
        log_action(logger, "warning", "credit_analyst", "CREWAI_FALLBACK",
                   f"error={str(e)} | using deterministic analysis")
        result = _deterministic_analysis(user_profile)
        log_action(logger, "info", "credit_analyst", "AGENT_TASK_COMPLETE",
                   f"method=deterministic | dti={result.get('dti_ratio', 'N/A')}% | risk_tier={result.get('risk_tier', 'N/A')}")
        return result


def _crew_analysis(user_profile: dict) -> dict:
    """Run analysis using CrewAI agent with Groq LLM."""
    from crewai import Agent, Task, Crew
    from tools.crewai_tools import loan_risk_scorer

    loan_amount = user_profile.get("requested_amount", 100000)
    loan_type   = user_profile.get("loan_type", "personal_loan")

    log_action(logger, "info", "credit_analyst", "AGENT_INITIALIZED",
               f"agent=credit_analyst | model={settings.CREDIT_ANALYST_MODEL}")

    credit_analyst_agent = Agent(
        role="Senior Credit Analyst",
        goal="Analyze the user's credit profile thoroughly and provide a narrative assessment",
        backstory="""You are an expert credit analyst at a leading Indian bank with 15+ years of experience.
        You evaluate borrower profiles for loan applications using CIBIL scores, DTI ratios,
        employment stability, and other financial metrics. You provide clear, actionable insights.""",
        tools=[loan_risk_scorer],
        llm=f"groq/{settings.CREDIT_ANALYST_MODEL}",
        verbose=False,
        allow_delegation=False,
    )

    analysis_task = Task(
        description=f"""Assess credit risk for: 
        Income: ₹{user_profile.get('annual_income', 0):,.0f}
        Credit Score: {user_profile.get('credit_score', 0)}
        Employment: {user_profile.get('employment_months', 0)}mo
        Existing EMI: ₹{user_profile.get('existing_emi_amount', 0):,.0f}
        Requested: ₹{loan_amount:,.0f} {loan_type}
        
        Use loan_risk_scorer with the profile above.
        Return JSON: {{analysis_summary, strengths[], weaknesses[]}}""",
        expected_output="JSON with analysis_summary (2-3 sentences), strengths, weaknesses"
    )

    crew = Crew(agents=[credit_analyst_agent], tasks=[analysis_task], verbose=False)
    result = crew.kickoff()
    result_str = str(result)

    # Try to parse LLM output as JSON
    return _parse_agent_output(result_str, user_profile)


def _deterministic_analysis(user_profile: dict) -> dict:
    """Fallback deterministic credit analysis."""
    income = user_profile.get("annual_income", 0)
    monthly_income = income / 12 if income > 0 else 0
    credit_score = user_profile.get("credit_score", 0)
    employment_months = user_profile.get("employment_months", 0)
    existing_emi = user_profile.get("existing_emi_amount", 0)
    existing_loans = user_profile.get("existing_loans", 0)
    utilization = user_profile.get("credit_utilization", 0)

    # DTI calculation — rounded to 2dp
    dti_ratio = round((existing_emi * 12 / income * 100), 2) if income > 0 else 100

    # Credit tier
    if credit_score >= 750:
        credit_tier = "Excellent"
    elif credit_score >= 700:
        credit_tier = "Good"
    elif credit_score >= 650:
        credit_tier = "Fair"
    else:
        credit_tier = "Poor"

    # Risk scoring
    risk_score = 0.5
    if credit_score >= 750:
        risk_score -= 0.2
    elif credit_score >= 700:
        risk_score -= 0.1
    elif credit_score < 600:
        risk_score += 0.2

    if dti_ratio < 30:
        risk_score -= 0.1
    elif dti_ratio > 50:
        risk_score += 0.2

    if employment_months >= 36:
        risk_score -= 0.1
    elif employment_months < 12:
        risk_score += 0.1

    risk_score = max(0.05, min(0.95, risk_score))
    risk_tier = "Low" if risk_score < 0.3 else "Medium" if risk_score < 0.6 else "High"

    # Max EMI capacity (50% of monthly income minus existing EMIs)
    max_emi = max(0, monthly_income * 0.5 - existing_emi)

    # Eligibility
    eligible = credit_score >= 650 and dti_ratio < 50 and employment_months >= 12

    # Strengths and weaknesses
    strengths = []
    weaknesses = []

    if credit_score >= 700:
        strengths.append(f"Good credit score ({credit_score})")
    else:
        weaknesses.append(f"Credit score below ideal ({credit_score})")

    if dti_ratio < 36:
        strengths.append(f"Healthy DTI ratio ({dti_ratio}%)")
    elif dti_ratio > 50:
        weaknesses.append(f"High DTI ratio ({dti_ratio}%)")

    if employment_months >= 36:
        strengths.append(f"Stable employment ({employment_months // 12} years)")
    elif employment_months < 24:
        weaknesses.append(f"Short employment tenure ({employment_months} months)")

    if utilization < 30:
        strengths.append(f"Low credit utilization ({utilization}%)")
    elif utilization > 50:
        weaknesses.append(f"High credit utilization ({utilization}%)")

    if income >= 600000:
        strengths.append(f"Good annual income (₹{income:,.0f})")

    summary_parts = []
    summary_parts.append(f"Credit profile assessment: {credit_tier} with {'acceptable' if eligible else 'concerning'} risk level.")
    summary_parts.append(f"DTI ratio at {dti_ratio}% with max EMI capacity of ₹{max_emi:,.0f}/month.")
    if not eligible:
        summary_parts.append("Profile improvements needed before loan approval.")

    return {
        "dti_ratio": dti_ratio,
        "risk_tier": risk_tier,
        "risk_score": round(risk_score, 4),
        "credit_tier": credit_tier,
        "max_emi_capacity": round(max_emi, 2),
        "monthly_income": round(monthly_income, 2),
        "analysis_summary": " ".join(summary_parts),
        "strengths": strengths,
        "weaknesses": weaknesses,
        "eligible": eligible,
        "method": "deterministic"
    }


def _parse_agent_output(result_str: str, user_profile: dict) -> dict:
    """
    Parse LLM output and enforce computed fields from deterministic analysis.
    The LLM contributes: analysis_summary, strengths, weaknesses (narrative).
    The deterministic model controls: dti_ratio, risk_tier, credit_tier, eligible,
    max_emi_capacity — these are ALWAYS computed from actual profile numbers.
    """
    import re

    # Always compute the ground-truth from actual numbers
    det = _deterministic_analysis(user_profile)

    # Try to extract narrative fields from LLM output
    llm_summary = None
    llm_strengths = None
    llm_weaknesses = None

    json_match = re.search(r'\{[\s\S]*\}', result_str)
    if json_match:
        try:
            parsed = json.loads(json_match.group())
            llm_summary = parsed.get("analysis_summary")
            llm_strengths = parsed.get("strengths")
            llm_weaknesses = parsed.get("weaknesses")
        except (json.JSONDecodeError, AttributeError):
            pass

    # Build final result: all computed fields from deterministic, narrative from LLM if available
    final = {
        # These come ONLY from deterministic computation — never trust LLM for numbers
        "dti_ratio":        det["dti_ratio"],
        "risk_tier":        det["risk_tier"],
        "risk_score":       det["risk_score"],
        "credit_tier":      det["credit_tier"],
        "max_emi_capacity": det["max_emi_capacity"],
        "monthly_income":   det["monthly_income"],
        "eligible":         det["eligible"],
        "credit_score":     user_profile.get("credit_score", 0),
        # Narrative: prefer LLM, fall back to deterministic
        "analysis_summary": llm_summary or det["analysis_summary"],
        "strengths":        llm_strengths or det["strengths"],
        "weaknesses":       llm_weaknesses or det["weaknesses"],
        "method":           "crewai",
    }

    log_action(logger, "info", "credit_analyst", "DETERMINISTIC_ENFORCED",
               f"score={user_profile.get('credit_score')} | dti={det['dti_ratio']}% | "
               f"risk={det['risk_tier']} | eligible={det['eligible']}")

    return final

