"""Tests for RAG services: document extraction, recursive chunking, embeddings, and FAISS retrieval."""

import uuid
from pathlib import Path

import numpy as np
import pytest

from app.services.document_service import DocumentService
from app.services.rag_service import (
    EMBEDDING_DIM,
    build_index,
    chunk_text,
    cosine_similarity,
    embed_chunks,
    retrieve_for_topic,
    retrieve_relevant_chunks,
)


def test_chunking_handles_short_and_empty_text():
    """Empty or short text should be handled gracefully without errors."""
    assert chunk_text("") == []
    assert chunk_text("   \n\t  ") == []

    short = "A single sentence explaining abstraction."
    chunks = chunk_text(short, chunk_size=50, overlap=10)
    assert len(chunks) == 1
    assert chunks[0] == short


def test_chunking_token_window_and_overlap():
    """Long multi-paragraph texts should be split with appropriate chunk sizes and overlap."""
    paragraphs = [
        "Object-oriented programming (OOP) is a programming paradigm based on the concept of objects.",
        "An object contains data in the form of fields and code in the form of procedures or methods.",
        "Encapsulation is an object-oriented programming concept that binds together the data and functions.",
        "Inheritance enables new objects to take on the properties of existing objects.",
        "Polymorphism allows objects of different types to be treated as instances of the same base type.",
    ]
    full_text = "\n\n".join(paragraphs)

    chunks = chunk_text(full_text, chunk_size=20, overlap=5)
    assert len(chunks) >= 3
    # Check that all chunks have words
    for chunk in chunks:
        assert len(chunk.split()) <= 25


def test_embed_chunks_output_shape_and_normalization():
    """Embeddings should have 384 dimensions and unit norm (L2 = 1.0)."""
    texts = [
        "Polymorphism allows dynamic method dispatch in object-oriented systems.",
        "Inheritance provides hierarchical code reuse.",
    ]
    embeddings = embed_chunks(texts)
    assert isinstance(embeddings, np.ndarray)
    assert embeddings.shape == (2, EMBEDDING_DIM)
    assert embeddings.dtype == np.float32

    # Verify unit norm
    norms = np.linalg.norm(embeddings, axis=1)
    for norm in norms:
        assert pytest.approx(float(norm), rel=1e-3) == 1.0


def test_cosine_similarity_computation():
    """Identical vectors should have similarity 1.0, orthogonal should have 0.0."""
    a = [1.0, 0.0, 0.0]
    b = [1.0, 0.0, 0.0]
    c = [0.0, 1.0, 0.0]

    assert pytest.approx(cosine_similarity(a, b), rel=1e-4) == 1.0
    assert pytest.approx(cosine_similarity(a, c), rel=1e-4) == 0.0


def test_retrieval_relevance_ranking():
    """Retrieval helper should rank the most semantically relevant chunk highest."""
    chunks = [
        "Database normalization organizes fields and tables of a relational database.",
        "Polymorphism and dynamic dispatch enable flexible software design patterns in OOP.",
        "Network packet routing determines the best path for data delivery across IP networks.",
    ]

    results = retrieve_relevant_chunks(
        "Explain polymorphism in object-oriented programming", chunks, top_k=2
    )
    assert len(results) == 2
    assert "Polymorphism" in results[0]["text"]
    assert results[0]["score"] >= results[1]["score"]


def test_faiss_index_build_and_retrieve_for_topic(tmp_path):
    """FAISS index should persist to disk and support topic-scoped nearest neighbor retrieval."""
    topic_id = uuid.uuid4()
    chunks = [
        "Binary search trees keep their keys in sorted order for logarithmic lookup.",
        "Hash tables use hash functions to compute an index into an array of buckets.",
        "Depth-first search traverses graph vertices along branches before backtracking.",
    ]

    metadata = build_index(topic_id, chunks, index_dir=tmp_path)
    assert metadata["chunk_count"] == 3
    assert (tmp_path / f"topic_{topic_id}.faiss").exists()
    assert (tmp_path / f"topic_{topic_id}.json").exists()

    top_chunks = retrieve_for_topic(
        topic_id, query="How does a binary search tree work?", top_k=2, index_dir=tmp_path
    )
    assert len(top_chunks) == 2
    assert "Binary search trees" in top_chunks[0]["text"]
    assert top_chunks[0]["score"] > 0


def test_pdf_extraction_from_real_fixture():
    """Extracting text from the sample syllabus PDF should retrieve all course topics."""
    pdf_path = (
        Path("backend/tests/fixtures/sample_syllabus.pdf")
        if Path("backend/tests/fixtures/sample_syllabus.pdf").exists()
        else Path("tests/fixtures/sample_syllabus.pdf")
    )
    assert pdf_path.exists(), "Sample syllabus fixture must exist"

    file_bytes = pdf_path.read_bytes()
    extracted_text = DocumentService.extract_text("sample_syllabus.pdf", file_bytes)

    assert "Course Syllabus" in extracted_text
    assert "Polymorphism" in extracted_text
    assert "Encapsulation" in extracted_text
