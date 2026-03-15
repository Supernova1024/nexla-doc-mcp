"""Semantic search and LLM-powered answer generation."""

import json
import logging

import chromadb

from .config import settings

logger = logging.getLogger(__name__)

GROUNDING_PROMPT = """You are a document analysis assistant. Answer the user's question using ONLY the provided context excerpts.

Rules:
1. Answer ONLY based on the provided context. Do not use prior knowledge.
2. Cite every claim with [Source: <document_name>, Page <page_number>].
3. If the context does not contain enough information to answer, say "I don't have enough information in the indexed documents to answer this question."
4. Be precise, factual, and concise.
5. If multiple documents are relevant, synthesize across them while maintaining citations.

Context:
{context}
"""


class DocumentRetriever:
    def __init__(self):
        self.client = chromadb.PersistentClient(path=str(settings.chroma_dir))
        self.collection = self.client.get_or_create_collection(
            name=settings.collection_name
        )

    def _refresh_collection(self):
        """Re-acquire the collection handle (needed after force re-ingestion)."""
        self.collection = self.client.get_or_create_collection(
            name=settings.collection_name
        )

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """Semantic search over indexed document chunks."""
        try:
            count = self.collection.count()
        except Exception:
            self._refresh_collection()
            count = self.collection.count()
        if count == 0:
            logger.warning("Collection is empty — no documents to search")
            return []

        safe_k = min(top_k, count)
        results = self.collection.query(query_texts=[query], n_results=safe_k)

        chunks = []
        for i in range(len(results["ids"][0])):
            chunks.append({
                "id": results["ids"][0][i],
                "text": results["documents"][0][i],
                "metadata": results["metadatas"][0][i],
                "distance": results["distances"][0][i] if results.get("distances") else None,
            })

        return chunks

    def _build_context(self, chunks: list[dict]) -> str:
        parts = []
        for i, chunk in enumerate(chunks, 1):
            meta = chunk["metadata"]
            parts.append(
                f"[Excerpt {i} | {meta['document']}, Page {meta['page']}]\n{chunk['text']}"
            )
        return "\n\n---\n\n".join(parts)

    def generate_answer(self, question: str, chunks: list[dict]) -> dict:
        """Generate a grounded answer from retrieved chunks using an LLM."""
        if not chunks:
            return {
                "answer": "No relevant document chunks were found for your question.",
                "sources": [],
                "chunks_used": 0,
            }

        context = self._build_context(chunks)
        system_message = GROUNDING_PROMPT.format(context=context)

        sources = [
            {
                "document": c["metadata"]["document"],
                "page": c["metadata"]["page"],
                "relevance_score": round(1 - c["distance"], 4) if c["distance"] is not None else None,
            }
            for c in chunks
        ]

        try:
            answer_text = self._call_llm(system_message, question)
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            answer_text = self._fallback_answer(chunks)

        return {
            "answer": answer_text,
            "sources": sources,
            "chunks_used": len(chunks),
        }

    def _call_llm(self, system_message: str, question: str) -> str:
        provider = settings.llm_provider.lower()

        if provider == "anthropic":
            return self._call_anthropic(system_message, question)
        elif provider == "openai":
            return self._call_openai(system_message, question)
        else:
            raise ValueError(f"Unsupported LLM provider: {provider}")

    def _call_anthropic(self, system_message: str, question: str) -> str:
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key or None)
        response = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=2048,
            temperature=settings.temperature,
            system=system_message,
            messages=[{"role": "user", "content": question}],
        )
        return response.content[0].text

    def _call_openai(self, system_message: str, question: str) -> str:
        from openai import OpenAI

        client = OpenAI(api_key=settings.openai_api_key or None)
        response = client.chat.completions.create(
            model=settings.openai_model,
            temperature=settings.temperature,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": question},
            ],
        )
        return response.choices[0].message.content

    def _fallback_answer(self, chunks: list[dict]) -> str:
        """Return raw retrieved chunks when LLM call fails."""
        parts = ["[LLM unavailable — returning raw retrieved excerpts]\n"]
        for i, chunk in enumerate(chunks, 1):
            meta = chunk["metadata"]
            parts.append(
                f"--- Excerpt {i} [{meta['document']}, Page {meta['page']}] ---\n{chunk['text']}"
            )
        return "\n\n".join(parts)

    def get_document_summary(self, document_name: str) -> dict:
        """Return metadata and a preview of the first chunk for a document."""
        try:
            count = self.collection.count()
        except Exception:
            self._refresh_collection()
            count = self.collection.count()
        if count == 0:
            return {"error": "No documents indexed"}

        results = self.collection.get(
            where={"document": document_name},
        )

        if not results["ids"]:
            return {"error": f"Document '{document_name}' not found in index"}

        pages = set()
        first_chunk_text = None
        first_chunk_idx = float("inf")

        for i, meta in enumerate(results["metadatas"]):
            pages.add(meta["page"])
            if meta["chunk_index"] < first_chunk_idx:
                first_chunk_idx = meta["chunk_index"]
                first_chunk_text = results["documents"][i]

        return {
            "document": document_name,
            "total_pages": len(pages),
            "total_chunks": len(results["ids"]),
            "file_hash": results["metadatas"][0]["file_hash"],
            "preview": first_chunk_text[:500] if first_chunk_text else "",
        }
