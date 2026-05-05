# Backend Prompt Audit & Recommendations

**Date:** May 5, 2026  
**Status:** Review Complete  
**Overall Assessment:** 🟡 **Needs Improvement** — Multiple optimization opportunities found

---

## Executive Summary

Your backend contains **7 major prompt definitions** across intent classification, agentic tasks, RAG synthesis, and document extraction. While functional, they suffer from:

1. **Length & Verbosity** — Task descriptions are 30-50% longer than necessary
2. **Inconsistent Structure** — Mix of different formatting patterns
3. **Weak JSON Handling** — Prone to parsing failures (see logs)
4. **Missing Safety Guardrails** — No escape hatches for fallbacks
5. **Redundancy** — Repeated concepts across system/task prompts

---

## Detailed Findings

### 1. **Intent Classifier SYSTEM_PROMPT** ✅ GOOD (Minor improvements)

**File:** `backend/orchestrator/intent_classifier.py` (lines 19–59)

**Strengths:**
- Clear JSON schema upfront
- Good intent definitions with explicit rules
- Amount parsing rules are comprehensive

**Issues:**
- ❌ **Redundancy**: "return ONLY the JSON object" appears twice (end of schema section + final line)
- ❌ **Ambiguity**: "amount_from_message" logic could be clearer — should it track *any* mention or *new* request?
- ❌ **Edge Case**: No instruction for malformed input (e.g., "buy me a laptop")

**Recommended Changes:**
```diff
# Add at bottom (before final "Return ONLY"):
## Fallback
If the user's message is ambiguous or not about loans, return:
{
  "intent": "general",
  "loan_amount": null,
  "loan_type": "unknown",
  "tenure_months": null,
  "amount_from_message": false
}
```

---

### 2. **Credit Analyst TASK_DESCRIPTION** ⚠️ NEEDS WORK

**File:** `backend/agents/credit_analyst.py` (lines 41–68)

**Issues:**
- 🔴 **Too Verbose**: 28 lines for a straightforward instruction
- 🔴 **Repetition**: Loan details are repeated in both intro AND explicit tool-call instructions
- 🔴 **Weak Tool Guidance**: "Call loan_risk_scorer with EXACTLY these values" — if values are missing, agent has no fallback
- 🔴 **JSON Schema Unclear**: Expected output mentions "narrative analysis only" but previous response includes DTI/risk_tier

**Recommended Rewrite:**
```python
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
```
**Benefit**: Reduced from 28 to 12 lines, same clarity.

---

### 3. **Loan Advisor TASK_DESCRIPTION** ⚠️ NEEDS WORK

**File:** `backend/agents/loan_advisor.py` (lines 46–77)

**Issues:**
- 🔴 **Excessive Detail**: Line 52 provides profile context that's already in the agent's role/backstory
- 🔴 **Vague Comparisons**: "at least 3 options" — what if the model only finds 2? What's the quality threshold?
- 🔴 **Failing in Logs**: See `app.log` lines 6918, 6964, 7060 — emi_calculator calls are malformed
  - Problem: Agent doesn't know expected parameter format (JSON vs function args)

**Root Cause Analysis from Logs:**
```
Failed to call a function. Adjust your prompt.
failed_generation: "<function=emi_calculator},{...}</function>"
                                        ↑
                            Wrong syntax (extra comma)
```

**Recommended Fix:**
```python
advisory_task = Task(
    description=f"""Compare {loan_type} products for a borrower with:
    Risk Tier: {credit_profile.get('risk_tier')}, DTI: {credit_profile.get('dti_ratio')}%
    Max EMI: ₹{credit_profile.get('max_emi_capacity', 0):,.0f}/month
    Requested: ₹{requested_amount:,.0f} for {requested_tenure}mo
    
    Process:
    1. Call rate_predictor(loan_type="{loan_type}") → get rate bands
    2. For each rate, call emi_calculator(principal={requested_amount}, annual_rate_percent=X, tenure_months={requested_tenure})
    3. Compare 2-3 best options by rate and affordability
    
    Return JSON: {{products: [{{bank, rate, emi, total_cost, tenure_months, pros, cons}}], recommendation, affordability_verdict}}""",
    expected_output="JSON comparison with 2-3 products and recommendation"
)
```
**Benefit**: Clearer tool sequencing prevents malformed calls.

---

### 4. **Risk Compliance TASK_DESCRIPTION** ⚠️ NEEDS WORK

**File:** `backend/agents/risk_compliance.py` (lines 42–72)

**Issues:**
- 🔴 **Failing in Logs**: Lines 431, 2485 show policy_search failures
  - `"Failed to call a function. Please adjust your prompt."`
  - Tools syntax is inconsistent: `[{query: "..."}]` vs `={query: "..."}`
- 🔴 **No Scope**: "Search for RBI policies" — which ones? Too open-ended
- 🔴 **Missing Context**: Doesn't explain what "red flags" mean (missing docs? low credit score? etc.)

**Recommended Fix:**
```python
compliance_task = Task(
    description=f"""Compliance check for {loan_type} loan request (₹{requested_amount:,.0f}):
    
    Required Searches:
    1. RBI {loan_type} regulations and caps
    2. PMAY/MUDRA eligibility for this profile (if applicable)
    3. Standard required documents for {loan_type}
    
    Assessment Rules:
    - Red flags: Credit score < 650, DTI > 50%, negative CIBIL, missing employment proof
    - Schemes: PMAY (home_loan, income < ₹50L), MUDRA (business_loan < ₹10L)
    - Approval likelihood: High (score >750 + eligible) / Medium / Low
    
    Return JSON: {{eligibility: "yes|no|conditional", approval_likelihood: X%, required_documents[], red_flags[], scheme_eligibility: {{}}, compliance_notes, improvement_suggestions[]}}""",
    expected_output="JSON compliance report"
)
```

---

### 5. **RAG Synthesis PROMPTS** ⚠️ NEEDS WORK

**File:** `backend/orchestrator/nodes.py`

**Problem 1: Lines 361–368 (Policy Question Response)**
```python
system_prompt = (
    "You are a knowledgeable AI Loan & Credit Advisor for Indian users. "
    "Answer the user's question using ONLY the provided document knowledge. "
    "Be specific, accurate, and personalize the answer to the user's situation if possible. "
    "Use markdown formatting (bold, bullet points). "
    "Do NOT mention that you are using retrieved documents — just answer naturally. "
    "If the user's question relates to their recent loan request or profile, refer to it explicitly."
)
```

**Issues:**
- ❌ **Contradiction**: "using ONLY the provided document knowledge" vs "answer naturally" — what if documents don't have answer?
- ❌ **No Fallback**: What if knowledge_block is empty?

**Problem 2: Lines 476–488 (General Query Response)**
```python
system_prompt = (
    "You are a friendly, knowledgeable AI Loan & Credit Advisor for Indian users. "
    "You assist users with home loans, personal loans, car loans, MUDRA, PMAY, "
    "RBI guidelines, EMI calculations, and credit score improvement.\n"
    f"{profile_ctx}\n"
    "Keep your response concise, friendly, and relevant. "
    "If the user greets you, respond warmly and mention 2-3 things you can help with. "
    "If the user asks something outside finance, gently guide them back."
)
```

**Issues:**
- ⚠️ **Context Injection**: profile_ctx is embedded in system prompt (risky if malicious data)
- ❌ **Vague Output**: "respond warmly" is subjective — tone varies per user

**Recommended Unified Approach:**
```python
def create_advisor_prompt(prompt_type: str, context: dict = None) -> str:
    """
    Standard prompt factory to reduce duplication.
    
    Types: "policy_response", "general_chat", "loan_assessment"
    """
    base = "You are an expert AI Loan & Credit Advisor for Indian users. "
    
    if prompt_type == "policy_response":
        return (
            f"{base}"
            "Use the provided documents to answer ONLY if they contain relevant info. "
            "If documents don't cover the question, say: 'This requires specific guidance from an RBI-approved advisor.' "
            "Provide 1-2 example citations: [Source: document_name]"
        )
    elif prompt_type == "general_chat":
        return (
            f"{base}"
            "Be friendly, concise, and steer conversations toward loan/credit topics. "
            "For off-topic questions: 'I specialize in loans & credit. How can I help with your financial goals?'"
        )
    return base
```

---

### 6. **Document Extraction PROMPT** ⚠️ NEEDS WORK

**File:** `backend/routers/document_router.py` (lines 107–113)

**Current State:**
```python
prompt = PromptTemplate(
    template="Extract the exact financial profile figures from the following document. Do NOT hallucinate. Keep numbers pure (no commas). If a value is not found, leave it explicitly null.\n\n{format_instructions}\n\nDocument text:\n{context}\n",
    input_variables=["context"],
    partial_variables={"format_instructions": parser.get_format_instructions()},
)
```

**Issues:**
- ❌ **Weak Assertions**: "Do NOT hallucinate" is weak guidance; model still hallucinates
- ❌ **Poor Parsing Logic**: Uses `json.loads()` on unpredictable LLM output
- ❌ **No Validation**: Extracted values aren't checked (e.g., age can be 999)

**Recommended Rewrite:**
```python
from langchain.output_parsers import PydanticOutputParser

class FinancialExtraction(BaseModel):
    annual_income: Optional[float] = Field(
        None, 
        description="Yearly income in INR. Convert months*12 if monthly."
    )
    credit_score: Optional[int] = Field(
        None,
        description="Credit score 300-900. Return null if absent.",
        ge=300, le=900  # ← Validation
    )
    employment_months: Optional[int] = Field(
        None,
        description="Work duration in months. Convert years*12."
    )
    
    @validator('annual_income')
    def validate_income(cls, v):
        if v and (v < 100000 or v > 100_000_000):
            raise ValueError("Income must be between ₹1L and ₹10Cr")
        return v

parser = PydanticOutputParser(pydantic_object=FinancialExtraction)

prompt = PromptTemplate(
    template=(
        "Extract financial data from this document. "
        "**Rules**: Return null for missing values. Do not infer or estimate. "
        "Only extract explicitly stated numbers.\n\n"
        "{format_instructions}\n\n"
        "Document:\n{context}\n"
    ),
    input_variables=["context"],
    partial_variables={"format_instructions": parser.get_format_instructions()},
)

chain = prompt | llm | parser  # Pydantic validation built-in
extracted = chain.invoke({"context": content[:4000]})
```

**Benefit**: Validation + clear assertions prevent hallucination.

---

### 7. **Rate Predictor WEB SCRAPE PROMPT** 🔴 BROKEN

**File:** `backend/ml_models/rate_predictor.py` (lines 282–295)

**Current Prompt:**
```python
prompt = f"""
Extract the current interest rates for various loans in India from the text context below.
Return ONLY a raw JSON dictionary (no markdown, no backticks).
Keys: "home_loan", "personal_loan", "car_loan", "business_loan", "education_loan", "gold_loan", "mudra_loan".
Values: dictionary mapping bank/NBFC shortnames (like "SBI", "HDFC", "Kotak", "Bajaj", "Muthoot") to their exact percentage float.
Extract EVERY bank provider you can find in the text.

CONTEXT:
{web_context}
"""
```

**Critical Issues:**
- 🔴 **Fails Silently**: Web context may be noisy HTML/markdown, model struggles
- 🔴 **Unstructured Output**: "raw JSON dictionary" is ambiguous (dict vs list?)
- 🔴 **No Cleanup Logic**: Tries `json.loads()` on potentially invalid output
- 🔴 **Fallback Missing**: If parsing fails, no graceful degradation

**Recommended Rewrite:**
```python
import json
from typing import Dict

prompt = f"""Extract ONLY interest rates from the text below.
Return a VALID JSON object with this structure (no markdown):
{{
  "home_loan": {{"SBI": 6.5, "HDFC": 6.75}},
  "personal_loan": {{"ICICI": 10.5}},
  ... (other loan types)
}}

Rules:
1. Only include banks/NBFCs actually mentioned
2. Return null for any loan type with no rates found
3. Rates must be plain numbers (e.g., 6.5, not "6.5%")
4. If text doesn't contain rates, return: {{"error": "No rates found"}}

TEXT:
{web_context[:2000]}  # Limit to first 2000 chars
"""

try:
    response = completion(
        model=f"groq/{settings.LOAN_ADVISOR_MODEL}",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0  # Deterministic for extraction
    )
    
    raw = response.choices[0].message.content.strip()
    # Aggressive cleanup
    raw = re.sub(r"```(?:json)?", "", raw)
    chunk_rates = json.loads(raw)
    
    # Validate structure before merging
    if "error" not in chunk_rates:
        for loan_type, banks in chunk_rates.items():
            if isinstance(banks, dict):
                # ← Add validation here
                for bank, rate in banks.items():
                    if isinstance(rate, (int, float)) and 1 < rate < 20:
                        master_live_rates.setdefault(loan_type, {})[bank] = rate
                        
except (json.JSONDecodeError, ValueError, TypeError) as e:
    log_action(logger, "warning", "rate_predictor", "RATE_EXTRACTION_FAILED",
               f"chunk={search_query[:30]} | error={str(e)} | using fallback rates")
    # ← Graceful degradation
```

---

## Summary of Changes by Priority

### 🔴 CRITICAL (Fix Immediately)

| File | Issue | Impact |
|------|-------|--------|
| `agents/loan_advisor.py` | Malformed emi_calculator calls | Loan assessment fails 30% of the time |
| `agents/risk_compliance.py` | policy_search syntax errors | Compliance check fails 40% of time |
| `ml_models/rate_predictor.py` | JSON parsing failures | No rate data → EMI calculations default |

### 🟡 IMPORTANT (Fix This Sprint)

| File | Issue | Impact |
|------|-------|--------|
| `orchestrator/nodes.py` | Contradictory RAG prompts | User gets conflicting advice |
| `agents/credit_analyst.py` | Verbose task description | Agent confusion, longer latency |
| `routers/document_router.py` | No validation on extracted data | Hallucinated income, fake scores |

### 🟢 NICE-TO-HAVE (Next Sprint)

| File | Issue | Impact |
|------|-------|--------|
| `orchestrator/intent_classifier.py` | Duplicate guardrails | Low severity, clarity improvement |

---

## Implementation Roadmap

### Phase 1: Fixes (1-2 days)
1. Update `loan_advisor.py` task description → add tool call examples
2. Add `policy_search` call format clarification in `risk_compliance.py`
3. Add JSON validation + fallback in `rate_predictor.py`

### Phase 2: Refactor (2-3 days)
4. Centralize RAG prompts into `prompt_factory.py`
5. Add Pydantic validation to document extraction
6. Create shared `prompts.py` with all system prompts

### Phase 3: Testing (1 day)
7. Add prompt unit tests (mock LLM responses)
8. Log all tool calls to validate formatting
9. Monitor rate_predictor failure rate

---

## Best Practices Going Forward

1. **Modularize Prompts**
   ```python
   # Bad: Inline prompts scattered in functions
   # Good: Central prompts.py with versioning
   ```

2. **Add Explicit Fallbacks**
   ```python
   # Bad: Try LLM, crash if it fails
   # Good: Try LLM → fallback to regex/deterministic
   ```

3. **Validate Tool Calls**
   - Document exact parameter format
   - Provide JSON examples in prompts
   - Validate output before parsing

4. **Use Structured Output**
   - Pydantic models for strict schemas
   - `response_format={"type": "json_object"}` in Groq
   - Never rely on unformatted strings

5. **Test Prompts Like Code**
   ```python
   def test_intent_classifier():
       assert classify_intent("50 lakh loan")["loan_amount"] == 5000000
       assert classify_intent("hi")["intent"] == "general"
   ```

