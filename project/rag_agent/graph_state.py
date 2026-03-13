from typing import List, Annotated, Set, Dict
import operator

# Optional dependency: some test environments may not include langgraph.
try:
    from langgraph.graph import MessagesState  # type: ignore
except Exception:  # pragma: no cover
    class MessagesState(dict):  # type: ignore
        pass

from common.citations import merge_citations

def accumulate_or_reset(existing: List[dict], new: List[dict]) -> List[dict]:
    if new and any(item.get('__reset__') for item in new):
        return []
    return existing + new

def set_union(a: Set[str], b: Set[str]) -> Set[str]:
    return a | b

class State(MessagesState):
    """State for main agent graph"""

    questionIsClear: bool = False
    conversation_summary: str = ""
    originalQuery: str = ""
    rewrittenQuestions: List[str] = []

    # One route per rewritten question.
    intent_routes: List[dict] = []

    # Each agent subgraph returns an answer dict. We reset between rewrites.
    agent_answers: Annotated[List[dict], accumulate_or_reset] = []

    # Structured citations aggregated from tool outputs.
    citations: Annotated[List[Dict], merge_citations] = []


class AgentState(MessagesState):
    """State for individual agent subgraph"""

    question: str = ""
    question_index: int = 0
    context_summary: str = ""
    retrieval_keys: Annotated[Set[str], set_union] = set()

    final_answer: str = ""
    agent_answers: List[dict] = []

    # Structured citations collected from retrieval tool outputs.
    citations: Annotated[List[Dict], merge_citations] = []

    tool_call_count: Annotated[int, operator.add] = 0
    iteration_count: Annotated[int, operator.add] = 0