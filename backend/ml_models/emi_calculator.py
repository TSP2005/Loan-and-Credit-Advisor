"""
EMI (Equated Monthly Installment) Calculator.
Pure mathematical calculation.
Formula: EMI = P × r × (1+r)^n / ((1+r)^n - 1)
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from logger import get_logger, log_action

logger = get_logger("emi_calculator")


def calculate_emi(principal: float, annual_rate_percent: float, tenure_months: int) -> dict:
    """
    Calculate EMI and related amounts.

    Args:
        principal: Loan principal amount (₹)
        annual_rate_percent: Annual interest rate (e.g. 8.5 for 8.5%)
        tenure_months: Loan tenure in months

    Returns:
        dict with monthly_emi, total_interest, total_repayment, principal, rate, tenure
    """
    if principal <= 0 or annual_rate_percent < 0 or tenure_months <= 0:
        log_action(logger, "warning", "emi_calculator", "EMI_INVALID_INPUT",
                   f"principal={principal} | rate={annual_rate_percent}% | tenure={tenure_months}")
        return {
            "monthly_emi": 0,
            "total_interest": 0,
            "total_repayment": 0,
            "principal": principal,
            "annual_rate_percent": annual_rate_percent,
            "tenure_months": tenure_months,
            "error": "Principal and tenure must be positive, rate must be non-negative"
        }

    # Monthly interest rate
    r = annual_rate_percent / (12 * 100)
    n = tenure_months

    if r == 0:
        monthly_emi = principal / n
    else:
        # EMI formula: P × r × (1+r)^n / ((1+r)^n - 1)
        power = (1 + r) ** n
        monthly_emi = principal * r * power / (power - 1)

    total_repayment = monthly_emi * n
    total_interest = total_repayment - principal

    result = {
        "monthly_emi": round(monthly_emi, 2),
        "total_interest": round(total_interest, 2),
        "total_repayment": round(total_repayment, 2),
        "principal": principal,
        "annual_rate_percent": annual_rate_percent,
        "tenure_months": tenure_months,
    }

    log_action(logger, "info", "emi_calculator", "EMI_CALCULATED",
               f"principal=₹{principal:,.0f} | rate={annual_rate_percent}% | "
               f"tenure={tenure_months} months | monthly_emi=₹{monthly_emi:,.2f} | "
               f"total_interest=₹{total_interest:,.2f}")

    return result
