"""
LangGraph orchestrator nodes — each node is a processing step in the pipeline.
"""
import json
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from logger import get_logger, log_action

logger = get_logger("orchestrator_nodes")


def intent_classifier_node(state: dict) -> dict:
    """Classify intent + extract loan details in one LLM call with conversation context."""
    from orchestrator.intent_classifier import classify_and_extract

    messages = state.get("messages", [])
    history = state.get("conversation_history", []) or []

    # Get latest user message
    last_msg = ""
    for m in reversed(messages):
        if hasattr(m, 'content'):
            if getattr(m, 'type', '') == 'human' or not hasattr(m, 'type'):
                last_msg = m.content
                break
        elif isinstance(m, dict) and m.get("role") == "user":
            last_msg = m.get("content", "")
            break

    if not last_msg:
        last_msg = str(messages[-1]) if messages else ""

    # Single LLM call: classify intent AND extract loan details
    extracted = classify_and_extract(last_msg, history)
    intent = extracted["intent"]

    updates = {"intent": intent, "flow": "intent_classified"}

    if intent == "loan_inquiry":
        loan_amount = extracted.get("loan_amount")
        loan_type = extracted.get("loan_type", "unknown")
        tenure = extracted.get("tenure_months")
        amount_from_message = extracted.get("amount_from_message", False)

        # If LLM didn't find amount in current message, look in history
        if not amount_from_message and history:
            for h in reversed(history):
                if h["role"] == "user":
                    prev = classify_and_extract(h["content"])  # regex-only OK here
                    if prev.get("amount_from_message") and prev.get("loan_amount"):
                        loan_amount = prev["loan_amount"]
                        loan_type = loan_type if loan_type != "unknown" else prev.get("loan_type", "personal_loan")
                        log_action(logger, "info", "nodes", "AMOUNT_FROM_HISTORY",
                                   f"amount={loan_amount} | type={loan_type}")
                        break

        # Resolve unknown loan type
        if loan_type == "unknown":
            loan_type = "home_loan" if (loan_amount or 0) > 2_000_000 else "personal_loan"

        # Default tenure
        if tenure is None:
            tenure = 240 if loan_type == "home_loan" else 60

        updates["loan_request"] = {
            "loan_type": loan_type,
            "requested_amount": loan_amount or 100000,
            "requested_tenure": tenure,
            "_amount_from_message": amount_from_message,
        }

    log_action(logger, "info", "nodes", "NODE_EXECUTED",
               f"node=intent_classifier | message={last_msg[:60]}... | intent={intent} | "
               f"history_len={len(history)}")

    return updates


def _resolve_intent_from_context(message: str, history: list, default: str) -> str:
    """Use the last assistant response to resolve ambiguous general intent."""
    last_assistant = ""
    for h in reversed(history):
        if h["role"] == "assistant":
            last_assistant = h["content"].lower()
            break

    loan_context = any(kw in last_assistant for kw in [
        "loan assessment", "loan options comparison", "credit analysis",
        "compliance & eligibility", "emi/month", "approval likelihood"
    ])
    if loan_context:
        follow_up_policy = any(kw in message.lower() for kw in [
            "pmay", "mudra", "rbi", "scheme", "subsidy", "explain",
            "tell me", "documents", "why", "how come", "what about"
        ])
        if follow_up_policy:
            return "policy_question"

    return default


def _maybe_upgrade_to_policy(message: str, history: list, intent: str) -> str:
    """Upgrade loan_inquiry to policy_question when the message is clearly a
    follow-up question about WHY/HOW a scheme applies — not a new loan request."""
    import re
    msg_lower = message.lower()

    # Signals this is a clarification/follow-up, NOT a new loan request
    clarification_signals = [
        r'\bwhy\b', r'\bhow\s+(?:come|is|does|can|do)\b',
        r'\bexplain\b', r'\btell\s+me\b', r'\bwhat\s+about\b',
        r'\bplease\s+(?:explain|clarify|tell)\b'
    ]
    policy_signals = [
        r'\bpmay\b', r'\bmudra\b', r'\bscheme\b', r'\bsubsidy\b',
        r'\beligib\w*\b', r'\brbi\b', r'\bdocument\b'
    ]

    has_clarification = any(re.search(p, msg_lower) for p in clarification_signals)
    has_policy = any(re.search(p, msg_lower) for p in policy_signals)

    # Also check if there was a recent loan assessment in history
    last_assistant = ""
    for h in reversed(history):
        if h["role"] == "assistant":
            last_assistant = h["content"].lower()
            break

    prior_loan_response = any(kw in last_assistant for kw in [
        "loan assessment", "emi/month", "approval likelihood",
        "compliance & eligibility", "credit analysis"
    ])

    if has_clarification and has_policy and prior_loan_response:
        log_action(logger, "info", "nodes", "INTENT_UPGRADED",
                   f"loan_inquiry -> policy_question | msg={msg_lower[:60]}")
        return "policy_question"

    return intent


def profile_collector_node(state: dict) -> dict:
    """Check if user profile is complete and return status."""
    user_profile = state.get("user_profile") or {}

    required_fields = ["annual_income", "credit_score", "employment_months", "existing_loans"]
    missing = [f for f in required_fields if not user_profile.get(f)]

    is_complete = len(missing) == 0

    log_action(logger, "info", "nodes", "NODE_EXECUTED",
               f"node=profile_collector | complete={is_complete} | missing_fields={missing}")

    if not is_complete:
        missing_str = ", ".join(missing)
        response = (f"To provide accurate loan advice, I need a few more details about your financial profile. "
                   f"Please update the following in your profile: **{missing_str}**.\n\n"
                   f"You can update your profile using the dashboard on the left.")
        return {
            "profile_complete": False,
            "flow": "profile_incomplete",
            "agent_response": response
        }

    return {"profile_complete": True, "flow": "profile_complete"}


def credit_analysis_node(state: dict) -> dict:
    """Run Credit Analyst agent on user profile."""
    from agents.credit_analyst import run_credit_analysis

    user_profile = state.get("user_profile", {}).copy()
    loan_request  = state.get("loan_request", {})

    # Merge loan details so the risk model scores this specific loan
    if loan_request.get("requested_amount"):
        user_profile["requested_amount"] = loan_request["requested_amount"]
    if loan_request.get("loan_type"):
        user_profile["loan_type"] = loan_request["loan_type"]

    log_action(logger, "info", "nodes", "NODE_EXECUTING",
               f"node=credit_analysis | user_id={state.get('user_id', 'unknown')}")

    credit_profile = run_credit_analysis(user_profile)


    log_action(logger, "info", "nodes", "NODE_EXECUTED",
               f"node=credit_analysis | dti={credit_profile.get('dti_ratio', 'N/A')}% | "
               f"risk_tier={credit_profile.get('risk_tier', 'N/A')} | eligible={credit_profile.get('eligible', False)}")

    # Carry credit_score into credit_profile if not present
    if "credit_score" not in credit_profile:
        credit_profile["credit_score"] = user_profile.get("credit_score", 700)

    return {"credit_profile": credit_profile, "flow": "credit_analyzed"}


def loan_matching_node(state: dict) -> dict:
    """Run Loan Advisor agent to compare products."""
    from agents.loan_advisor import run_loan_advisory

    credit_profile = state.get("credit_profile", {})
    loan_request = state.get("loan_request", {})

    loan_type = loan_request.get("loan_type", "home_loan")
    amount = loan_request.get("requested_amount", 5000000)
    tenure = loan_request.get("requested_tenure", 240)

    log_action(logger, "info", "nodes", "NODE_EXECUTING",
               f"node=loan_matching | loan_type={loan_type} | amount=₹{amount:,.0f}")

    advisory = run_loan_advisory(credit_profile, loan_type, amount, tenure)

    log_action(logger, "info", "nodes", "NODE_EXECUTED",
               f"node=loan_matching | products_compared={len(advisory.get('products', []))}")

    return {"loan_advisory": advisory, "flow": "loans_matched"}


def compliance_check_node(state: dict) -> dict:
    """Run Risk & Compliance agent."""
    from agents.risk_compliance import run_compliance_check

    credit_profile = state.get("credit_profile", {})
    loan_request = state.get("loan_request", {})

    loan_type = loan_request.get("loan_type", "home_loan")
    amount = loan_request.get("requested_amount", 5000000)

    log_action(logger, "info", "nodes", "NODE_EXECUTING",
               f"node=compliance_check | loan_type={loan_type} | amount=₹{amount:,.0f}")

    compliance = run_compliance_check(credit_profile, loan_type, amount)

    log_action(logger, "info", "nodes", "NODE_EXECUTED",
               f"node=compliance_check | eligibility={compliance.get('eligibility', 'N/A')} | "
               f"approval_likelihood={compliance.get('approval_likelihood', 'N/A')}%")

    return {"compliance_result": compliance, "flow": "compliance_checked"}


def improvement_plan_node(state: dict) -> dict:
    """Generate improvement plan for ineligible users."""
    from agents.risk_compliance import generate_improvement_plan

    credit_profile = state.get("credit_profile", {})

    log_action(logger, "info", "nodes", "NODE_EXECUTING", "node=improvement_plan")

    plan = generate_improvement_plan(credit_profile)

    log_action(logger, "info", "nodes", "NODE_EXECUTED",
               f"node=improvement_plan | steps={len(plan.get('steps', []))}")

    return {"improvement_plan": plan, "flow": "improvement_planned"}


def rag_search_node(state: dict) -> dict:
    """
    Retrieval-Augmented Generation node.
    1. Retrieves relevant policy chunks from FAISS
    2. Passes them + conversation context to Groq LLM for synthesis
    3. Returns a contextual, personalized answer — not raw chunk dumps
    """
    from rag.pipeline import rag_pipeline

    messages = state.get("messages", [])
    history = state.get("conversation_history", []) or []
    user_profile = state.get("user_profile") or {}
    loan_request = state.get("loan_request") or {}

    # Get current user query
    query = ""
    for m in reversed(messages):
        if hasattr(m, 'content') and getattr(m, 'type', '') == 'human':
            query = m.content
            break
        elif isinstance(m, dict) and m.get("role") == "user":
            query = m.get("content", "")
            break
    if not query:
        query = str(messages[-1]) if messages else "loan policy"

    log_action(logger, "info", "nodes", "NODE_EXECUTING",
               f"node=rag_search | query={query[:80]}")

    # Step 1: RETRIEVE relevant chunks
    results = rag_pipeline.search(query, top_k=5)

    log_action(logger, "info", "nodes", "RAG_RETRIEVED",
               f"chunks={len(results)} | top_score={results[0]['score']:.4f}" if results else "chunks=0")

    # Step 2: GENERATE — use LLM to synthesize a smart answer
    response = _rag_generate(query, results, history, user_profile, loan_request)

    log_action(logger, "info", "nodes", "NODE_EXECUTED",
               f"node=rag_search | results={len(results)} | response_length={len(response)}")

    return {
        "rag_results": {"query": query, "results_count": len(results)},
        "agent_response": response,
        "flow": "rag_searched"
    }


def _rag_generate(query: str, chunks: list, history: list,
                  user_profile: dict, loan_request: dict) -> str:
    """
    Use Groq LLM to synthesize a contextual, personalized answer from:
    - The retrieved document chunks (knowledge)
    - The conversation history (context)
    - The user's financial profile (personalization)
    """
    from config import settings

    # Build context from retrieved chunks
    if chunks:
        knowledge_block = "\n\n".join(
            f"[Source: {c['source'].replace('_', ' ').replace('.txt', '').title()}]\n{c['text'][:600]}"
            for c in chunks[:4]
        )
    else:
        knowledge_block = "No specific documents found. Use general knowledge."

    # Build user context snippet
    profile_ctx = ""
    if user_profile.get("annual_income"):
        profile_ctx = (
            f"User Profile: Income=₹{user_profile['annual_income']:,.0f}/yr, "
            f"Credit Score={user_profile.get('credit_score', 'N/A')}, "
            f"City={user_profile.get('city', 'N/A')}, "
            f"Age={user_profile.get('age', 'N/A')}."
        )

    # Build loan context from memory (what was discussed)
    loan_ctx = ""
    if history:
        # Find the most recent loan assessment in assistant messages
        for h in reversed(history):
            if h["role"] == "assistant" and any(
                kw in h["content"].lower()
                for kw in ["loan assessment", "emi/month", "approval likelihood", "personal loan", "home loan"]
            ):
                # Extract a short summary
                lines = [l.strip() for l in h["content"].split("\n") if l.strip()][:6]
                loan_ctx = "Recent loan context: " + " | ".join(lines[:4])
                break

    if loan_request.get("requested_amount"):
        amt = loan_request["requested_amount"]
        ltype = loan_request.get("loan_type", "").replace("_", " ")
        loan_ctx += f"\nCurrent loan request: ₹{amt:,.0f} {ltype}."

    # Build recent conversation turns for LLM
    recent_turns = history[-6:] if len(history) > 6 else history
    conv_str = ""
    for h in recent_turns[:-1]:  # exclude last (current) message
        role = "User" if h["role"] == "user" else "Assistant"
        conv_str += f"{role}: {h['content'][:300]}\n"

    system_prompt = (
        "You are a knowledgeable AI Loan & Credit Advisor for Indian users. "
        "Answer the user's question using ONLY the provided document knowledge. "
        "Be specific, accurate, and personalize the answer to the user's situation if possible. "
        "Use markdown formatting (bold, bullet points). "
        "Do NOT mention that you are using retrieved documents — just answer naturally. "
        "If the user's question relates to their recent loan request or profile, refer to it explicitly."
    )

    user_content = (
        f"## Knowledge Base\n{knowledge_block}\n\n"
        f"## User Context\n{profile_ctx}\n{loan_ctx}\n\n"
        f"## Recent Conversation\n{conv_str}\n"
        f"## User Question\n{query}"
    )

    if not settings.GROQ_API_KEY:
        return _rag_fallback_format(query, chunks)

    try:
        from groq import Groq
        client = Groq(api_key=settings.GROQ_API_KEY)

        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",     # better reasoning for synthesis
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            max_tokens=700,
            temperature=0.3,
        )
        response = completion.choices[0].message.content.strip()
        log_action(logger, "info", "nodes", "RAG_GENERATED",
                   f"model=llama-3.3-70b-versatile | response_length={len(response)}")
        return response

    except Exception as e:
        log_action(logger, "warning", "nodes", "RAG_GENERATE_FAILED",
                   f"error={str(e)[:120]} | using raw chunk fallback")
        return _rag_fallback_format(query, chunks)


def _rag_fallback_format(query: str, chunks: list) -> str:
    """Fallback: format raw chunks if LLM generation fails."""
    if not chunks:
        return ("I couldn't find specific policy information for your query. "
                "Please try asking about RBI guidelines, PMAY, MUDRA loans, "
                "credit scores, or tax benefits.")
    parts = [f"📋 **Policy Information** — *{query[:80]}*\n"]
    for i, r in enumerate(chunks[:3], 1):
        source = r["source"].replace("_", " ").replace(".txt", "").title()
        parts.append(f"**{i}. From {source}** (relevance: {r['score']:.0%})\n{r['text'][:400]}...\n")
    return "\n---\n".join(parts)



def response_formatter_node(state: dict) -> dict:
    """Format the final response from all agent outputs."""
    intent = state.get("intent", "general")
    flow = state.get("flow", "")

    log_action(logger, "info", "nodes", "NODE_EXECUTING",
               f"node=response_formatter | intent={intent} | flow={flow}")

    if state.get("agent_response") and flow in ["rag_searched", "profile_incomplete"]:
        # Already have a response
        log_action(logger, "info", "nodes", "NODE_EXECUTED",
                   f"node=response_formatter | response_length={len(state['agent_response'])}")
        return {"flow": "response_ready"}

    if intent == "loan_inquiry":
        response = _format_loan_response(state)
    elif intent == "profile_update":
        response = "✅ Your profile has been updated successfully. You can now ask me about loan eligibility, EMI calculations, or policy information!"
    else:
        # Use real LLM for general chat instead of hardcoded placeholder
        response = _llm_general_response(state)

    log_action(logger, "info", "nodes", "NODE_EXECUTED",
               f"node=response_formatter | response_length={len(response)}")

    return {"agent_response": response, "flow": "response_ready"}


def _llm_general_response(state: dict) -> str:
    """Use Groq LLM to respond to general/greeting messages with conversation context."""
    from config import settings

    history = state.get("conversation_history", []) or []
    messages = state.get("messages", [])
    user_profile = state.get("user_profile") or {}

    # Get current message
    current_msg = ""
    for m in reversed(messages):
        if hasattr(m, "content") and (getattr(m, "type", "") == "human" or not hasattr(m, "type")):
            current_msg = m.content
            break

    # Build profile context snippet
    profile_ctx = ""
    if user_profile.get("annual_income"):
        name = user_profile.get("full_name", "the user")
        profile_ctx = (f"The user's name is {name}. "
                       f"Income: ₹{user_profile['annual_income']:,.0f}/yr, "
                       f"Credit Score: {user_profile.get('credit_score', 'N/A')}, "
                       f"City: {user_profile.get('city', 'N/A')}.")

    # Build recent conversation for LLM
    recent = history[-8:] if len(history) > 8 else history
    conv_text = "\n".join(
        f"{m['role'].upper()}: {m['content'][:300]}" for m in recent[:-1]
    ) if len(recent) > 1 else "(No prior conversation)"

    system_prompt = (
        "You are a friendly, knowledgeable AI Loan & Credit Advisor for Indian users. "
        "You assist users with home loans, personal loans, car loans, MUDRA, PMAY, "
        "RBI guidelines, EMI calculations, and credit score improvement.\n"
        f"{profile_ctx}\n"
        "Keep your response concise, friendly, and relevant. "
        "If the user greets you, respond warmly and mention 2-3 things you can help with. "
        "If the user asks something outside finance, gently guide them back."
    )

    if not settings.GROQ_API_KEY:
        return _fallback_general_response()

    try:
        from groq import Groq
        client = Groq(api_key=settings.GROQ_API_KEY)

        chat_messages = [{"role": "system", "content": system_prompt}]

        # Add recent history
        for m in recent[:-1]:
            role = "user" if m["role"] == "user" else "assistant"
            chat_messages.append({"role": role, "content": m["content"][:500]})

        # Add current message
        chat_messages.append({"role": "user", "content": current_msg})

        completion = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=chat_messages,
            max_tokens=400,
            temperature=0.7,
        )
        response = completion.choices[0].message.content.strip()
        log_action(logger, "info", "nodes", "LLM_GENERAL_RESPONSE",
                   f"model=llama-3.1-8b-instant | length={len(response)}")
        return response
    except Exception as e:
        log_action(logger, "warning", "nodes", "LLM_GENERAL_FALLBACK",
                   f"error={str(e)[:100]} | using static response")
        return _fallback_general_response()


def _fallback_general_response() -> str:
    """Static fallback if Groq is unavailable."""
    return (
        "Hi! I'm your AI Loan & Credit Advisor. I can help you with:\n\n"
        "🏠 **Loan eligibility** — Home, personal, car, business loans\n"
        "📊 **EMI calculations** — Monthly payment breakdowns\n"
        "📋 **Policy info** — RBI guidelines, PMAY, MUDRA schemes\n"
        "💡 **Credit improvement** — Tips to boost your CIBIL score\n\n"
        "What would you like help with today?"
    )


def _format_loan_response(state: dict) -> str:
    """Format a comprehensive loan inquiry response."""
    credit_profile = state.get("credit_profile", {})
    loan_advisory = state.get("loan_advisory", {})
    compliance = state.get("compliance_result", {})
    improvement = state.get("improvement_plan")
    loan_request = state.get("loan_request", {})

    parts = []

    # Header
    loan_type = loan_request.get("loan_type", "loan").replace("_", " ").title()
    amount = loan_request.get("requested_amount", 0)
    parts.append(f"## 🏦 {loan_type} Assessment — ₹{amount:,.0f}\n")

    # Credit Analysis
    if credit_profile:
        risk_emoji = {"Low": "🟢", "Medium": "🟡", "High": "🔴"}.get(credit_profile.get("risk_tier"), "⚪")
        parts.append(f"### 📊 Credit Analysis\n")
        parts.append(f"- **Risk Tier:** {risk_emoji} {credit_profile.get('risk_tier', 'N/A')}")
        parts.append(f"- **Credit Rating:** {credit_profile.get('credit_tier', 'N/A')}")
        parts.append(f"- **DTI Ratio:** {credit_profile.get('dti_ratio', 'N/A')}%")
        parts.append(f"- **Max EMI Capacity:** ₹{credit_profile.get('max_emi_capacity', 0):,.0f}/month")
        parts.append(f"- **Assessment:** {credit_profile.get('analysis_summary', 'N/A')}\n")

    # Loan Products
    if loan_advisory and loan_advisory.get("products"):
        parts.append(f"### 💰 Loan Options Comparison\n")
        parts.append(f"| Bank | Rate | Tenure | EMI/month | Total Interest | Total Cost |")
        parts.append(f"|------|------|--------|-----------|---------------|------------|")
        for p in loan_advisory["products"]:
            parts.append(f"| {p.get('bank_name', 'N/A')} | {p.get('rate', 'N/A')}% | "
                        f"{p.get('tenure_months', 0)} mo | "
                        f"₹{p.get('emi', 0):,.0f} | ₹{p.get('total_interest', 0):,.0f} | "
                        f"₹{p.get('total_cost', 0):,.0f} |")
        parts.append(f"\n**Recommendation:** {loan_advisory.get('recommendation', 'N/A')}")
        parts.append(f"\n**Affordability:** {loan_advisory.get('affordability_verdict', 'N/A')}\n")

    # Compliance
    if compliance:
        elig_emoji = {"yes": "✅", "no": "❌", "conditional": "⚠️"}.get(compliance.get("eligibility"), "❓")
        parts.append(f"### 📋 Compliance & Eligibility\n")
        parts.append(f"- **Eligibility:** {elig_emoji} {compliance.get('eligibility', 'N/A').upper()}")
        parts.append(f"- **Approval Likelihood:** {compliance.get('approval_likelihood', 'N/A')}%")

        if compliance.get("scheme_eligibility"):
            parts.append(f"\n**Government Schemes:**")
            for scheme, status in compliance["scheme_eligibility"].items():
                parts.append(f"- {scheme}: {status}")

        if compliance.get("red_flags"):
            parts.append(f"\n**⚠️ Red Flags:**")
            for flag in compliance["red_flags"]:
                parts.append(f"- {flag}")

        if compliance.get("required_documents"):
            parts.append(f"\n**📄 Required Documents:**")
            for doc in compliance["required_documents"][:8]:
                parts.append(f"- {doc}")
            if len(compliance.get("required_documents", [])) > 8:
                parts.append(f"- *...and {len(compliance['required_documents']) - 8} more*")

    # Improvement Plan
    if improvement and improvement.get("steps"):
        parts.append(f"\n### 💡 Credit Improvement Plan\n")
        for step in improvement["steps"]:
            parts.append(f"**Step {step['step']}: {step['action']}** ({step.get('timeline', 'N/A')})")
            parts.append(f"- {step['details']}")
            parts.append(f"- Expected: {step.get('expected_improvement', 'N/A')}\n")

    return "\n".join(parts)
