"""Chunking, embedding, and retrieval helpers for RAG-backed viva questions."""

from __future__ import annotations

import json
import logging
import re
import uuid
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 384
_SENTENCE_TRANSFORMER_MODEL = None


def _get_transformer_model():
    """Lazily load the sentence transformer model only from local cache."""
    global _SENTENCE_TRANSFORMER_MODEL
    if _SENTENCE_TRANSFORMER_MODEL is None:
        try:
            from sentence_transformers import SentenceTransformer

            _SENTENCE_TRANSFORMER_MODEL = SentenceTransformer(
                "all-MiniLM-L6-v2",
                local_files_only=True,
            )
        except Exception as exc:
            logger.info(
                "SentenceTransformer local model unavailable (%s); using deterministic fallback.",
                exc,
            )
            _SENTENCE_TRANSFORMER_MODEL = False
    return _SENTENCE_TRANSFORMER_MODEL if _SENTENCE_TRANSFORMER_MODEL is not False else None


def _tokenize(text: str) -> list[str]:
    """Tokenize text into lowercase word tokens."""
    return re.findall(r"\b[\w'-]+\b", text.lower())


def chunk_text(text: str, chunk_size: int = 512, overlap: int = 64) -> list[str]:
    """Split a document into overlapping chunks using a recursive text splitter strategy.

    Splits progressively along paragraph boundaries, sentence boundaries, and word tokens.
    """
    if not text or not text.strip():
        return []

    stripped = text.strip()
    words = stripped.split()
    if len(words) <= chunk_size:
        return [stripped]

    # Split by paragraphs first
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", stripped) if p.strip()]
    if not paragraphs:
        paragraphs = [stripped]

    units: list[str] = []
    for para in paragraphs:
        para_words = para.split()
        if len(para_words) <= chunk_size:
            units.append(para)
        else:
            # Split paragraph by sentences
            sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", para) if s.strip()]
            for sentence in sentences:
                sent_words = sentence.split()
                if len(sent_words) <= chunk_size:
                    units.append(sentence)
                else:
                    # Split long sentences by word tokens
                    for i in range(0, len(sent_words), max(1, chunk_size - overlap)):
                        chunk_words = sent_words[i : i + chunk_size]
                        if chunk_words:
                            units.append(" ".join(chunk_words))

    # Recombine units into chunks up to chunk_size with overlap
    chunks: list[str] = []
    step = max(1, chunk_size - overlap)

    # Flatten all units into word tokens with preserved punctuation
    all_words = " ".join(units).split()
    if not all_words:
        return []

    for start in range(0, len(all_words), step):
        chunk_words = all_words[start : start + chunk_size]
        if chunk_words:
            chunks.append(" ".join(chunk_words))
        if start + chunk_size >= len(all_words):
            break

    return chunks


def _deterministic_vector(text: str, dimension: int = EMBEDDING_DIM) -> np.ndarray:
    """Fallback deterministic vector generator when neural models are offline."""
    tokens = _tokenize(text)
    if not tokens:
        return np.zeros(dimension, dtype="float32")

    vector = np.zeros(dimension, dtype="float32")
    for token in tokens:
        # Distribute token character values across dimensions
        h1 = sum(ord(ch) * (31**i) for i, ch in enumerate(token[:8])) % dimension
        h2 = sum(ord(ch) for ch in token) % dimension
        vector[h1] += 1.0
        vector[h2] += 0.5

    norm = np.linalg.norm(vector)
    if norm > 0:
        vector = vector / norm
    return vector.astype("float32")


def embed_chunks(chunks: list[str]) -> np.ndarray:
    """Generate dense embeddings for a list of text chunks.

    Returns an (N, 384) float32 numpy array, L2-normalized for cosine similarity.
    """
    if not chunks:
        return np.empty((0, EMBEDDING_DIM), dtype="float32")

    model = _get_transformer_model()
    if model is not None:
        try:
            embeddings = model.encode(chunks, convert_to_numpy=True, normalize_embeddings=True)
            return embeddings.astype("float32")
        except Exception as exc:
            logger.warning(
                "Neural embedding failed (%s); falling back to deterministic vectors.", exc
            )

    vectors = [_deterministic_vector(chunk) for chunk in chunks]
    matrix = np.array(vectors, dtype="float32")
    # Normalize L2
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (matrix / norms).astype("float32")


def cosine_similarity(a: list[float] | np.ndarray, b: list[float] | np.ndarray) -> float:
    """Compute cosine similarity between two float vectors."""
    vec_a = np.asarray(a, dtype="float32")
    vec_b = np.asarray(b, dtype="float32")

    norm_a = np.linalg.norm(vec_a)
    norm_b = np.linalg.norm(vec_b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(vec_a, vec_b) / (norm_a * norm_b))


def build_index(
    topic_id: str | uuid.UUID,
    chunks: list[str],
    index_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Build a FAISS vector index for a topic's chunks and persist it to disk."""
    import faiss

    dest_dir = Path(index_dir) if index_dir is not None else Path("vector_store")
    dest_dir.mkdir(parents=True, exist_ok=True)

    if not chunks:
        # Create empty index
        index = faiss.IndexFlatIP(EMBEDDING_DIM)
        embeddings_list: list[list[float]] = []
    else:
        embeddings = embed_chunks(chunks)
        index = faiss.IndexFlatIP(EMBEDDING_DIM)
        index.add(embeddings)
        embeddings_list = embeddings.tolist()

    # Save FAISS index
    index_file = dest_dir / f"topic_{topic_id}.faiss"
    faiss.write_index(index, str(index_file))

    # Save chunks metadata
    metadata = {
        "topic_id": str(topic_id),
        "chunk_count": len(chunks),
        "chunks": chunks,
        "embeddings": embeddings_list,
    }
    meta_file = dest_dir / f"topic_{topic_id}.json"
    meta_file.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    return metadata


def load_index(
    topic_id: str | uuid.UUID,
    index_dir: str | Path | None = None,
) -> tuple[Any | None, list[str]]:
    """Load the FAISS index and chunk texts for a topic."""
    import faiss

    dest_dir = Path(index_dir) if index_dir is not None else Path("vector_store")
    index_file = dest_dir / f"topic_{topic_id}.faiss"
    meta_file = dest_dir / f"topic_{topic_id}.json"

    chunks: list[str] = []
    if meta_file.exists():
        try:
            data = json.loads(meta_file.read_text(encoding="utf-8"))
            chunks = data.get("chunks", [])
        except Exception as exc:
            logger.warning("Failed to load topic metadata (%s): %s", meta_file, exc)

    index = None
    if index_file.exists():
        try:
            index = faiss.read_index(str(index_file))
        except Exception as exc:
            logger.warning("Failed to load FAISS index (%s): %s", index_file, exc)

    return index, chunks


def retrieve_relevant_chunks(
    query: str,
    chunks: list[str],
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """Rank in-memory chunks by cosine similarity to query."""
    if not chunks:
        return []

    query_emb = embed_chunks([query])[0]
    chunk_embs = embed_chunks(chunks)

    scored: list[dict[str, Any]] = []
    for chunk, emb in zip(chunks, chunk_embs, strict=False):
        score = float(np.dot(query_emb, emb))
        scored.append({"text": chunk, "score": score})

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]


def retrieve_for_topic(
    topic_id: str | uuid.UUID,
    query: str,
    top_k: int = 5,
    index_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Query a topic's persisted FAISS index to retrieve the top-k chunks."""
    index, chunks = load_index(topic_id, index_dir=index_dir)
    if index is None or not chunks:
        return []

    query_emb = embed_chunks([query])
    k = min(top_k, len(chunks))
    distances, indices = index.search(query_emb, k)

    results: list[dict[str, Any]] = []
    for dist, idx in zip(distances[0], indices[0], strict=False):
        if 0 <= idx < len(chunks):
            results.append({"text": chunks[idx], "score": float(dist)})

    return results
