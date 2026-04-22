"""
RAG Pipeline: Document ingestion, chunking, embedding, and FAISS index building.
"""
import os
import sys
import json
import numpy as np
import faiss
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings
from logger import get_logger, log_action

logger = get_logger("rag_pipeline")


class RAGPipeline:
    """Handles document ingestion, chunking, embedding, and FAISS index creation."""

    def __init__(self):
        self.index = None
        self.chunks = []  # List of {text, source, chunk_id}
        self.embedding_model = None
        self.dimension = 384  # all-MiniLM-L6-v2 dimension
        self._load_embedding_model()
        self._try_load_index()

    def _load_embedding_model(self):
        """Load the sentence-transformers model for embedding."""
        try:
            from sentence_transformers import SentenceTransformer
            self.embedding_model = SentenceTransformer(settings.EMBEDDING_MODEL)
            log_action(logger, "info", "rag_pipeline", "EMBEDDING_MODEL_LOADED",
                       f"model={settings.EMBEDDING_MODEL}")
        except Exception as e:
            log_action(logger, "error", "rag_pipeline", "EMBEDDING_MODEL_LOAD_FAILED",
                       f"error={str(e)}")

    def _try_load_index(self):
        """Try to load a previously saved FAISS index."""
        index_path = os.path.join(settings.FAISS_PATH, "index.faiss")
        chunks_path = os.path.join(settings.FAISS_PATH, "chunks.json")

        if os.path.exists(index_path) and os.path.exists(chunks_path):
            try:
                self.index = faiss.read_index(index_path)
                with open(chunks_path, 'r', encoding='utf-8') as f:
                    self.chunks = json.load(f)
                log_action(logger, "info", "rag_pipeline", "INDEX_LOADED",
                           f"source=disk | chunks={len(self.chunks)} | index_size={self.index.ntotal}")
            except Exception as e:
                log_action(logger, "warning", "rag_pipeline", "INDEX_LOAD_FAILED",
                           f"error={str(e)}")

    def ingest_documents(self, force_reingest=False):
        """Load, chunk, embed, and index all policy documents."""
        if self.index and self.index.ntotal > 0 and not force_reingest:
            log_action(logger, "info", "rag_pipeline", "INGESTION_SKIPPED",
                       f"existing_chunks={len(self.chunks)}")
            return

        docs_dir = settings.RAG_DOCS_DIR
        if not os.path.exists(docs_dir):
            log_action(logger, "error", "rag_pipeline", "DOCUMENTS_DIR_NOT_FOUND",
                       f"path={docs_dir}")
            return

        txt_files = [f for f in os.listdir(docs_dir) if f.endswith('.txt')]
        log_action(logger, "info", "rag_pipeline", "RAG_INGESTION_STARTED",
                   f"document_count={len(txt_files)} | source_dir={docs_dir}")

        all_chunks = []
        for filename in txt_files:
            filepath = os.path.join(docs_dir, filename)
            with open(filepath, 'r', encoding='utf-8') as f:
                text = f.read()

            chunks = self._chunk_text(text, filename)
            all_chunks.extend(chunks)
            log_action(logger, "debug", "rag_pipeline", "DOCUMENT_CHUNKED",
                       f"file={filename} | chunks={len(chunks)} | total_chars={len(text)}")

        if not all_chunks:
            log_action(logger, "warning", "rag_pipeline", "NO_CHUNKS_CREATED", "")
            return

        self.chunks = all_chunks

        # Embed all chunks
        texts = [c["text"] for c in all_chunks]
        log_action(logger, "info", "rag_pipeline", "EMBEDDING_STARTED",
                   f"total_chunks={len(texts)}")

        embeddings = self.embedding_model.encode(texts, show_progress_bar=False, batch_size=32)
        embeddings = np.array(embeddings, dtype='float32')

        # Build FAISS index
        self.dimension = embeddings.shape[1]
        self.index = faiss.IndexFlatL2(self.dimension)
        self.index.add(embeddings)

        # Save to disk
        self._save_index()

        log_action(logger, "info", "rag_pipeline", "RAG_INGESTION_COMPLETE",
                   f"total_chunks={len(all_chunks)} | index_size={self.index.ntotal} | "
                   f"dimension={self.dimension} | index_path={settings.FAISS_PATH}")

    def _chunk_text(self, text: str, source: str) -> list:
        """Split text into overlapping chunks."""
        # Split by paragraphs first, then merge into chunks of target size
        paragraphs = text.split('\n\n')
        chunks = []
        current_chunk = ""
        chunk_id = 0

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            if len(current_chunk) + len(para) < settings.CHUNK_SIZE * 4:  # ~4 chars per token
                current_chunk += "\n\n" + para if current_chunk else para
            else:
                if current_chunk:
                    chunks.append({
                        "text": current_chunk.strip(),
                        "source": source,
                        "chunk_id": f"{source}_{chunk_id}"
                    })
                    chunk_id += 1
                    # Keep overlap
                    overlap_text = current_chunk[-settings.CHUNK_OVERLAP * 4:]
                    current_chunk = overlap_text + "\n\n" + para
                else:
                    current_chunk = para

        # Add remaining chunk
        if current_chunk.strip():
            chunks.append({
                "text": current_chunk.strip(),
                "source": source,
                "chunk_id": f"{source}_{chunk_id}"
            })

        return chunks

    def _save_index(self):
        """Save FAISS index and chunks to disk."""
        os.makedirs(settings.FAISS_PATH, exist_ok=True)
        index_path = os.path.join(settings.FAISS_PATH, "index.faiss")
        chunks_path = os.path.join(settings.FAISS_PATH, "chunks.json")

        faiss.write_index(self.index, index_path)
        with open(chunks_path, 'w', encoding='utf-8') as f:
            json.dump(self.chunks, f, ensure_ascii=False, indent=2)

        log_action(logger, "info", "rag_pipeline", "INDEX_SAVED",
                   f"index_path={index_path} | chunks_path={chunks_path}")

    def search(self, query: str, top_k: int = None) -> list:
        """Search FAISS index for relevant chunks."""
        if top_k is None:
            top_k = settings.RAG_TOP_K

        if self.index is None or self.index.ntotal == 0:
            log_action(logger, "warning", "rag_pipeline", "SEARCH_NO_INDEX",
                       "No FAISS index available. Run ingest_documents() first.")
            return []

        # Embed the query
        query_embedding = self.embedding_model.encode([query]).astype('float32')

        # Search
        distances, indices = self.index.search(query_embedding, min(top_k, self.index.ntotal))

        results = []
        for i, (dist, idx) in enumerate(zip(distances[0], indices[0])):
            if idx < len(self.chunks):
                chunk = self.chunks[idx]
                results.append({
                    "text": chunk["text"],
                    "source": chunk["source"],
                    "chunk_id": chunk["chunk_id"],
                    "score": float(1 / (1 + dist)),  # Convert distance to similarity
                    "rank": i + 1
                })

        top_score = results[0]["score"] if results else 0
        log_action(logger, "info", "rag_pipeline", "RAG_SEARCH",
                   f"query={query[:80]}... | results_count={len(results)} | top_score={top_score:.4f}")

        return results


# Singleton
rag_pipeline = RAGPipeline()
