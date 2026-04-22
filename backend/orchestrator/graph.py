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
)
from logger import get_logger, log_action

logger = get_logger("graph")


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
        return "response_formatter"  # Ask user to complete profile


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


def _route_after_improvement(state: dict) -> str:
    """After improvement plan, go to response formatter."""
    log_action(logger, "info", "graph", "EDGE_TRAVERSED",
               f"from=improvement_plan | to=response_formatter")
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

    # Set entry point
    graph.set_entry_point("intent_classifier")

    # Conditional edges from intent classifier
    graph.add_conditional_edges(
        "intent_classifier",
        _route_after_intent,
        {
            "profile_collector": "profile_collector",
            "rag_search": "rag_search",
            "response_formatter": "response_formatter",
        }
    )

    # Conditional edges from profile collector
    graph.add_conditional_edges(
        "profile_collector",
        _route_after_profile,
        {
            "credit_analysis": "credit_analysis",
            "response_formatter": "response_formatter",
        }
    )

    # Conditional edges from credit analysis
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

    # compliance_check → response_formatter
    graph.add_edge("compliance_check", "response_formatter")

    # improvement_plan → response_formatter
    graph.add_edge("improvement_plan", "response_formatter")

    # rag_search → response_formatter
    graph.add_edge("rag_search", "response_formatter")

    # response_formatter → END
    graph.add_edge("response_formatter", END)

    compiled = graph.compile()

    log_action(logger, "info", "graph", "GRAPH_COMPILED",
               "LangGraph orchestrator compiled successfully with all nodes and edges")

    return compiled


# Build the graph at module level
orchestrator_graph = build_graph()
