import importlib
import json
import os
import unittest


class TestOpenBBToolOutputPacked(unittest.TestCase):
    def test_tool_output_is_tool_output_v1_and_citations_parse(self):
        try:
            import langchain_core  # noqa: F401
        except Exception:
            self.skipTest("langchain_core not installed in this environment")

        os.environ["MAX_DATE_RANGE_DAYS"] = "3650"

        import config

        importlib.reload(config)

        from openbb import tools as openbb_tools

        importlib.reload(openbb_tools)

        def fake_get_json(self, endpoint, params, ttl_seconds, use_cache=True):
            return json.dumps({"ok": True, "endpoint": endpoint, "params": params}, ensure_ascii=False)

        openbb_tools.OpenBBClient.get_json = fake_get_json  # type: ignore

        out = openbb_tools.openbb_equity_price_quote.invoke({"symbol": "AAPL"})

        payload = json.loads(out)
        self.assertEqual(payload.get("format"), "tool_output.v1")
        self.assertIn("text", payload)
        self.assertIsInstance(payload.get("citations"), list)
        self.assertGreaterEqual(len(payload["citations"]), 1)

        cite0 = payload["citations"][0]
        self.assertEqual(cite0.get("source"), "openbb")
        self.assertEqual(cite0.get("endpoint"), "/api/v1/equity/price/quote")
        self.assertTrue(cite0.get("params_hash"))
        self.assertTrue(cite0.get("snippet"))
        self.assertTrue(cite0.get("created_at"))

        from common.citations import unpack_tool_output

        text, cites = unpack_tool_output(out)
        self.assertTrue(text)
        self.assertIsInstance(cites, list)
        self.assertEqual(cites[0].get("source"), "openbb")


if __name__ == "__main__":
    unittest.main()
