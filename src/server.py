"""FastMCP server exposing document Q&A tools."""

import json
import logging

from mcp.server.fastmcp import FastMCP

from .config import settings
from .ingestion import DocumentIngester
from .retrieval import DocumentRetriever

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

mcp = FastMCP(
    "Nexla Doc MCP",
    instructions=(
        "An MCP server that answers natural-language questions about PDF documents "
        "using retrieval-augmented generation. It indexes PDFs from a local directory, "
        "stores embeddings in ChromaDB, and generates grounded answers with source citations."
    ),
)

ingester = DocumentIngester()
retriever = DocumentRetriever()


def _auto_ingest_if_empty():
    """Ingest all PDFs if the collection is empty."""
    if ingester.collection.count() == 0:
        logger.info("Collection empty — auto-ingesting PDFs from data/")
        ingester.ingest_all()


@mcp.tool()
def query_documents(question: str, top_k: int = 5) -> str:
    """Ask a natural-language question about indexed PDF documents.

    Returns a JSON object with `answer` (source-cited response),
    `sources` (list of doc name, page, relevance score), and `chunks_used` count.
    Auto-ingests PDFs on first query if the index is empty.
    """
    _auto_ingest_if_empty()

    chunks = retriever.search(question, top_k=top_k)
    result = retriever.generate_answer(question, chunks)
    return json.dumps(result, indent=2)


@mcp.tool()
def list_documents() -> str:
    """List all indexed PDF documents with metadata.

    Returns a JSON array of objects, each containing the document name,
    page count, chunk count, and file hash.
    """
    docs = ingester.list_indexed_documents()
    return json.dumps(docs, indent=2)


@mcp.tool()
def reingest_documents() -> str:
    """Force re-ingestion of all PDFs in the data directory.

    Clears the existing index and re-processes every PDF file.
    Returns a JSON object with status and per-document results.
    """
    logger.info("Force re-ingestion requested")
    results = ingester.ingest_all(force=True)

    # Reinitialize retriever's collection handle after re-ingestion
    retriever.collection = retriever.client.get_or_create_collection(
        name=settings.collection_name
    )

    ingested_count = sum(1 for r in results if r["status"] == "ingested")
    return json.dumps({
        "status": "complete",
        "documents_processed": len(results),
        "documents_ingested": ingested_count,
        "details": results,
    }, indent=2)


@mcp.tool()
def get_document_summary(document_name: str) -> str:
    """Get a summary and metadata preview of a specific indexed document.

    Provide the exact filename (e.g. "report.pdf"). Returns page count,
    chunk count, file hash, and a text preview of the first chunk.
    """
    result = retriever.get_document_summary(document_name)
    return json.dumps(result, indent=2)


def main():
    logger.info("Starting Nexla Doc MCP server...")
    _auto_ingest_if_empty()
    mcp.run()


if __name__ == "__main__":
    main()
