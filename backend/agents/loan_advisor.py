"""
Loan Advisor Agent - CrewAI agent that matches credit profiles to
suitable loan products, compares options, and recommends the best fit.
"""
import json
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings
from logger import get_logger, log_action

logger = get_logger("loan_advisor")


def run_loan_advisory(credit_profile: dict, loan_type: str,
                      requested_amount: float, requested_tenure: int) -> dict:
    """
    Run loan advisory analysis — compare products and recommend best fit.
    
    Args:
        credit_profile: Output from credit analyst (includes DTI, risk_tier, etc.)
        loan_type: Type of loan requested
        requested_amount: Loan amount requested in INR
        requested_tenure: Loan tenure in months
    
    Returns:
        dict with loan comparison table and recommendation
    """
    log_action(logger, "info", "loan_advisor", "AGENT_TASK_STARTED",
               f"task=compare_loan_products | loan_type={loan_type} | "
               f"amount=₹{requested_amount:,.0f} | tenure={requested_tenure}mo")

    try:
        result = _crew_advisory(credit_profile, loan_type, requested_amount, requested_tenure)
        log_action(logger, "info", "loan_advisor", "AGENT_TASK_COMPLETE",
                   f"method=crewai | products_compared={len(result.get('products', []))}")
        return result
    except Exception as e:
        log_action(logger, "warning", "loan_advisor", "CREWAI_FALLBACK",
                   f"error={str(e)} | using deterministic advisory")
        result = _deterministic_advisory(credit_profile, loan_type, requested_amount, requested_tenure)
        log_action(logger, "info", "loan_advisor", "AGENT_TASK_COMPLETE",
                   f"method=deterministic | products_compared={len(result.get('products', []))}")
        return result


def _crew_advisory(credit_profile: dict, loan_type: str,
                   requested_amount: float, requested_tenure: int) -> dict:
    """Run advisory using CrewAI agent with Groq LLM."""
    from crewai import Agent, Task, Crew
    from tools.crewai_tools import emi_calculator, rate_predictor

    log_action(logger, "info", "loan_advisor", "AGENT_INITIALIZED",
               f"agent=loan_advisor | model={settings.LOAN_ADVISOR_MODEL}")

    advisor_agent = Agent(
        role="Senior Loan Product Advisor",
        goal="Compare loan products and recommend the best option for the borrower",
        backstory="""You are a senior loan product specialist at India's top financial advisory firm.
        You have deep knowledge of loan products from all major Indian banks including SBI, HDFC, ICICI, 
        Kotak, and Axis Bank. You compare EMIs, total costs, and eligibility requirements to find the 
        best match for each borrower's profile. You always provide clear comparison tables.""",
        tools=[emi_calculator, rate_predictor],
        llm=f"groq/{settings.LOAN_ADVISOR_MODEL}",
        verbose=False,
        allow_delegation=False,
    )

    advisory_task = Task(
        description=f"""Compare loan products for this borrower:

        BORROWER PROFILE:
        - Risk Tier: {credit_profile.get('risk_tier', 'Medium')}
        - Credit Tier: {credit_profile.get('credit_tier', 'Good')}
        - DTI Ratio: {credit_profile.get('dti_ratio', 0)}%
        - Max EMI Capacity: ₹{credit_profile.get('max_emi_capacity', 0):,.0f}/month
        - Monthly Income: ₹{credit_profile.get('monthly_income', 0):,.0f}

        LOAN REQUEST:
        - Type: {loan_type}
        - Amount: ₹{requested_amount:,.0f}
        - Tenure: {requested_tenure} months

        Use the rate predictor tool to get rate bands for {loan_type}.
        Use the EMI calculator tool to calculate EMIs at different rates.
        
        Compare at least 3 options (best case, average case, and a shorter tenure option).
        
        Provide response as JSON with:
        - products (list of objects with: bank_name, rate, emi, total_interest, total_cost, tenure_months, pros, cons)
        - recommendation (string - which product and why)
        - affordability_verdict (string - whether borrower can afford the requested loan)
        """,
        expected_output="A JSON comparison of loan products with recommendation",
        agent=advisor_agent
    )

    crew = Crew(agents=[advisor_agent], tasks=[advisory_task], verbose=False)
    result = crew.kickoff()
    return _parse_advisory_output(str(result), credit_profile, loan_type, requested_amount, requested_tenure)


def _deterministic_advisory(credit_profile: dict, loan_type: str,
                            requested_amount: float, requested_tenure: int) -> dict:
    """Fallback deterministic loan advisory."""
    from ml_models.emi_calculator import calculate_emi
    from ml_models.rate_predictor import predict_rate

    rate_info = predict_rate(loan_type, credit_profile.get("credit_score", 700) if "credit_score" in credit_profile else 700)

    if "error" in rate_info:
        rate_info = {"min_rate": 9.0, "max_rate": 14.0, "avg_rate": 10.5, "personalized_rate": 10.5}

    # Create 3 product comparisons
    products = []
    provider_rates = rate_info.get("provider_rates", [])

    if len(provider_rates) >= 3:
        provider_rates = sorted(provider_rates, key=lambda x: x["rate"])
        
        # Best case
        best_p = provider_rates[0]
        best_emi = calculate_emi(requested_amount, best_p["rate"], requested_tenure)
        products.append({
            "bank_name": best_p["name"],
            "rate": best_p["rate"],
            "emi": best_emi["monthly_emi"],
            "total_interest": best_emi["total_interest"],
            "total_cost": best_emi["total_repayment"],
            "tenure_months": requested_tenure,
            "pros": ["Lowest interest rate", "Minimum total interest payable"],
            "cons": ["Stricter documentation"]
        })

        # Average case
        avg_p = provider_rates[1]
        avg_emi = calculate_emi(requested_amount, avg_p["rate"], requested_tenure)
        products.append({
            "bank_name": avg_p["name"],
            "rate": avg_p["rate"],
            "emi": avg_emi["monthly_emi"],
            "total_interest": avg_emi["total_interest"],
            "total_cost": avg_emi["total_repayment"],
            "tenure_months": requested_tenure,
            "pros": ["Faster processing", "Balanced terms"],
            "cons": ["Slightly higher interest rate"]
        })

        # Short tenure / Premium case
        prem_p = provider_rates[2]
        short_tenure = max(12, int(requested_tenure * 0.5))
        short_emi = calculate_emi(requested_amount, prem_p["rate"], short_tenure)
        products.append({
            "bank_name": prem_p["name"],
            "rate": prem_p["rate"],
            "emi": short_emi["monthly_emi"],
            "total_interest": short_emi["total_interest"],
            "total_cost": short_emi["total_repayment"],
            "tenure_months": short_tenure,
            "pros": ["Lower total interest", "Faster loan closure"],
            "cons": ["Higher monthly EMI"]
        })
    else:
        # Extreme Fallback
        best_rate = rate_info.get("min_rate", 8.5)
        avg_rate = rate_info.get("personalized_rate", rate_info.get("avg_rate", 10.0))
        best_emi = calculate_emi(requested_amount, best_rate, requested_tenure)
        avg_emi = calculate_emi(requested_amount, avg_rate, requested_tenure)
        products.append({"bank_name": "Standard Option A", "rate": best_rate, "emi": best_emi["monthly_emi"], "total_interest": best_emi["total_interest"], "total_cost": best_emi["total_repayment"], "tenure_months": requested_tenure, "pros": ["Good rates"], "cons": []})
        products.append({"bank_name": "Standard Option B", "rate": avg_rate, "emi": avg_emi["monthly_emi"], "total_interest": avg_emi["total_interest"], "total_cost": avg_emi["total_repayment"], "tenure_months": requested_tenure, "pros": ["Flexible"], "cons": []})
        
        short_tenure = max(12, int(requested_tenure * 0.5))
        short_emi = calculate_emi(requested_amount, avg_rate, short_tenure)
        products.append({"bank_name": "Premium Option", "rate": avg_rate + 0.5, "emi": short_emi["monthly_emi"], "total_interest": short_emi["total_interest"], "total_cost": short_emi["total_repayment"], "tenure_months": short_tenure, "pros": ["Fast processing"], "cons": []})

    # Establish standard variables for the text template regardless of the source
    best_rate = products[0]["rate"]
    best_emi_val = products[0]["emi"]
    avg_emi_val = products[1]["emi"] if len(products) > 1 else best_emi_val

    # Check affordability
    max_emi = credit_profile.get("max_emi_capacity", 0)
    affordable = avg_emi_val <= max_emi if max_emi > 0 else True

    if affordable:
        recommendation = (f"Based on your profile, we recommend the {products[0]['bank_name']} option "
                         f"at {best_rate}% with EMI of ₹{best_emi_val:,.0f}/month. "
                         f"This fits within your max EMI capacity of ₹{max_emi:,.0f}/month.")
        affordability = f"✅ Affordable. Monthly EMI (₹{avg_emi_val:,.0f}) is within your capacity (₹{max_emi:,.0f}/month)."
    else:
        recommendation = (f"The requested loan amount may stretch your finances. Consider reducing the "
                         f"amount or extending the tenure. Your max EMI capacity is ₹{max_emi:,.0f}/month "
                         f"but the average EMI would be ₹{avg_emi_val:,.0f}/month.")
        affordability = f"⚠️ Potentially unaffordable. EMI (₹{avg_emi_val:,.0f}) exceeds capacity (₹{max_emi:,.0f}/month)."

    return {
        "products": products,
        "recommendation": recommendation,
        "affordability_verdict": affordability,
        "loan_type": loan_type,
        "requested_amount": requested_amount,
        "requested_tenure": requested_tenure,
        "method": "deterministic"
    }


def _parse_advisory_output(result_str: str, credit_profile: dict, loan_type: str,
                           requested_amount: float, requested_tenure: int) -> dict:
    """Parse CrewAI advisory output."""
    import re
    json_match = re.search(r'\{[\s\S]*\}', result_str)
    if json_match:
        try:
            parsed = json.loads(json_match.group())
            if "products" in parsed:
                parsed["method"] = "crewai"
                return parsed
        except json.JSONDecodeError:
            pass

    det = _deterministic_advisory(credit_profile, loan_type, requested_amount, requested_tenure)
    det["llm_analysis"] = result_str[:500]
    det["method"] = "crewai_hybrid"
    return det
