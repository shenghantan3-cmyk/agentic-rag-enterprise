import importlib
import os
import sys
import unittest
from pathlib import Path

# Ensure project/ is importable as top-level modules (config, openbb, rag_agent, ...)
_PROJECT_DIR = Path(__file__).resolve().parents[1] / "project"
if str(_PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(_PROJECT_DIR))


class TestConfigEnvKnobs(unittest.TestCase):
    def test_env_int_defaults_and_override(self):
        # Ensure env overrides are picked up on import/reload.
        os.environ["MAX_TOOL_CALLS"] = "12"
        os.environ["MAX_OPENBB_CALLS"] = "3"
        os.environ["MAX_DATE_RANGE_DAYS"] = "90"
        os.environ["MAX_NEWS_LIMIT"] = "7"

        import config

        importlib.reload(config)
        self.assertEqual(config.MAX_TOOL_CALLS, 12)
        self.assertEqual(config.MAX_OPENBB_CALLS, 3)
        self.assertEqual(config.MAX_DATE_RANGE_DAYS, 90)
        self.assertEqual(config.MAX_NEWS_LIMIT, 7)


class TestOpenBBToolClamps(unittest.TestCase):
    def test_news_limit_clamped_by_knob_and_hard_cap(self):
        try:
            import langchain_core  # noqa: F401
        except Exception:
            self.skipTest("langchain_core not installed in this environment")

        # Set knob low; tool should clamp to it.
        os.environ["MAX_NEWS_LIMIT"] = "3"
        import config

        importlib.reload(config)

        # Reload openbb.tools so it re-reads config module globals.
        from openbb import tools as openbb_tools

        importlib.reload(openbb_tools)

        # Patch client to avoid network and capture params
        captured = {}

        def fake_get_json(self, endpoint, params, ttl_seconds, use_cache=True):
            captured["endpoint"] = endpoint
            captured["params"] = params
            return "{}"

        openbb_tools.OpenBBClient.get_json = fake_get_json  # type: ignore

        # openbb_news_company is a LangChain StructuredTool; call via .invoke
        openbb_tools.openbb_news_company.invoke({"symbol": "AAPL", "limit": 999})
        self.assertEqual(captured["params"]["limit"], 3)


class TestGraphBudgets(unittest.TestCase):
    def test_route_blocks_openbb_when_budget_exhausted(self):
        try:
            import langchain_core  # noqa: F401
        except Exception:
            self.skipTest("langchain_core not installed in this environment")

        os.environ["MAX_OPENBB_CALLS"] = "1"
        os.environ["MAX_TOOL_CALLS"] = "99"
        import config

        importlib.reload(config)

        from rag_agent import edges

        importlib.reload(edges)

        from langchain_core.messages import AIMessage, ToolMessage

        # One OpenBB call already executed.
        msgs = [ToolMessage(content="{}", name="openbb_equity_price_quote", tool_call_id="t1")]
        # Orchestrator now requests another OpenBB call.
        ai = AIMessage(content="", tool_calls=[{"id": "call_1", "name": "openbb_news_company", "args": {"symbol": "AAPL"}}])
        msgs.append(ai)

        state = {
            "messages": msgs,
            "iteration_count": 0,
            "tool_call_count": 0,
        }
        self.assertEqual(edges.route_after_orchestrator_call(state), "fallback_response")


class TestIntentRoutingEdge(unittest.TestCase):
    def test_route_after_intent_fans_out(self):
        from rag_agent import edges

        routes = [
            {"intent": "document", "rationale": "docs"},
            {"intent": "market", "rationale": "quote"},
            {"intent": "fusion", "rationale": "both"},
            {"intent": "general", "rationale": "non-finance"},
        ]
        state = {
            "rewrittenQuestions": ["q1", "q2", "q3", "q4"],
            "intent_routes": routes,
        }

        sends = edges.route_after_intent(state)
        self.assertEqual(len(sends), 4)

        nodes = [getattr(s, "node", None) for s in sends]
        if nodes[0] is None:
            # Fallback Send dataclass uses .node, but if LangGraph Send differs,
            # allow a .name attribute.
            nodes = [getattr(s, "name", None) for s in sends]

        self.assertEqual(nodes[0], "agent")
        self.assertEqual(nodes[1], "market_agent")
        self.assertEqual(nodes[2], "fusion_agent")
        self.assertEqual(nodes[3], "general_agent")


if __name__ == "__main__":
    unittest.main()
