from typing import Literal

from langchain_core.messages import ToolMessage
from langgraph.types import Send

from .graph_state import State, AgentState
from config import MAX_ITERATIONS, MAX_OPENBB_CALLS, MAX_TOOL_CALLS
from openbb.storage import record_budget_event

def route_after_rewrite(state: State) -> Literal["request_clarification", "agent"]:
    if not state.get("questionIsClear", False):
        return "request_clarification"
    else:
        return [
                Send("agent", {"question": query, "question_index": idx, "messages": []})
                for idx, query in enumerate(state["rewrittenQuestions"])
            ]
    
def _count_openbb_tool_messages(state: AgentState) -> int:
    count = 0
    for m in state.get("messages") or []:
        if isinstance(m, ToolMessage) and str(getattr(m, "name", "")).startswith("openbb_"):
            count += 1
    return count


def route_after_orchestrator_call(state: AgentState) -> Literal["tools", "fallback_response", "collect_answer"]:
    iteration = int(state.get("iteration_count", 0) or 0)
    tool_count = int(state.get("tool_call_count", 0) or 0)

    # Stop conditions (global budgets)
    if iteration >= MAX_ITERATIONS:
        record_budget_event("max_iterations", iteration=iteration, max_iterations=MAX_ITERATIONS)
        return "fallback_response"

    if tool_count >= MAX_TOOL_CALLS:
        record_budget_event("max_tool_calls", tool_count=tool_count, max_tool_calls=MAX_TOOL_CALLS)
        return "fallback_response"

    last_message = state["messages"][-1]
    tool_calls = getattr(last_message, "tool_calls", None) or []

    if not tool_calls:
        return "collect_answer"

    # OpenBB call budget: block OpenBB tools once the budget is reached.
    openbb_used = _count_openbb_tool_messages(state)
    openbb_requested = sum(1 for tc in tool_calls if str(tc.get("name", "")).startswith("openbb_"))

    if MAX_OPENBB_CALLS >= 0 and openbb_requested > 0:
        if openbb_used >= MAX_OPENBB_CALLS or (openbb_used + openbb_requested) > MAX_OPENBB_CALLS:
            record_budget_event(
                "max_openbb_calls",
                openbb_used=openbb_used,
                openbb_requested=openbb_requested,
                max_openbb_calls=MAX_OPENBB_CALLS,
            )
            return "fallback_response"

    return "tools"