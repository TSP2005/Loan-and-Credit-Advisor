"""
Indian Loan Risk Detector — XGBoost model trained on Indian loan data.
Replaces the old UCI Taiwan credit card dataset model.

Features: credit_score, annual_income, employment_months, existing_emi_amount,
          loan_amount, dti_ratio, age, credit_utilization, existing_loans, loan_type_idx
Target: default probability (0=repaid, 1=defaulted)
"""
import os
import sys
import numpy as np
import joblib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings
from logger import get_logger, log_action

logger = get_logger("loan_risk_detector")

FEATURES = [
    "credit_score", "annual_income", "employment_months",
    "existing_emi_amount", "loan_amount", "dti_ratio",
    "age", "credit_utilization", "existing_loans", "loan_type_idx"
]

LOAN_TYPE_INDEX = {
    "home_loan": 0, "personal_loan": 1, "car_loan": 2,
    "business_loan": 3, "education_loan": 4, "gold_loan": 5, "mudra_loan": 6,
}


class LoanRiskDetector:
    """XGBoost loan default risk detector — trained on Indian loan data."""

    def __init__(self):
        self.model = None
        self.scaler = None
        self.is_trained = False
        self._try_load_model()

    def _try_load_model(self):
        model_path  = os.path.join(settings.MODEL_SAVE_PATH, settings.LOAN_RISK_MODEL_FILE)
        scaler_path = os.path.join(settings.MODEL_SAVE_PATH, settings.LOAN_RISK_SCALER_FILE)

        if os.path.exists(model_path) and os.path.exists(scaler_path):
            try:
                self.model  = joblib.load(model_path)
                self.scaler = joblib.load(scaler_path)
                self.is_trained = True
                log_action(logger, "info", "loan_risk_detector", "MODEL_LOADED",
                           f"source=disk | model=loan_risk_model.joblib | features={len(FEATURES)}")
            except Exception as e:
                log_action(logger, "warning", "loan_risk_detector", "MODEL_LOAD_FAILED",
                           f"error={str(e)}")

    def predict(self, user_profile: dict, loan_amount: float = None,
                loan_type: str = "personal_loan") -> dict:
        """
        Predict loan default risk for a user.

        Args:
            user_profile: dict with credit_score, annual_income, employment_months,
                          existing_emi_amount, age, credit_utilization, existing_loans
            loan_amount:  Requested loan amount in INR
            loan_type:    One of home_loan, personal_loan, car_loan, etc.

        Returns:
            dict with risk_score (0-1), risk_tier (Low/Medium/High), explanation
        """
        if not self.is_trained:
            return self._heuristic_predict(user_profile, loan_amount)

        try:
            feature_vector = self._build_feature_vector(user_profile, loan_amount, loan_type)
            scaled = self.scaler.transform([feature_vector])
            risk_score = float(self.model.predict_proba(scaled)[0][1])
        except Exception as e:
            log_action(logger, "warning", "loan_risk_detector", "PREDICTION_FALLBACK",
                       f"error={str(e)} | using heuristic")
            return self._heuristic_predict(user_profile, loan_amount)

        risk_tier    = self._tier(risk_score)
        explanation  = self._explain(user_profile, loan_amount, risk_score, risk_tier)

        log_action(logger, "info", "loan_risk_detector", "RISK_PREDICTION",
                   f"risk_score={risk_score:.4f} | risk_tier={risk_tier} | "
                   f"credit_score={user_profile.get('credit_score', 0)} | "
                   f"annual_income={user_profile.get('annual_income', 0)} | "
                   f"loan_amount={loan_amount or 0:.0f}")

        return {
            "risk_score": round(risk_score, 4),
            "risk_tier":  risk_tier,
            "explanation": explanation,
            "model_type":  "lending_club_model",
        }

    def _build_feature_vector(self, profile: dict, loan_amount: float,
                               loan_type: str) -> list:
        income      = float(profile.get("annual_income", 0))
        emi         = float(profile.get("existing_emi_amount", 0))
        loan_amt    = float(loan_amount or profile.get("requested_amount", 100000))
        monthly_inc = income / 12 if income > 0 else 1

        # New EMI estimate (approx 2% of loan per month for 5yr)
        new_emi    = loan_amt * 0.02
        dti_ratio  = min(((emi + new_emi) * 12) / income * 100, 120) if income > 0 else 100

        return [
            float(profile.get("credit_score", 600)),
            income,
            float(profile.get("employment_months", 12)),
            emi,
            loan_amt,
            dti_ratio,
            float(profile.get("age", 30)),
            float(profile.get("credit_utilization", 30)),
            float(profile.get("existing_loans", 0)),
            float(LOAN_TYPE_INDEX.get(loan_type, 1)),
        ]

    def _heuristic_predict(self, profile: dict, loan_amount: float = None) -> dict:
        """Fallback when model is not loaded."""
        score = 0.5
        cs = profile.get("credit_score", 600)
        if cs >= 750: score -= 0.25
        elif cs >= 700: score -= 0.10
        elif cs >= 650: score -= 0.00
        elif cs >= 600: score += 0.15
        else: score += 0.30

        income = profile.get("annual_income", 0)
        emi    = profile.get("existing_emi_amount", 0)
        if income > 0:
            dti = (emi * 12) / income
            if dti > 0.6: score += 0.25
            elif dti > 0.4: score += 0.10
            elif dti < 0.2: score -= 0.05

        emp = profile.get("employment_months", 12)
        if emp < 6: score += 0.15
        elif emp < 12: score += 0.08
        elif emp >= 36: score -= 0.05

        risk_score = float(np.clip(score, 0.02, 0.97))
        risk_tier  = self._tier(risk_score)
        explanation = self._explain(profile, loan_amount, risk_score, risk_tier)

        log_action(logger, "info", "loan_risk_detector", "RISK_PREDICTION_HEURISTIC",
                   f"risk_score={risk_score:.4f} | risk_tier={risk_tier}")

        return {
            "risk_score":  round(risk_score, 4),
            "risk_tier":   risk_tier,
            "explanation": explanation,
            "model_type":  "heuristic",
        }

    @staticmethod
    def _tier(score: float) -> str:
        # In real-world lending (like Lending Club), the baseline default rate is ~15%.
        # A default probability > 30% is considered High Risk.
        if score < 0.15: return "Low"
        if score < 0.35: return "Medium"
        return "High"


    @staticmethod
    def _explain(profile: dict, loan_amount: float, score: float, tier: str) -> str:
        parts = []
        cs     = profile.get("credit_score", 0)
        income = profile.get("annual_income", 0)
        emi    = profile.get("existing_emi_amount", 0)
        emp    = profile.get("employment_months", 0)

        if cs >= 750: parts.append(f"Excellent CIBIL score ({cs})")
        elif cs >= 700: parts.append(f"Good CIBIL score ({cs})")
        elif cs >= 650: parts.append(f"Fair CIBIL score ({cs}) — borderline")
        elif cs > 0:    parts.append(f"Low CIBIL score ({cs}) — major risk factor")

        if income > 0 and emi > 0:
            dti = round((emi * 12) / income * 100, 1)
            if dti > 50:   parts.append(f"High debt-to-income ratio ({dti}%)")
            elif dti > 30: parts.append(f"Moderate DTI ratio ({dti}%)")
            else:          parts.append(f"Healthy DTI ratio ({dti}%)")

        if emp >= 36:   parts.append(f"Stable employment ({emp // 12} years)")
        elif emp >= 12: parts.append(f"Moderate employment tenure ({emp} months)")
        elif emp > 0:   parts.append(f"Short employment ({emp} months) — adds risk")

        if loan_amount and income:
            leverage = loan_amount / income
            if leverage > 3: parts.append(f"Loan amount is {leverage:.1f}x annual income — high leverage")

        parts.append(f"Overall risk: {tier} (score: {score:.2f})")
        return ". ".join(parts)


# ─── Singleton ───────────────────────────────────────────
loan_risk_detector = LoanRiskDetector()

# Keep backwards-compatible alias so existing imports still work
fraud_detector = loan_risk_detector
