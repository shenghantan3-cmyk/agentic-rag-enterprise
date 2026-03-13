import unittest


class TestCitationsHelpers(unittest.TestCase):
    def test_pack_unpack_roundtrip(self):
        from common.citations import pack_tool_output, unpack_tool_output

        text = "hello"
        cites = [{"chunk_id": "c1", "parent_id": "p1", "source": "a.pdf", "snippet": "hi", "score": 0.1}]
        out = pack_tool_output(text, cites)
        t2, c2 = unpack_tool_output(out)
        self.assertEqual(t2, text)
        self.assertEqual(c2, cites)

    def test_unpack_without_marker(self):
        from common.citations import unpack_tool_output

        t2, c2 = unpack_tool_output("plain")
        self.assertEqual(t2, "plain")
        self.assertEqual(c2, [])

    def test_merge_dedupes(self):
        from common.citations import merge_citations

        a = [{"chunk_id": "c1", "source": "a.pdf"}]
        b = [{"chunk_id": "c1", "source": "a.pdf"}, {"chunk_id": "c2", "source": "b.pdf"}]
        out = merge_citations(a, b)
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0]["chunk_id"], "c1")
        self.assertEqual(out[1]["chunk_id"], "c2")


if __name__ == "__main__":
    unittest.main()
