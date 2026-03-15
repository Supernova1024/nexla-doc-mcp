"""PDF parsing, chunking, and ChromaDB storage pipeline."""

import hashlib
import logging
from pathlib import Path

import chromadb
import pdfplumber

from .config import settings

logger = logging.getLogger(__name__)

SENTENCE_BOUNDARIES = [". ", "\n\n", "\n"]


class DocumentIngester:
    def __init__(self):
        self.client = chromadb.PersistentClient(path=str(settings.chroma_dir))
        self.collection = self.client.get_or_create_collection(
            name=settings.collection_name
        )

    def _compute_file_hash(self, filepath: Path) -> str:
        hasher = hashlib.md5()
        with open(filepath, "rb") as f:
            for buf in iter(lambda: f.read(65536), b""):
                hasher.update(buf)
        return hasher.hexdigest()

    def _extract_text_from_pdf(self, filepath: Path) -> list[dict]:
        """Extract text page-by-page from a PDF file."""
        pages = []
        with pdfplumber.open(filepath) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                text = page.extract_text() or ""
                if text.strip():
                    pages.append({"page": page_num, "text": text})
        return pages

    def _chunk_text(self, text: str) -> list[str]:
        """Split text into overlapping chunks with sentence-boundary awareness."""
        if len(text) <= settings.chunk_size:
            return [text]

        chunks = []
        start = 0
        while start < len(text):
            end = start + settings.chunk_size

            if end < len(text):
                best_break = -1
                for boundary in SENTENCE_BOUNDARIES:
                    search_start = start + settings.chunk_size // 2
                    pos = text.rfind(boundary, search_start, end)
                    if pos != -1:
                        best_break = pos + len(boundary)
                        break

                if best_break > start:
                    end = best_break

            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)

            start = end - settings.chunk_overlap
            if start >= len(text):
                break

        return chunks

    def _is_already_ingested(self, file_hash: str) -> bool:
        """Check if a document with this hash is already in the collection."""
        if self.collection.count() == 0:
            return False

        results = self.collection.get(where={"file_hash": file_hash}, limit=1)
        return len(results["ids"]) > 0

    def ingest_file(self, filepath: Path, force: bool = False) -> dict:
        """Ingest a single PDF file into ChromaDB."""
        filename = filepath.name
        file_hash = self._compute_file_hash(filepath)

        if not force and self._is_already_ingested(file_hash):
            logger.info(f"Skipping {filename} — already ingested (hash: {file_hash[:8]})")
            return {"document": filename, "status": "skipped", "reason": "already_ingested"}

        if force:
            self._remove_document(filename)

        logger.info(f"Ingesting {filename}...")
        pages = self._extract_text_from_pdf(filepath)
        if not pages:
            logger.warning(f"No extractable text in {filename}")
            return {"document": filename, "status": "skipped", "reason": "no_text"}

        all_ids = []
        all_documents = []
        all_metadatas = []
        chunk_index = 0

        for page_info in pages:
            chunks = self._chunk_text(page_info["text"])
            for chunk_text in chunks:
                doc_id = f"{filename}::page{page_info['page']}::chunk{chunk_index}"
                all_ids.append(doc_id)
                all_documents.append(chunk_text)
                all_metadatas.append({
                    "document": filename,
                    "page": page_info["page"],
                    "chunk_index": chunk_index,
                    "file_hash": file_hash,
                })
                chunk_index += 1

        batch_size = 100
        for i in range(0, len(all_ids), batch_size):
            self.collection.upsert(
                ids=all_ids[i : i + batch_size],
                documents=all_documents[i : i + batch_size],
                metadatas=all_metadatas[i : i + batch_size],
            )

        logger.info(f"Ingested {filename}: {len(pages)} pages, {chunk_index} chunks")
        return {
            "document": filename,
            "status": "ingested",
            "pages": len(pages),
            "chunks": chunk_index,
        }

    def _remove_document(self, filename: str):
        """Remove all chunks for a document from the collection."""
        if self.collection.count() == 0:
            return
        existing = self.collection.get(where={"document": filename})
        if existing["ids"]:
            self.collection.delete(ids=existing["ids"])
            logger.info(f"Removed {len(existing['ids'])} existing chunks for {filename}")

    def ingest_all(self, force: bool = False) -> list[dict]:
        """Ingest all PDFs in the data directory."""
        pdf_files = sorted(settings.data_dir.glob("*.pdf"))
        if not pdf_files:
            logger.warning(f"No PDF files found in {settings.data_dir}")
            return []

        if force:
            logger.info("Force re-ingestion: clearing existing collection")
            self.client.delete_collection(settings.collection_name)
            self.collection = self.client.get_or_create_collection(
                name=settings.collection_name
            )

        results = []
        for pdf_path in pdf_files:
            result = self.ingest_file(pdf_path, force=False)
            results.append(result)

        return results

    def list_indexed_documents(self) -> list[dict]:
        """Return a list of indexed documents with page and chunk counts."""
        if self.collection.count() == 0:
            return []

        all_metadata = self.collection.get()["metadatas"]
        doc_stats: dict[str, dict] = {}

        for meta in all_metadata:
            doc_name = meta["document"]
            if doc_name not in doc_stats:
                doc_stats[doc_name] = {"document": doc_name, "pages": set(), "chunks": 0, "file_hash": meta["file_hash"]}
            doc_stats[doc_name]["pages"].add(meta["page"])
            doc_stats[doc_name]["chunks"] += 1

        return [
            {
                "document": info["document"],
                "pages": len(info["pages"]),
                "chunks": info["chunks"],
                "file_hash": info["file_hash"],
            }
            for info in doc_stats.values()
        ]
