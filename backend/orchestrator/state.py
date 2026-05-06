"""
LangGraph state definition for the orchestrator.
"""
from typing import TypedDict, Optional, Annotated, List
from langgraph.graph.message import add_messages


class OrchestratorState(TypedDict):
    """State that flows through the LangGraph orchestrator."""
    # User info
    user_id: str
    messages: Annotated[list, add_messages]

    # Full conversation history [{role, content}, ...] for context-aware intent
    conversation_history: Optional[List[dict]]

    # Profile data
    user_profile: Optional[dict]
    profile_complete: bool

    # Analysis results
    credit_profile: Optional[dict]
    loan_advisory: Optional[dict]
    compliance_result: Optional[dict]
    improvement_plan: Optional[dict]
    rag_results: Optional[dict]

    # Request context
    loan_request: Optional[dict]
    report_topic: Optional[str]   # For send_report intent: free-form topic or None
    send_report_after: Optional[bool]  # True when user wants loan answer + report in same message

    # Routing
    intent: str  # loan_inquiry, policy_question, profile_update, send_report, general
    flow: str    # current stage in the flow

    # Final output
    agent_response: str
