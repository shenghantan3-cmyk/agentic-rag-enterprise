from langgraph.graph import START, END, StateGraph
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.prebuilt import ToolNode
from functools import partial

from .graph_state import State
from .nodes import *
from .edges import *


def create_agent_graph(llm, tools_list):
    # Split tools: market graph must only see OpenBB tools.
    openbb_tools = [
        t for t in (tools_list or []) if str(getattr(t, "name", "")).startswith("openbb_")
    ]

    llm_with_tools = llm.bind_tools(tools_list)
    tool_node = ToolNode(tools_list)

    checkpointer = InMemorySaver()

    print("Compiling agent graph...")
    agent_builder = StateGraph(AgentState)
    agent_builder.add_node("orchestrator", partial(orchestrator, llm_with_tools=llm_with_tools))
    agent_builder.add_node("tools", tool_node)
    agent_builder.add_node("compress_context", partial(compress_context, llm=llm))
    agent_builder.add_node("fallback_response", partial(fallback_response, llm=llm))
    agent_builder.add_node(should_compress_context) 
    agent_builder.add_node(collect_answer)
    
    agent_builder.add_edge(START, "orchestrator")    
    agent_builder.add_conditional_edges("orchestrator", route_after_orchestrator_call, {"tools": "tools", "fallback_response": "fallback_response", "collect_answer": "collect_answer"})
    agent_builder.add_edge("tools", "should_compress_context")
    agent_builder.add_edge("compress_context", "orchestrator")
    agent_builder.add_edge("fallback_response", "collect_answer")
    agent_builder.add_edge("collect_answer", END)
    
    agent_subgraph = agent_builder.compile()

    # --- Market-only subgraph (OpenBB tools only) ---
    market_llm_with_tools = llm.bind_tools(openbb_tools)
    market_tool_node = ToolNode(openbb_tools)

    market_builder = StateGraph(AgentState)
    market_builder.add_node("orchestrator", partial(market_orchestrator, llm_with_tools=market_llm_with_tools))
    market_builder.add_node("tools", market_tool_node)
    market_builder.add_node("compress_context", partial(compress_context, llm=llm))
    market_builder.add_node("fallback_response", partial(fallback_response, llm=llm))
    market_builder.add_node(should_compress_context)
    market_builder.add_node(collect_answer)

    market_builder.add_edge(START, "orchestrator")
    market_builder.add_conditional_edges(
        "orchestrator",
        route_after_orchestrator_call,
        {"tools": "tools", "fallback_response": "fallback_response", "collect_answer": "collect_answer"},
    )
    market_builder.add_edge("tools", "should_compress_context")
    market_builder.add_edge("compress_context", "orchestrator")
    market_builder.add_edge("fallback_response", "collect_answer")
    market_builder.add_edge("collect_answer", END)

    market_subgraph = market_builder.compile()

    # --- Fusion subgraph (doc + market, then fuse) ---
    fusion_builder = StateGraph(AgentState)
    fusion_builder.add_node(
        "fusion_run",
        partial(fusion_run, llm=llm, doc_subgraph=agent_subgraph, market_subgraph=market_subgraph),
    )
    fusion_builder.add_edge(START, "fusion_run")
    fusion_builder.add_edge("fusion_run", END)
    fusion_subgraph = fusion_builder.compile()

    graph_builder = StateGraph(State)
    graph_builder.add_node("summarize_history", partial(summarize_history, llm=llm))
    graph_builder.add_node("rewrite_query", partial(rewrite_query, llm=llm))
    graph_builder.add_node("route_intent", partial(route_intent, llm=llm))
    graph_builder.add_node(request_clarification)
    # --- General subgraph (no tools) ---
    general_builder = StateGraph(AgentState)
    general_builder.add_node("general_answer", partial(general_answer, llm=llm))
    general_builder.add_edge(START, "general_answer")
    general_builder.add_edge("general_answer", END)
    general_subgraph = general_builder.compile()

    graph_builder.add_node("agent", agent_subgraph)
    graph_builder.add_node("market_agent", market_subgraph)
    graph_builder.add_node("fusion_agent", fusion_subgraph)
    graph_builder.add_node("general_agent", general_subgraph)
    graph_builder.add_node("aggregate_answers", partial(aggregate_answers, llm=llm))

    graph_builder.add_edge(START, "summarize_history")
    graph_builder.add_edge("summarize_history", "rewrite_query")
    graph_builder.add_conditional_edges("rewrite_query", route_after_rewrite)
    graph_builder.add_edge("request_clarification", "rewrite_query")

    # After intent routing, fan out per-question to the correct subgraph.
    graph_builder.add_conditional_edges("route_intent", route_after_intent)

    graph_builder.add_edge(["agent", "market_agent", "fusion_agent", "general_agent"], "aggregate_answers")
    graph_builder.add_edge("aggregate_answers", END)

    agent_graph = graph_builder.compile(checkpointer=checkpointer, interrupt_before=["request_clarification"])

    print("✓ Agent graph compiled successfully.")
    return agent_graph