from langchain_core.messages import HumanMessage



class ChatInterface:

    def __init__(self, rag_system):
        self.rag_system = rag_system

    def chat_with_citations(self, message, history):
        """Return (answer_text, structured_citations).

        Structured citations are collected from tool outputs and aggregated into
        the LangGraph state under `citations`.
        """
        if not self.rag_system.agent_graph:
            return "⚠️ System not initialized!", []

        try:
            result = self.rag_system.agent_graph.invoke(
                {"messages": [HumanMessage(content=message.strip())]},
                self.rag_system.get_config(),
            )
            answer = result["messages"][-1].content
            citations = result.get("citations") or []
            return answer, citations

        except Exception as e:
            return f"❌ Error: {str(e)}", []

    def chat(self, message, history):
        # Backward-compatible entrypoint for Gradio UI.
        answer, _ = self.chat_with_citations(message, history)
        return answer

    def clear_session(self):
        self.rag_system.reset_thread()
