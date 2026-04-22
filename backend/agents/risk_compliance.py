"""
Risk & Compliance Agent - CrewAI agent that validates against RBI policy,
checks government scheme eligibility, and generates improvement plans.
"""
import json
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings
from logger import get_logger, log_action

logger = get_logger("risk_compliance")


def run_compliance_check(credit_profile: dict, loan_type: str, requested_amount: float) -> dict:
    """
    Run compliance checks against RBI policy and government schemes.
    
    Args:
        credit_profile: Output from credit analyst
        loan_type: Type of loan requested
        requested_amount: Loan amount in INR
    
    Returns:
        dict with eligibility, required_docs, red_flags, scheme_eligibility, approval_likelihood
    """
    log_action(logger, "info", "risk_compliance", "AGENT_TASK_STARTED",
               f"task=compliance_check | loan_type={loan_type} | amount=₹{requested_amount:,.0f}")

    try:
        result = _crew_compliance(credit_profile, loan_type, requested_amount)
        log_action(logger, "info", "risk_compliance", "AGENT_TASK_COMPLETE",
                   f"method=crewai | eligibility={result.get('eligibility', 'unknown')}")
        return result
    except Exception as e:
        log_action(logger, "warning", "risk_compliance", "CREWAI_FALLBACK",
                   f"error={str(e)} | using deterministic compliance")
        result = _deterministic_compliance(credit_profile, loan_type, requested_amount)
        log_action(logger, "info", "risk_compliance", "AGENT_TASK_COMPLETE",
                   f"method=deterministic | eligibility={result.get('eligibility', 'unknown')}")
        return result


def _crew_compliance(credit_profile: dict, loan_type: str, requested_amount: float) -> dict:
    """Run compliance check using CrewAI agent with Groq LLM."""
    from crewai import Agent, Task, Crew
    from tools.crewai_tools import policy_search

    log_action(logger, "info", "risk_compliance", "AGENT_INITIALIZED",
               f"agent=risk_compliance | model={settings.RISK_COMPLIANCE_MODEL}")

    compliance_agent = Agent(
        role="Risk & Compliance Officer",
        goal="Validate loan application against RBI policies and government schemes, identify eligibility and red flags",
        backstory="""You are a senior risk and compliance officer at an Indian bank with expertise in 
        RBI regulations, PMAY housing scheme, MUDRA loan scheme, and all applicable government programs.
        You ensure loan applications comply with regulatory requirements and identify any red flags.
        You also check eligibility for government subsidies and schemes that could benefit the borrower.""",
        tools=[policy_search],
        llm=f"groq/{settings.RISK_COMPLIANCE_MODEL}",
        verbose=False,
        allow_delegation=False,
    )

    compliance_task = Task(
        description=f"""Perform compliance check for this loan application:

        CREDIT PROFILE:
        - Risk Tier: {credit_profile.get('risk_tier', 'Medium')}
        - DTI Ratio: {credit_profile.get('dti_ratio', 0)}%
        - Credit Score (tier): {credit_profile.get('credit_tier', 'Unknown')}
        - Eligible (basic): {credit_profile.get('eligible', False)}

        LOAN APPLICATION:
        - Type: {loan_type}
        - Amount: ₹{requested_amount:,.0f}

        Tasks:
        1. Search for RBI policies relevant to {loan_type}
        2. Check if the borrower qualifies for PMAY, MUDRA, or other government schemes
        3. List required documents for this loan type
        4. Identify any red flags in the application
        5. Estimate approval likelihood

        Provide response as JSON with:
        - eligibility: "yes" / "no" / "conditional"
        - approval_likelihood: percentage (0-100)
        - required_documents: list of document names
        - red_flags: list of concern strings (empty if none)
        - scheme_eligibility: object with scheme names and yes/no
        - compliance_notes: string summary
        - improvement_suggestions: list of actionable steps if not eligible
        """,
        expected_output="A JSON compliance report",
        agent=compliance_agent
    )

    crew = Crew(agents=[compliance_agent], tasks=[compliance_task], verbose=False)
    result = crew.kickoff()
    return _parse_compliance_output(str(result), credit_profile, loan_type, requested_amount)


def _deterministic_compliance(credit_profile: dict, loan_type: str, requested_amount: float) -> dict:
    """Fallback deterministic compliance check."""
    eligible = credit_profile.get("eligible", False)
    risk_tier = credit_profile.get("risk_tier", "Medium")
    dti = credit_profile.get("dti_ratio", 50)
    credit_tier = credit_profile.get("credit_tier", "Fair")

    # Determine eligibility
    if eligible and risk_tier != "High":
        eligibility = "yes"
        approval_likelihood = 80 if risk_tier == "Low" else 60
    elif risk_tier == "High" or dti > 50:
        eligibility = "no"
        approval_likelihood = 15
    else:
        eligibility = "conditional"
        approval_likelihood = 40

    # Adjust for credit tier
    if credit_tier == "Excellent":
        approval_likelihood = min(95, approval_likelihood + 15)
    elif credit_tier == "Poor":
        approval_likelihood = max(5, approval_likelihood - 20)

    # Required documents based on loan type
    base_docs = [
        "Identity Proof (Aadhaar Card / PAN Card / Passport)",
        "Address Proof (Utility bill / Aadhaar / Passport)",
        "Passport-sized photographs (2)",
        "Bank statements (last 6 months)",
    ]

    income_docs_salaried = [
        "Last 3 months salary slips",
        "Form 16 / ITR (last 2 years)",
        "Appointment or experience letter",
    ]

    loan_specific_docs = {
        "home_loan": ["Property documents", "Sale agreement / Allotment letter",
                      "Builder's approved plan", "NOC from housing society", "Title deed"],
        "personal_loan": ["No specific collateral documents needed"],
        "car_loan": ["Vehicle quotation / proforma invoice", "Driving license"],
        "business_loan": ["Business registration / GST certificate", "Business plan",
                         "Audited financials (last 3 years)", "Trade license"],
        "education_loan": ["Admission letter from institution", "Fee structure",
                          "Course details", "Academic transcripts"],
        "mudra_loan": ["Business plan / project report", "GST registration (if applicable)",
                      "Business proof / trade license"],
    }

    loan_type_key = loan_type.lower().replace(" ", "_").replace("-", "_")
    required_docs = base_docs + income_docs_salaried + loan_specific_docs.get(loan_type_key, [])

    # Red flags
    red_flags = []
    if dti > 50:
        red_flags.append(f"High DTI ratio ({dti}%) exceeds RBI recommended limit of 50%")
    if credit_tier in ["Poor", "Fair"]:
        red_flags.append(f"Credit score below ideal ({credit_tier} tier)")
    if risk_tier == "High":
        red_flags.append("High risk classification from fraud/default assessment")
    if requested_amount > 10000000 and loan_type_key == "home_loan":
        red_flags.append("Loan amount above ₹1Cr — higher down payment and stricter checks required")

    # Scheme eligibility
    income = credit_profile.get("monthly_income", 0) * 12
    scheme_eligibility = {}

    if loan_type_key == "home_loan":
        if income <= 300000:
            scheme_eligibility["PMAY-EWS"] = "Eligible (income ≤ ₹3L) — 6.5% interest subsidy"
        elif income <= 600000:
            scheme_eligibility["PMAY-LIG"] = "Eligible (income ₹3-6L) — 6.5% interest subsidy"
        elif income <= 1200000:
            scheme_eligibility["PMAY-MIG-I"] = "Eligible (income ₹6-12L) — 4% interest subsidy"
        elif income <= 1800000:
            scheme_eligibility["PMAY-MIG-II"] = "Eligible (income ₹12-18L) — 3% interest subsidy"
        else:
            scheme_eligibility["PMAY"] = "Not eligible (income > ₹18L)"
    elif loan_type_key in ["business_loan", "mudra_loan"]:
        if requested_amount <= 1000000:
            if requested_amount <= 50000:
                scheme_eligibility["MUDRA-Shishu"] = "Eligible (loan up to ₹50K)"
            elif requested_amount <= 500000:
                scheme_eligibility["MUDRA-Kishore"] = "Eligible (loan ₹50K-5L)"
            else:
                scheme_eligibility["MUDRA-Tarun"] = "Eligible (loan ₹5L-10L)"
        else:
            scheme_eligibility["MUDRA"] = "Not eligible (amount > ₹10L)"

    # Improvement suggestions
    suggestions = []
    if not eligible:
        if dti > 50:
            suggestions.append("Reduce existing EMIs or increase income to lower DTI below 50%")
        if credit_tier in ["Poor", "Fair"]:
            suggestions.append("Build credit score by paying existing dues on time for 6-12 months")
            suggestions.append("Keep credit card utilization below 30%")
        if credit_profile.get("employment_months", 0) < 24:
            suggestions.append("Build at least 2 years of stable employment before applying")
        suggestions.append("Consider applying for a lower loan amount to improve approval chances")

    compliance_notes = (f"Loan application for {loan_type} of ₹{requested_amount:,.0f} — "
                       f"Eligibility: {eligibility.upper()} | "
                       f"Approval Likelihood: {approval_likelihood}% | "
                       f"Red Flags: {len(red_flags)} | "
                       f"Government Schemes: {len([v for v in scheme_eligibility.values() if 'Eligible' in v])} applicable")

    return {
        "eligibility": eligibility,
        "approval_likelihood": approval_likelihood,
        "required_documents": required_docs,
        "red_flags": red_flags,
        "scheme_eligibility": scheme_eligibility,
        "compliance_notes": compliance_notes,
        "improvement_suggestions": suggestions,
        "method": "deterministic"
    }


def _parse_compliance_output(result_str: str, credit_profile: dict,
                             loan_type: str, requested_amount: float) -> dict:
    """Parse CrewAI compliance output."""
    import re
    json_match = re.search(r'\{[\s\S]*\}', result_str)
    if json_match:
        try:
            parsed = json.loads(json_match.group())
            if "eligibility" in parsed:
                parsed["method"] = "crewai"
                return parsed
        except json.JSONDecodeError:
            pass

    det = _deterministic_compliance(credit_profile, loan_type, requested_amount)
    det["llm_analysis"] = result_str[:500]
    det["method"] = "crewai_hybrid"
    return det


def generate_improvement_plan(credit_profile: dict) -> dict:
    """Generate a credit improvement plan for users who aren't eligible."""
    log_action(logger, "info", "risk_compliance", "IMPROVEMENT_PLAN_STARTED",
               f"risk_tier={credit_profile.get('risk_tier', 'N/A')}")

    weaknesses = credit_profile.get("weaknesses", [])
    dti = credit_profile.get("dti_ratio", 0)
    credit_tier = credit_profile.get("credit_tier", "Fair")

    steps = []

    if credit_tier in ["Poor", "Fair"]:
        steps.append({
            "step": 1,
            "action": "Improve Credit Score",
            "details": "Pay all EMIs and credit card bills on time. Reduce credit utilization below 30%. Avoid new credit applications for 6 months.",
            "timeline": "6-12 months",
            "expected_improvement": "50-100 point increase in CIBIL score"
        })

    if dti > 40:
        steps.append({
            "step": len(steps) + 1,
            "action": "Reduce Debt-to-Income Ratio",
            "details": f"Current DTI is {dti}%. Prepay or close small loans. Avoid taking new debt. Target DTI below 36%.",
            "timeline": "3-6 months",
            "expected_improvement": f"Reduce DTI from {dti}% to below 40%"
        })

    steps.append({
        "step": len(steps) + 1,
        "action": "Build Savings & Documentation",
        "details": "Maintain regular bank account activity. Save at least 20% of income. Keep all income proof documents updated.",
        "timeline": "3-6 months",
        "expected_improvement": "Stronger application profile"
    })

    if not steps:
        steps.append({
            "step": 1,
            "action": "Maintain Current Profile",
            "details": "Your profile is already in good shape. Continue timely payments and maintain low utilization.",
            "timeline": "Ongoing",
            "expected_improvement": "Maintain eligibility"
        })

    plan = {
        "title": "Credit Improvement Plan",
        "current_status": f"Risk: {credit_profile.get('risk_tier', 'N/A')} | Credit: {credit_tier} | DTI: {dti}%",
        "steps": steps,
        "estimated_timeline": f"{max(s.get('timeline', '3 months').split('-')[0].strip().split()[0] for s in steps if 'timeline' in s)} months minimum",
        "goal": "Achieve loan eligibility with competitive interest rates"
    }

    log_action(logger, "info", "risk_compliance", "IMPROVEMENT_PLAN_GENERATED",
               f"steps={len(steps)} | timeline=estimated")

    return plan
