"""
LLM-powered intent classifier.
Uses Groq (llama-3.1-8b-instant — fastest/cheapest model) to classify intent
and extract loan details from natural language, with full conversation context.
Falls back to regex heuristics if LLM is unavailable or hits rate limits.
"""
import re
import json
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from logger import get_logger, log_action

logger = get_logger("intent_classifier")

# ─────────────────────────────────────────────────────────
#  LLM CLASSIFICATION  (primary)
# ─────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are the intent router for an Indian AI Loan & Credit Advisor.

Given a user message (and optional conversation history), return a JSON object — nothing else.

## JSON Schema
{
  "intent": one of ["loan_inquiry", "policy_question", "profile_update", "general"],
  "loan_amount": <number in Indian Rupees, or null if not mentioned>,
  "loan_type": one of ["home_loan","personal_loan","car_loan","business_loan","education_loan","gold_loan","mudra_loan","unknown"],
  "tenure_months": <integer, or null if not mentioned>,
  "amount_from_message": <true if loan_amount was explicitly stated in the CURRENT message, false otherwise>
}

## Intent Definitions
- **loan_inquiry**: ONLY use this if the user is explicitly requesting a brand new loan amount OR asking to recalculate/compare an EMI with new numbers. Do NOT use this for conversational follow-ups.
- **policy_question**: User asks about government schemes (PMAY, MUDRA), RBI rules, tax benefits, document requirements, eligibility criteria, credit score improvement tips, or follow-up questions about WHY something was approved/rejected.
- **profile_update**: User is directly providing their personal financial data to update their profile (e.g. "my income is 5 lakhs", "I work for 2 years", "my credit score is 720").
- **general**: CRITICAL - Use this for arguments ("but you said..."), clarifications, greetings, chit-chat, or any follow-up question that does not explicitly ask to rerun a loan calculation.

## Amount Rules
- "50000" → 50000
- "50 lakhs" / "50 lakh" → 5000000
- "1.5 crore" → 15000000
- "2.5L" → 250000
- Always return the raw rupee number, never multiply yourself.

## Loan Type Rules
- Mentions "wedding", "marriage", "medical", "festival", "vacation" → personal_loan
- Mentions "house", "apartment", "flat", "plot" → home_loan
- Mentions "car", "bike", "vehicle" → car_loan
- Mentions "business", "startup", "enterprise" → business_loan
- Mentions "college", "education", "study", "university" → education_loan
- Mentions "gold" → gold_loan
- Mentions "mudra" → mudra_loan
- If loan, but no type → unknown (system will infer from amount)

## Tenure Rules
- "20 years" → 240
- "5 years" → 60
- "36 months" → 36
- If not mentioned → null

Return ONLY the JSON object, no explanation, no markdown code fences."""


def classify_intent_llm(message: str, history: list = None) -> dict:
    """
    Use Groq LLM to classify intent and extract loan details.
    Returns a dict with keys: intent, loan_amount, loan_type, tenure_months, amount_from_message
    """
    try:
        from config import settings
        from groq import Groq

        if not settings.GROQ_API_KEY:
            raise ValueError("No GROQ_API_KEY")

        client = Groq(api_key=settings.GROQ_API_KEY)

        # Build messages for the LLM
        chat_messages = [{"role": "system", "content": SYSTEM_PROMPT}]

        # Add recent conversation history (last 6 turns max for context)
        if history:
            recent = history[-12:] if len(history) > 12 else history
            # Exclude the last message (current one) — added below
            for h in recent[:-1]:
                role = "user" if h["role"] == "user" else "assistant"
                # Truncate long assistant responses to keep token count low
                content = h["content"][:400] if role == "assistant" else h["content"]
                chat_messages.append({"role": role, "content": content})

        # Add the current message
        chat_messages.append({"role": "user", "content": message})

        completion = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=chat_messages,
            max_tokens=200,
            temperature=0.0,   # deterministic for classification
            response_format={"type": "json_object"},
        )

        raw = completion.choices[0].message.content.strip()
        result = json.loads(raw)

        # Validate and normalise
        valid_intents = {"loan_inquiry", "policy_question", "profile_update", "general"}
        valid_types = {"home_loan", "personal_loan", "car_loan", "business_loan",
                       "education_loan", "gold_loan", "mudra_loan", "unknown"}

        intent = result.get("intent", "general")
        if intent not in valid_intents:
            intent = "general"

        loan_type = result.get("loan_type", "unknown")
        if loan_type not in valid_types:
            loan_type = "unknown"

        loan_amount = result.get("loan_amount")
        if loan_amount is not None:
            try:
                loan_amount = float(loan_amount)
                # Sanity cap — reject if > ₹100 Crore (LLM hallucinated a number)
                if loan_amount > 1_000_000_000:
                    loan_amount = None
            except (ValueError, TypeError):
                loan_amount = None

        tenure = result.get("tenure_months")
        if tenure is not None:
            try:
                tenure = int(tenure)
            except (ValueError, TypeError):
                tenure = None

        amount_from_message = bool(result.get("amount_from_message", loan_amount is not None))

        parsed = {
            "intent": intent,
            "loan_amount": loan_amount,
            "loan_type": loan_type,
            "tenure_months": tenure,
            "amount_from_message": amount_from_message,
        }

        log_action(logger, "info", "intent_classifier", "LLM_CLASSIFIED",
                   f"message={message[:60]} | {parsed}")
        return parsed

    except Exception as e:
        log_action(logger, "warning", "intent_classifier", "LLM_CLASSIFY_FAILED",
                   f"error={str(e)[:120]} | falling back to regex")
        return None


# ─────────────────────────────────────────────────────────
#  REGEX FALLBACK  (when LLM is rate-limited / unavailable)
# ─────────────────────────────────────────────────────────

_LOAN_KW = [
    r'\bloan\b', r'\bemi\b', r'\bborrow\b', r'\bmortgage\b',
    r'\binterest\s*rate\b', r'\bcan\s*i\s*get\b',
    r'\blakhs?\b', r'\bcrore\b', r'\b₹\b', r'\brupees?\b',
    r'\brepay\b', r'\btenure\b', r'\bdown\s*payment\b', r'\bafford\b',
]
_POLICY_KW = [
    r'\bpolicy\b', r'\brbi\b', r'\bpmay\b', r'\bawas\b', r'\bsubsidy\b',
    r'\bguideline\b', r'\bscheme\b', r'\bcompliance\b', r'\beligib\w*\b',
    r'\bmudra\b', r'\btax\s*benefit\b', r'\bsection\s*80\b',
    r'\bwhy\b', r'\bhow\s*(?:come|is|does)\b', r'\bexplain\b',
]
_PROFILE_KW = [
    r'\bi\s*earn\b', r'\bmy\s*salary\b', r'\bmy\s*income\b',
    r'\bupdate\s*(?:my)?\s*profile\b', r'\bi\s*work\b',
]
_AMOUNT_PATTERNS = [
    (r'(?:₹|rs\.?|inr)\s*([\d,]+(?:\.\d+)?)\s*(?:lakhs?|lac)\b',  1e5),
    (r'(?:₹|rs\.?|inr)\s*([\d,]+(?:\.\d+)?)\s*(?:crores?|cr)\b',  1e7),
    (r'([\d,]+(?:\.\d+)?)\s*(?:lakhs?|lac)\b',                     1e5),
    (r'([\d,]+(?:\.\d+)?)\s*(?:crores?|cr)\b',                     1e7),
    (r'(?:₹|rs\.?|inr)\s*([\d,]+(?:\.\d+)?)',                      1),
    (r'\b(\d{4,9})\b',                                              1),
]
_TYPE_PATTERNS = [
    ("home_loan",      [r'home\s*loan', r'housing\s*loan', r'flat\s*loan', r'buy.*\b(?:house|apartment|flat)\b']),
    ("personal_loan",  [r'personal\s*loan', r'\bwedding\b', r'\bmarriage\b', r'\bmedical\b', r'\bvacation\b']),
    ("car_loan",       [r'car\s*loan', r'vehicle\s*loan', r'bike\s*loan', r'buy.*\bcar\b']),
    ("business_loan",  [r'business\s*loan', r'msme\s*loan', r'\bstartup\b']),
    ("education_loan", [r'education\s*loan', r'study\s*loan', r'student\s*loan', r'\bcollege\b']),
    ("gold_loan",      [r'gold\s*loan']),
    ("mudra_loan",     [r'\bmudra\b']),
]


def _regex_classify(message: str) -> dict:
    """Regex-based fallback classifier."""
    msg = message.lower()

    scores = {"loan_inquiry": 0, "policy_question": 0, "profile_update": 0, "general": 1}
    for p in _LOAN_KW:
        if re.search(p, msg): scores["loan_inquiry"] += 2
    for p in _POLICY_KW:
        if re.search(p, msg): scores["policy_question"] += 2
    for p in _PROFILE_KW:
        if re.search(p, msg): scores["profile_update"] += 2
    if re.search(r'[₹$]\s*\d+|\d+\s*(?:lakh|crore|lac)\b', msg):
        scores["loan_inquiry"] += 3

    intent = max(scores, key=scores.get)

    # Extract amount
    loan_amount = None
    amount_from_message = False
    for pattern, multiplier in _AMOUNT_PATTERNS:
        m = re.search(pattern, msg)
        if m:
            val = float(m.group(1).replace(',', '')) * multiplier
            if val <= 1_000_000_000:
                loan_amount = val
                amount_from_message = True
                break

    # Extract type
    loan_type = "unknown"
    for lt, patterns in _TYPE_PATTERNS:
        if any(re.search(p, msg) for p in patterns):
            loan_type = lt
            break

    # Extract tenure
    tenure = None
    m = re.search(r'(\d+)\s*years?', msg)
    if m: tenure = int(m.group(1)) * 12
    else:
        m = re.search(r'(\d+)\s*months?', msg)
        if m: tenure = int(m.group(1))

    return {
        "intent": intent,
        "loan_amount": loan_amount,
        "loan_type": loan_type,
        "tenure_months": tenure,
        "amount_from_message": amount_from_message,
    }


# ─────────────────────────────────────────────────────────
#  PUBLIC API  (used by nodes.py)
# ─────────────────────────────────────────────────────────

def classify_intent(message: str, history: list = None) -> str:
    """Classify intent only (compatibility shim for old call sites)."""
    result = classify_and_extract(message, history)
    return result["intent"]


def classify_and_extract(message: str, history: list = None) -> dict:
    """
    Main entry point: returns a unified dict with all extracted info.
    Tries LLM first, falls back to regex on failure.
    """
    # Try LLM first
    result = classify_intent_llm(message, history)

    if result is None:
        # LLM failed — use regex
        result = _regex_classify(message)
        log_action(logger, "info", "intent_classifier", "INTENT_CLASSIFIED",
                   f"method=regex | message={message[:80]} | intent={result['intent']}")
    else:
        log_action(logger, "info", "intent_classifier", "INTENT_CLASSIFIED",
                   f"method=llm | message={message[:80]} | intent={result['intent']} | "
                   f"amount={result['loan_amount']} | type={result['loan_type']}")

    return result


def extract_loan_details(message: str, history: list = None) -> dict:
    """
    Extract loan details (compatibility shim — now calls classify_and_extract).
    Returns format compatible with existing nodes.py code.
    """
    result = classify_and_extract(message, history)

    loan_type = result["loan_type"]
    loan_amount = result["loan_amount"]

    # Resolve "unknown" type from amount heuristic
    if loan_type == "unknown":
        if loan_amount and loan_amount > 2_000_000:
            loan_type = "home_loan"
        else:
            loan_type = "personal_loan"

    # Default tenure based on type
    tenure = result["tenure_months"]
    if tenure is None:
        tenure = 240 if loan_type == "home_loan" else 60

    details = {
        "loan_type": loan_type,
        "requested_amount": loan_amount,          # May be None — history lookup in nodes.py
        "requested_tenure": tenure,
        "_amount_from_message": result["amount_from_message"],
    }

    log_action(logger, "info", "intent_classifier", "LOAN_DETAILS_EXTRACTED",
               f"type={loan_type} | amount={loan_amount} | tenure={tenure}mo | "
               f"explicit={result['amount_from_message']}")

    return details
