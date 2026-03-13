from typing import List

from langchain_core.tools import tool
from db.parent_store_manager import ParentStoreManager

from common.citations import make_chunk_id, now_iso, pack_tool_output
from openbb.tools import create_openbb_tools

class ToolFactory:
    
    def __init__(self, collection):
        self.collection = collection
        self.parent_store_manager = ParentStoreManager()
    
    def _search_child_chunks(self, query: str, limit: int) -> str:
        """Search for the top K most relevant child chunks.

        Backward compatible: returns the same human readable text as before,
        but appends a machine-readable citation payload.
        """
        try:
            # Prefer retrieval with scores if available.
            results_with_score = None
            fn = getattr(self.collection, "similarity_search_with_score", None)
            if callable(fn):
                try:
                    results_with_score = fn(query, k=limit)
                except Exception:
                    results_with_score = None

            docs = []
            if results_with_score:
                for doc, score in results_with_score:
                    docs.append((doc, score))
            else:
                results = self.collection.similarity_search(query, k=limit, score_threshold=0.7)
                docs = [(doc, None) for doc in (results or [])]

            if not docs:
                return "NO_RELEVANT_CHUNKS"

            citations = []
            blocks = []
            for doc, score in docs:
                meta = getattr(doc, "metadata", {}) or {}
                parent_id = str(meta.get("parent_id") or "")
                source = str(meta.get("source") or "")
                content = (getattr(doc, "page_content", "") or "").strip()
                snippet = content[:280]
                chunk_id = str(meta.get("chunk_id") or meta.get("id") or "")
                if not chunk_id:
                    chunk_id = make_chunk_id(source, parent_id, snippet)

                citations.append(
                    {
                        "doc_id": source or None,
                        "doc_name": source or None,
                        "source": source or None,
                        "chunk_id": chunk_id,
                        "parent_id": parent_id or None,
                        "snippet": snippet or None,
                        "score": float(score) if score is not None else None,
                        "span_start": None,
                        "span_end": None,
                        "retriever": "vector",
                        "created_at": now_iso(),
                    }
                )

                blocks.append(
                    f"Parent ID: {parent_id}\n"
                    f"File Name: {source}\n"
                    f"Content: {content}"
                )

            text = "\n\n".join(blocks)
            return pack_tool_output(text, citations)

        except Exception as e:
            return f"RETRIEVAL_ERROR: {str(e)}"    
    def _retrieve_many_parent_chunks(self, parent_ids: List[str]) -> str:
        """Retrieve full parent chunks by their IDs.

        Backward compatible: returns human readable text with appended citations payload.
        """
        try:
            ids = [parent_ids] if isinstance(parent_ids, str) else list(parent_ids)
            raw_parents = self.parent_store_manager.load_content_many(ids)
            if not raw_parents:
                return "NO_PARENT_DOCUMENTS"

            citations = []
            blocks = []
            for doc in raw_parents:
                pid = str(doc.get("parent_id", "n/a"))
                source = str(doc.get("metadata", {}).get("source", "unknown"))
                content = str(doc.get("content", "")).strip()
                snippet = content[:280]
                chunk_id = make_chunk_id(source, pid, snippet)

                citations.append(
                    {
                        "doc_id": (source if source != "unknown" else None),
                        "doc_name": (source if source != "unknown" else None),
                        "source": source if source != "unknown" else None,
                        "chunk_id": chunk_id,
                        "parent_id": pid if pid != "n/a" else None,
                        "snippet": snippet or None,
                        "score": None,
                        "span_start": None,
                        "span_end": None,
                        "retriever": "parent_store",
                        "created_at": now_iso(),
                    }
                )

                blocks.append(
                    f"Parent ID: {pid}\n"
                    f"File Name: {source}\n"
                    f"Content: {content}"
                )

            text = "\n\n".join(blocks)
            return pack_tool_output(text, citations)

        except Exception as e:
            return f"PARENT_RETRIEVAL_ERROR: {str(e)}"

    def _retrieve_parent_chunks(self, parent_id: str) -> str:
        """Retrieve full parent chunk by its ID.

        Backward compatible: returns human readable text with appended citations payload.
        """
        try:
            parent = self.parent_store_manager.load_content(parent_id)
            if not parent:
                return "NO_PARENT_DOCUMENT"

            pid = str(parent.get("parent_id", "n/a"))
            source = str(parent.get("metadata", {}).get("source", "unknown"))
            content = str(parent.get("content", "")).strip()
            snippet = content[:280]
            chunk_id = make_chunk_id(source, pid, snippet)

            citations = [
                {
                    "doc_id": (source if source != "unknown" else None),
                    "doc_name": (source if source != "unknown" else None),
                    "source": source if source != "unknown" else None,
                    "chunk_id": chunk_id,
                    "parent_id": pid if pid != "n/a" else None,
                    "snippet": snippet or None,
                    "score": None,
                    "span_start": None,
                    "span_end": None,
                    "retriever": "parent_store",
                    "created_at": now_iso(),
                }
            ]

            text = (
                f"Parent ID: {pid}\n"
                f"File Name: {source}\n"
                f"Content: {content}"
            )

            return pack_tool_output(text, citations)

        except Exception as e:
            return f"PARENT_RETRIEVAL_ERROR: {str(e)}"
    
    def create_tools(self) -> List:
        """Create and return the list of tools."""
        search_tool = tool("search_child_chunks")(self._search_child_chunks)
        retrieve_tool = tool("retrieve_parent_chunks")(self._retrieve_parent_chunks)

        # Optional OpenBB tools (local OpenBB server)
        openbb_tools = create_openbb_tools()

        return [search_tool, retrieve_tool] + openbb_tools