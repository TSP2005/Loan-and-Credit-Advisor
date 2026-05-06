"""
LangGraph state machine — compiles the graph with conditional routing.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langgraph.graph import StateGraph, END
from orchestrator.state import OrchestratorState
from orchestrator.nodes import (
    intent_classifier_node,
    profile_collector_node,
    credit_analysis_node,
    loan_matching_node,
    compliance_check_node,
    improvement_plan_node,
    rag_search_node,
    response_formatter_node,
    email_report_node,
)
from logger import get_logger, log_action

logger = get_logger("graph")

_LOAN_TYPES = {
    "home_loan", "personal_loan", "car_loan", "business_loan",
    "education_loan", "gold_loan", "mudra_loan",
}


def _route_after_intent(state: dict) -> str:
    """Route based on classified intent."""
    intent = state.get("intent", "general")
    log_action(logger, "info", "graph", "EDGE_TRAVERSED",
               f"from=intent_classifier | condition=intent={intent}")

    if intent == "loan_inquiry":
        return "profile_collector"
    elif intent == "policy_question":
        return "rag_search"
    elif intent == "profile_update":
        return "response_formatter"
    elif intent == "send_report":
        topic = (state.get("report_topic") or "").lower().replace(" ", "_")
        if any(lt in topic for lt in _LOAN_TYPES):
            return "profile_collector"      # Run full loan pipeline first
        elif topic:
            return "rag_search"             # Policy/scheme topic → RAG first
        else:
            return "email_report"           # No topic → compile from conversation
    else:
        return "response_formatter"


def _route_after_profile(state: dict) -> str:
    """Route based on profile completeness."""
    complete = state.get("profile_complete", False)
    log_action(logger, "info", "graph", "EDGE_TRAVERSED",
               f"from=profile_collector | condition=profile_complete={complete}")
    if complete:
        return "credit_analysis"
    else:
        return "response_formatter"


def _route_after_credit(state: dict) -> str:
    """Route based on eligibility."""
    credit_profile = state.get("credit_profile", {})
    eligible = credit_profile.get("eligible", False)
    log_action(logger, "info", "graph", "EDGE_TRAVERSED",
               f"from=credit_analysis | condition=eligible={eligible}")
    if eligible:
        return "loan_matching"
    else:
        return "improvement_plan"


def _route_after_compliance(state: dict) -> str:
    """After compliance, go to email_report if send_report intent, else response_formatter."""
    if state.get("intent") == "send_report":
        return "email_report"
    return "response_formatter"


def _route_after_improvement(state: dict) -> str:
    """After improvement plan, go to email_report if send_report intent, else response_formatter."""
    if state.get("intent") == "send_report":
        return "email_report"
    return "response_formatter"


def _route_after_formatter(state: dict) -> str:
    """After response_formatter, send report email if dual-intent was detected."""
    if state.get("send_report_after"):
        return "email_report"
    return END


def _route_after_rag(state: dict) -> str:
    """After RAG search, go to email_report if send_report intent, else response_formatter."""
    if state.get("intent") == "send_report":
        return "email_report"
    return "response_formatter"


def build_graph() -> StateGraph:
    """Build and compile the LangGraph orchestrator."""
    log_action(logger, "info", "graph", "GRAPH_BUILDING", "Starting graph compilation")

    graph = StateGraph(OrchestratorState)

    # Add nodes
    graph.add_node("intent_classifier", intent_classifier_node)
    graph.add_node("profile_collector", profile_collector_node)
    graph.add_node("credit_analysis", credit_analysis_node)
    graph.add_node("loan_matching", loan_matching_node)
    graph.add_node("compliance_check", compliance_check_node)
    graph.add_node("improvement_plan", improvement_plan_node)
    graph.add_node("rag_search", rag_search_node)
    graph.add_node("response_formatter", response_formatter_node)
    graph.add_node("email_report", email_report_node)

    # Entry point
    graph.set_entry_point("intent_classifier")

    # From intent classifier
    graph.add_conditional_edges(
        "intent_classifier",
        _route_after_intent,
        {
            "profile_collector": "profile_collector",
            "rag_search": "rag_search",
            "response_formatter": "response_formatter",
            "email_report": "email_report",
        }
    )

    # From profile collector
    graph.add_conditional_edges(
        "profile_collector",
        _route_after_profile,
        {
            "credit_analysis": "credit_analysis",
            "response_formatter": "response_formatter",
        }
    )

    # From credit analysis
    graph.add_conditional_edges(
        "credit_analysis",
        _route_after_credit,
        {
            "loan_matching": "loan_matching",
            "improvement_plan": "improvement_plan",
        }
    )

    # loan_matching → compliance_check
    graph.add_edge("loan_matching", "compliance_check")

    # compliance_check → conditional (report or formatter)
    graph.add_conditional_edges(
        "compliance_check",
        _route_after_compliance,
        {
            "email_report": "email_report",
            "response_formatter": "response_formatter",
        }
    )

    # improvement_plan → conditional (report or formatter)
    graph.add_conditional_edges(
        "improvement_plan",
        _route_after_improvement,
        {
            "email_report": "email_report",
            "response_formatter": "response_formatter",
        }
    )

    # rag_search → conditional (report or formatter)
    graph.add_conditional_edges(
        "rag_search",
        _route_after_rag,
        {
            "email_report": "email_report",
            "response_formatter": "response_formatter",
        }
    )

    # email_report → END
    graph.add_edge("email_report", END)

    # response_formatter → conditional (END or email_report for dual-intent)
    graph.add_conditional_edges(
        "response_formatter",
        _route_after_formatter,
        {
            "email_report": "email_report",
            END: END,
        }
    )

    compiled = graph.compile()
    log_action(logger, "info", "graph", "GRAPH_COMPILED",
               "LangGraph orchestrator compiled with email_report_node")
    return compiled


# Build at module level
orchestrator_graph = build_graph()
