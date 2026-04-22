"""
Interest rate predictor — repo-rate-linked rate bands by loan type.
Rates are computed as: Repo Rate + Spread (adjusted by credit score).

RBI Repo Rate: 6.00% (as of April 2026 — 25bps cut from 6.25%)
Source: RBI MPC April 2026 policy announcement.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from logger import get_logger, log_action

logger = get_logger("rate_predictor")

# ─────────────────────────────────────────────────────────
#  RBI REPO RATE (Fetches live from RBI on boot, falls back to 6.00%)
# ─────────────────────────────────────────────────────────
def _fetch_live_repo_rate():
    try:
        import requests
        from bs4 import BeautifulSoup
        import re
        
        response = requests.get('https://www.rbi.org.in/', timeout=5, headers={'User-Agent': 'Mozilla/5.0'})
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            match = re.search(r'Policy Repo Rate.*?([0-9\.]+)\s*%', soup.get_text(), re.IGNORECASE | re.DOTALL)
            if match:
                rate = float(match.group(1))
                log_action(logger, "info", "rate_predictor", "REPO_RATE_FETCHED", f"live_rate={rate}%")
                return rate
    except Exception as e:
        log_action(logger, "warning", "rate_predictor", "REPO_RATE_FETCH_FAILED", f"error={str(e)}")
        
    return 6.00  # Default fallback if offline or structural changes occur on RBI site

RBI_REPO_RATE = _fetch_live_repo_rate()

# ─────────────────────────────────────────────────────────
#  RATE BANDS — expressed as spreads over repo rate
#  (actual market rates = repo_rate + spread)
#  Providers listed from best to most expensive
# ─────────────────────────────────────────────────────────
RATE_BANDS = {
    "home_loan": {
        "spread_min": 2.35,   # → 8.35% at repo=6.00
        "spread_max": 5.50,   # → 11.50%
        "spread_avg": 3.15,   # → 9.15%
        "description": "Home Loan / Housing Loan",
        "typical_tenure": "Up to 30 years (360 months)",
        "providers": [
            {"name": "SBI / Top PSU Bank",          "spread": 2.35},
            {"name": "HDFC / Leading Private Bank", "spread": 2.65},
            {"name": "ICICI / Premium Option",      "spread": 2.40, "tenure_variant": 0.5},
            {"name": "Axis Bank",                   "spread": 2.60},
            {"name": "Punjab National Bank (PNB)",  "spread": 2.35},
        ],
        "notes": "Linked to RLLR / EBLR (repo-linked). Rates reset quarterly."
    },
    "personal_loan": {
        "spread_min": 4.49,   # → 10.49%
        "spread_max": 18.00,  # → 24.00%
        "spread_avg": 8.00,   # → 14.00%
        "description": "Personal Loan (unsecured)",
        "typical_tenure": "1 to 5 years (12–60 months)",
        "providers": [
            {"name": "HDFC",          "spread": 4.49},
            {"name": "ICICI",         "spread": 8.00},
            {"name": "Bajaj Finserv", "spread": 4.49, "tenure_variant": -0.5},
            {"name": "Tata Capital",  "spread": 5.50},
            {"name": "Axis Bank",     "spread": 6.50},
        ],
        "notes": "Fixed rate product. Not directly repo-linked but moves with RBI cycle."
    },
    "car_loan": {
        "spread_min": 2.50,   # → 8.50%
        "spread_max": 8.00,   # → 14.00%
        "spread_avg": 3.75,   # → 9.75%
        "description": "Car / Vehicle Loan",
        "typical_tenure": "1 to 7 years (12–84 months)",
        "providers": [
            {"name": "SBI",               "spread": 2.50},
            {"name": "HDFC",              "spread": 2.75},
            {"name": "ICICI",             "spread": 3.00},
            {"name": "Bank of Baroda",    "spread": 2.65},
            {"name": "Mahindra Finance",  "spread": 4.00},
        ],
        "notes": "Secured loan. Rates closely track repo rate changes."
    },
    "business_loan": {
        "spread_min": 8.00,   # → 14.00%
        "spread_max": 24.00,  # → 30.00%
        "spread_avg": 12.00,  # → 18.00%
        "description": "Business Loan / MSME Loan",
        "typical_tenure": "1 to 5 years (12–60 months)",
        "providers": [
            {"name": "SBI MSME",       "spread": 8.00},
            {"name": "HDFC Business",  "spread": 9.00},
            {"name": "Kotak Business", "spread": 10.00},
            {"name": "Lendingkart",    "spread": 12.00},
            {"name": "IndusInd MSME",  "spread": 9.50},
        ],
        "notes": "Higher spread due to unsecured nature and business risk."
    },
    "education_loan": {
        "spread_min": 1.50,   # → 7.50%
        "spread_max": 7.50,   # → 13.50%
        "spread_avg": 3.50,   # → 9.50%
        "description": "Education Loan",
        "typical_tenure": "5 to 15 years (60–180 months)",
        "providers": [
            {"name": "SBI Scholar",     "spread": 1.50},
            {"name": "Bank of Baroda",  "spread": 2.00},
            {"name": "Avanse",          "spread": 4.00},
            {"name": "HDFC Credila",    "spread": 3.50},
            {"name": "PNB Education",   "spread": 1.75},
        ],
        "notes": "Subsidized rates available under government schemes. Moratorium during study."
    },
    "gold_loan": {
        "spread_min": 1.00,   # → 7.00%
        "spread_max": 11.00,  # → 17.00%
        "spread_avg": 4.50,   # → 10.50%
        "description": "Gold Loan (secured against gold)",
        "typical_tenure": "3 months to 3 years (3–36 months)",
        "providers": [
            {"name": "Muthoot Finance", "spread": 1.00},
            {"name": "Manappuram",      "spread": 1.50},
            {"name": "SBI Gold",        "spread": 2.00},
            {"name": "HDFC Gold",       "spread": 2.50},
        ],
        "notes": "Secured loan. Lowest spread category. LTV up to 75% of gold value."
    },
    "mudra_loan": {
        "spread_min": 2.00,   # → 8.00%
        "spread_max": 6.00,   # → 12.00%
        "spread_avg": 3.50,   # → 9.50%
        "description": "PMMY MUDRA Loan (up to ₹10 Lakh for micro-enterprises)",
        "typical_tenure": "Up to 5 years (60 months)",
        "providers": [
            {"name": "SBI e-MUDRA",          "spread": 2.00},
            {"name": "Public Sector Banks",  "spread": 2.50},
            {"name": "Private Banks",        "spread": 3.50},
            {"name": "Microfinance (MFI)",   "spread": 5.00},
        ],
        "notes": "Shishu: up to ₹50K | Kishore: ₹50K–5L | Tarun: ₹5L–10L. No collateral."
    },
}

# Credit score → rate adjustment over avg (in %)
CREDIT_ADJUSTMENTS = {
    "Excellent":     ("800+",   -0.75),
    "Very Good":     ("750–799",-0.25),
    "Good":          ("700–749", 0.00),
    "Fair":          ("650–699", 0.50),
    "Below Average": ("600–649", 1.50),
    "Poor":          ("<600",    3.00),
}


def _credit_tier(credit_score: int) -> tuple:
    """Return (tier_name, spread_adjustment) for a given credit score."""
    if credit_score >= 800:   return "Excellent",     -0.75
    if credit_score >= 750:   return "Very Good",     -0.25
    if credit_score >= 700:   return "Good",           0.00
    if credit_score >= 650:   return "Fair",           0.50
    if credit_score >= 600:   return "Below Average",  1.50
    return "Poor",  3.00


def predict_rate(loan_type: str, credit_score: int = 700,
                 repo_rate: float = None) -> dict:
    """
    Predict interest rate band for a loan type.

    Rates = RBI Repo Rate + Spread (adjusted by credit score tier).

    Args:
        loan_type:    One of home_loan, personal_loan, car_loan, ...
        credit_score: User's CIBIL score (300–900)
        repo_rate:    Override the global repo rate (for future simulations)

    Returns:
        dict with min_rate, max_rate, personalized_rate, providers, repo_rate, ...
    """
    repo = repo_rate if repo_rate is not None else RBI_REPO_RATE
    lt = loan_type.lower().replace(" ", "_").replace("-", "_")

    if lt not in RATE_BANDS:
        log_action(logger, "warning", "rate_predictor", "UNKNOWN_LOAN_TYPE",
                   f"loan_type={loan_type} | available={list(RATE_BANDS.keys())}")
        return {"error": f"Unknown loan type: {loan_type}",
                "available_types": list(RATE_BANDS.keys())}

    band = RATE_BANDS[lt]
    tier, adjustment = _credit_tier(credit_score)

    # Compute actual rates from repo + spread
    min_rate = round(repo + band["spread_min"], 2)
    max_rate = round(repo + band["spread_max"], 2)
    avg_rate = round(repo + band["spread_avg"], 2)

    # Personalized rate: avg + credit adjustment, clamped
    personalized_rate = round(avg_rate + adjustment, 2)
    personalized_rate = max(min_rate, min(max_rate, personalized_rate))

    # Build per-provider rates
    provider_rates = []
    for p in band.get("providers", []):
        p_rate = round(repo + p["spread"] + adjustment, 2)
        p_rate = max(min_rate, min(max_rate, p_rate))
        provider_rates.append({
            "name": p["name"],
            "rate": p_rate,
            "spread_over_repo": p["spread"],
        })

    result = {
        "loan_type": lt,
        "description": band["description"],
        "rbi_repo_rate": repo,
        "min_rate": min_rate,
        "max_rate": max_rate,
        "avg_rate": avg_rate,
        "personalized_rate": personalized_rate,
        "credit_score": credit_score,
        "credit_tier": tier,
        "rate_adjustment": adjustment,
        "typical_tenure": band["typical_tenure"],
        "providers": [p["name"] for p in band.get("providers", [])],
        "provider_rates": provider_rates,
        "notes": band.get("notes", ""),
    }

    log_action(logger, "info", "rate_predictor", "RATE_PREDICTED",
               f"loan_type={lt} | credit_score={credit_score} | repo={repo}% | "
               f"tier={tier} | min_rate={min_rate}% | max_rate={max_rate}% | "
               f"personalized_rate={personalized_rate}%")

    return result


def get_all_rates(credit_score: int = 700) -> list:
    """Get rate predictions for all loan types at current repo rate."""
    return [predict_rate(lt, credit_score) for lt in RATE_BANDS.keys()]

# ─────────────────────────────────────────────────────────
#  BOOT-TIME WEB SCRAPER & LLM SERIALIZER
# ─────────────────────────────────────────────────────────
def _fetch_live_bank_rates(current_repo: float):
    """
    On server boot, autonomously search the internet for today's bank rates across 
    all loan categories using a scatter-gather chunked approach.
    """
    try:
        from duckduckgo_search import DDGS
        from litellm import completion
        from config import settings
        import json
        import time
        import re
        
        log_action(logger, "info", "rate_predictor", "WEB_SCRAPE_STARTING", "Initializing scatter-gather interest rate fetch...")
        
        search_chunks = [
            # Chunk A: Retail Loans
            "latest interest rates 2026 home loan personal loan car loan India SBI HDFC ICICI Bajaj",
            # Chunk B: Specialized/Business Loans
            "latest interest rates 2026 business loan education loan MSME India Kotak Bank of Baroda Avanse",
            # Chunk C: Asset-Backed & Microfinance
            "latest interest rates 2026 gold loan mudra loan India Muthoot Manappuram Microfinance"
        ]
        
        master_live_rates = {}
        
        for search_query in search_chunks:
            try:
                # 1. Autonomous Web Scrape for Chunk
                results = DDGS().text(search_query, max_results=5)
                web_context = "\\n".join([r.get('body', '') for r in results])
                
                # 2. LLM Serialization
                prompt = f"""
                Extract the current interest rates for various loans in India from the text context below.
                Return ONLY a raw JSON dictionary (no markdown, no backticks).
                Keys: "home_loan", "personal_loan", "car_loan", "business_loan", "education_loan", "gold_loan", "mudra_loan".
                Values: dictionary mapping bank/NBFC shortnames (like "SBI", "HDFC", "Kotak", "Bajaj", "Muthoot") to their exact percentage float.
                Extract EVERY bank provider you can find in the text.
                
                CONTEXT:
                {web_context}
                """
                
                response = completion(
                    model=f"groq/{settings.LOAN_ADVISOR_MODEL}",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.0
                )
                
                raw = response.choices[0].message.content.strip()
                if raw.startswith("```"):
                    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
                    
                chunk_rates = json.loads(raw)
                
                # Merge into master dict
                for loan_type, banks in chunk_rates.items():
                    if loan_type not in master_live_rates:
                        master_live_rates[loan_type] = {}
                    master_live_rates[loan_type].update(banks)
                
            except Exception as e:
                log_action(logger, "warning", "rate_predictor", "CHUNK_PARSE_FAILED", f"chunk={search_query[:30]} | error={str(e)}")
            
            # Anti-Limiting defense
            time.sleep(2.5)
            
        # 3. Overwrite Global Spread Cache Using Master Data
        updated = 0
        for loan_type, banks in master_live_rates.items():
            if loan_type in RATE_BANDS:
                for provider in RATE_BANDS[loan_type]["providers"]:
                    for fetched_bank, fetched_rate in banks.items():
                        if fetched_bank.upper() in provider["name"].upper():
                            new_spread = round(float(fetched_rate) - current_repo, 2)
                            provider["spread"] = new_spread
                            updated += 1
                            break
                            
        if updated > 0:
            log_action(logger, "info", "rate_predictor", "LIVE_RATES_UPDATED", f"banks_updated={updated} | repo={current_repo}%")
            
    except Exception as e:
        log_action(logger, "warning", "rate_predictor", "LIVE_RATES_UPDATE_FAILED", f"error={str(e)}")

# Instantly fetch real rates and calibrate spreads whenever Uvicorn boots
_fetch_live_bank_rates(RBI_REPO_RATE)
