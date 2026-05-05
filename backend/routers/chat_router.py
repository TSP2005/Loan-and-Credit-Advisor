"""
WebSocket chat router — real-time conversation with the LangGraph orchestrator.
Maintains per-user, per-session conversation memory across messages.
"""
import json
import uuid
import traceback
from datetime import datetime, timezone
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from auth.jwt_handler import verify_token, get_current_user
from auth.service import user_service
from logger import get_logger, log_action

logger = get_logger("chat_router")
router = APIRouter(tags=["Chat"])

# Store active WebSocket connections
active_connections: dict = {}

# Per-session conversation history: {session_id: [{"role": "user"|"assistant", "content": str}]}
session_memory: dict = {}

# Chat sessions per user: {user_id: [{"session_id": str, "title": str, "created_at": str, "last_message": str}]}
user_sessions: dict = {}

MAX_MEMORY_TURNS = 10  # Keep last 10 exchanges (20 messages) to avoid token bloat

STORAGE_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "chromadb_storage", "chat_data.json")

def _load_memory():
    global session_memory, user_sessions
    if os.path.exists(STORAGE_FILE):
        try:
            with open(STORAGE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                session_memory = data.get("session_memory", {})
                user_sessions = data.get("user_sessions", {})
        except Exception:
            pass

def _save_memory():
    try:
        os.makedirs(os.path.dirname(STORAGE_FILE), exist_ok=True)
        with open(STORAGE_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "session_memory": session_memory,
                "user_sessions": user_sessions
            }, f)
    except Exception:
        pass

_load_memory()

# ─── Session Management Endpoints ────────────────────────────────────────────

@router.get("/chat/sessions/{user_id}")
async def list_sessions(user_id: str, current_user: dict = Depends(get_current_user)):
    """List all chat sessions for a user."""
    if current_user.get("sub") != user_id:
        raise HTTPException(status_code=403, detail="Unauthorized")
    sessions = user_sessions.get(user_id, [])
    return {"sessions": sessions}


@router.post("/chat/sessions/{user_id}")
async def create_session(user_id: str, body: dict = {}, current_user: dict = Depends(get_current_user)):
    """Create a new chat session."""
    if current_user.get("sub") != user_id:
        raise HTTPException(status_code=403, detail="Unauthorized")
    session_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    session = {
        "session_id": session_id,
        "title": body.get("title", f"Chat {len(user_sessions.get(user_id, [])) + 1}"),
        "created_at": now,
        "last_message": "",
        "last_updated": now,
    }
    if user_id not in user_sessions:
        user_sessions[user_id] = []
    user_sessions[user_id].insert(0, session)  # Newest first
    session_memory[session_id] = []
    _save_memory()
    log_action(logger, "info", "chat_router", "SESSION_CREATED", f"user_id={user_id} | session_id={session_id}")
    return {"session": session}


@router.delete("/chat/sessions/{user_id}/{session_id}")
async def delete_session(user_id: str, session_id: str, current_user: dict = Depends(get_current_user)):
    """Delete a chat session."""
    if current_user.get("sub") != user_id:
        raise HTTPException(status_code=403, detail="Unauthorized")
    if user_id in user_sessions:
        user_sessions[user_id] = [s for s in user_sessions[user_id] if s["session_id"] != session_id]
    session_memory.pop(session_id, None)
    _save_memory()
    return {"success": True}


@router.get("/chat/sessions/{user_id}/{session_id}/messages")
async def get_session_messages(user_id: str, session_id: str, current_user: dict = Depends(get_current_user)):
    """Get all messages for a session."""
    if current_user.get("sub") != user_id:
        raise HTTPException(status_code=403, detail="Unauthorized")
    messages = session_memory.get(session_id, [])
    return {"messages": messages}


@router.websocket("/ws/chat/{user_id}")
async def websocket_chat(websocket: WebSocket, user_id: str):
    """WebSocket endpoint for real-time chat with the AI advisor."""
    await websocket.accept()
    active_connections[user_id] = websocket

    # The active session_id will be sent with each message from the client
    current_session_id = None

    log_action(logger, "info", "chat_router", "WEBSOCKET_CONNECT",
               f"user_id={user_id} | active_connections={len(active_connections)}")

    try:
        while True:
            data = await websocket.receive_text()
            message_data = json.loads(data)
            user_message = message_data.get("message", "")
            token = message_data.get("token", "")
            session_id = message_data.get("session_id", None)

            # Ensure session exists
            if session_id and session_id not in session_memory:
                session_memory[session_id] = []

            log_action(logger, "info", "chat_router", "WEBSOCKET_MESSAGE_IN",
                       f"user_id={user_id} | content_length={len(user_message)}")

            # Validate token
            user_verified = False
            if token:
                try:
                    payload = verify_token(token)
                    if payload.get("sub") == user_id:
                        user_verified = True
                except Exception:
                    pass

            # Typing indicator
            await websocket.send_text(json.dumps({
                "type": "typing",
                "content": "Analyzing your request..."
            }))

            try:
                # Get user profile
                profile = user_service.get_profile(user_id) if user_verified else {}

                # Route to the correct session memory
                mem_key = session_id if session_id else user_id
                if mem_key not in session_memory:
                    session_memory[mem_key] = []

                # Add user message to session memory
                session_memory[mem_key].append({
                    "role": "user",
                    "content": user_message
                })

                # Run orchestrator with correct session history
                response, result = await _run_orchestrator(
                    user_id, user_message,
                    profile or {},
                    session_memory[mem_key]
                )

                # Add assistant response to session memory
                session_memory[mem_key].append({
                    "role": "assistant",
                    "content": response
                })

                # Trim memory to last N turns
                if len(session_memory[mem_key]) > MAX_MEMORY_TURNS * 2:
                    session_memory[mem_key] = session_memory[mem_key][-(MAX_MEMORY_TURNS * 2):]

                # Update session metadata
                if session_id and user_id in user_sessions:
                    for s in user_sessions[user_id]:
                        if s["session_id"] == session_id:
                            s["last_message"] = user_message[:60] + ("..." if len(user_message) > 60 else "")
                            s["last_updated"] = datetime.now(timezone.utc).isoformat()
                            # Auto-title from first user message
                            if s["title"].startswith("Chat ") and len(session_memory[mem_key]) == 2:
                                s["title"] = user_message[:40] + ("..." if len(user_message) > 40 else "")
                            break

                log_action(logger, "info", "chat_router", "MEMORY_UPDATED",
                           f"user_id={user_id} | session_id={session_id} | total_messages={len(session_memory[mem_key])}")
                _save_memory()

                # Determine if this is a loan report that warrants a push notification
                intent = result.get("intent", "") if isinstance(result, dict) else ""
                loan_request = result.get("loan_request") or {} if isinstance(result, dict) else {}
                notification_type = "loan_report" if intent == "loan_inquiry" else None

                ws_payload = {
                    "type": "message",
                    "content": response,
                    "user_id": user_id,
                }
                if notification_type:
                    ws_payload["notification_type"] = notification_type
                    ws_payload["loan_type"] = loan_request.get("loan_type", "loan").replace("_", " ").title()
                    ws_payload["loan_amount"] = loan_request.get("requested_amount", 0)

                await websocket.send_text(json.dumps(ws_payload))

                log_action(logger, "info", "chat_router", "WEBSOCKET_MESSAGE_OUT",
                           f"user_id={user_id} | content_length={len(response)}")

            except Exception as e:
                error_msg = "I encountered an error processing your request. Please try again."
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "content": error_msg
                }))
                log_action(logger, "error", "chat_router", "ORCHESTRATOR_ERROR",
                           f"user_id={user_id} | error={str(e)}\n{traceback.format_exc()}")

    except WebSocketDisconnect:
        log_action(logger, "info", "chat_router", "WEBSOCKET_DISCONNECT",
                   f"user_id={user_id}")
    except Exception as e:
        log_action(logger, "error", "chat_router", "WEBSOCKET_ERROR",
                   f"user_id={user_id} | error={str(e)}")
    finally:
        active_connections.pop(user_id, None)


@router.delete("/chat/memory/{user_id}")
async def clear_memory(user_id: str):
    """Clear all conversation memory for a user (legacy fallback)."""
    session_memory.pop(user_id, None)
    _save_memory()
    log_action(logger, "info", "chat_router", "MEMORY_CLEARED", f"user_id={user_id}")
    return {"success": True, "message": "Conversation memory cleared"}


async def _run_orchestrator(user_id: str, message: str, profile: dict,
                            history: list) -> tuple:
    """Run the LangGraph orchestrator with full conversation context.
    Returns (response_str, result_dict) so callers can access intent/loan_request.
    """
    from langchain_core.messages import HumanMessage, AIMessage
    from orchestrator.graph import orchestrator_graph

    log_action(logger, "info", "chat_router", "ORCHESTRATOR_INVOKED",
               f"user_id={user_id} | message_length={len(message)} | "
               f"history_turns={len(history) // 2}")

    # Build LangChain message list from history (exclude the latest user message
    # since we'll add it as the final HumanMessage)
    lc_messages = []
    for msg in history[:-1]:  # Exclude last (just-added user message)
        if msg["role"] == "user":
            lc_messages.append(HumanMessage(content=msg["content"]))
        else:
            lc_messages.append(AIMessage(content=msg["content"]))

    # Add the current message
    lc_messages.append(HumanMessage(content=message))

    initial_state = {
        "user_id": user_id,
        "messages": lc_messages,
        "conversation_history": history,   # Raw history for context-aware classifier
        "user_profile": profile,
        "profile_complete": profile.get("profile_complete", False),
        "credit_profile": None,
        "loan_advisory": None,
        "compliance_result": None,
        "improvement_plan": None,
        "rag_results": None,
        "loan_request": None,
        "intent": "",
        "flow": "start",
        "agent_response": ""
    }

    import asyncio
    result = await asyncio.to_thread(orchestrator_graph.invoke, initial_state)

    response = result.get("agent_response",
                          "I'm sorry, I couldn't process your request. Please try again.")

    log_action(logger, "info", "chat_router", "ORCHESTRATOR_COMPLETE",
               f"user_id={user_id} | intent={result.get('intent', 'unknown')} | "
               f"flow={result.get('flow', 'unknown')} | response_length={len(response)}")

    return response, result
