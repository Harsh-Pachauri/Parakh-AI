"""Phase 2 behavior tests: document ingestion, RAG chunking, and question generation."""

import uuid

import pytest
from fastapi import status

from app.services.question_service import QuestionService
from app.services.rag_service import chunk_text, retrieve_relevant_chunks
from tests.test_courses import create_user_and_get_token


@pytest.mark.asyncio
async def test_document_upload_and_list(client):
    """Teachers can upload a text document to a topic and list it back."""
    token = await create_user_and_get_token(
        client, "teacher2@example.com", "teacher", "Teacher Two"
    )

    course = await client.post(
        "/api/courses",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Biology 101",
            "code": "BIO101",
            "description": "Introductory biology",
        },
    )
    course_id = course.json()["id"]
    topic = await client.post(
        f"/api/courses/{course_id}/topics",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Cell Biology", "sort_order": 1},
    )
    topic_id = topic.json()["id"]

    response = await client.post(
        f"/api/topics/{topic_id}/documents",
        headers={"Authorization": f"Bearer {token}"},
        files={
            "file": (
                "syllabus.txt",
                b"Cell division is crucial for growth. Mitosis produces identical cells.",
                "text/plain",
            )
        },
    )
    assert response.status_code == status.HTTP_201_CREATED
    body = response.json()
    assert body["filename"] == "syllabus.txt"
    assert body["topic_id"] == str(topic_id)

    listing = await client.get(
        f"/api/topics/{topic_id}/documents",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert listing.status_code == status.HTTP_200_OK
    assert len(listing.json()) >= 1


def test_chunking_and_retrieval_helpers():
    """Chunking should split text into manageable units with overlap, and the retrieval helper should rank relevant content first."""
    text = " ".join(
        [
            "Mitosis is the process of cell division.",
            "During mitosis chromosomes align and separate.",
            "Cell growth requires nutrients and energy.",
            "The cell cycle includes interphase and mitosis.",
            "During interphase DNA is copied.",
            "Cell differentiation is a separate process.",
        ]
    )

    chunks = chunk_text(text, chunk_size=18, overlap=5)
    assert len(chunks) >= 2
    assert all(len(chunk.split()) <= 25 for chunk in chunks)

    relevant = retrieve_relevant_chunks(
        "mitosis and cell division",
        chunks,
        top_k=2,
    )
    assert relevant
    assert (
        relevant[0]["text"].lower().find("mitosis") >= 0
        or relevant[0]["text"].lower().find("cell division") >= 0
    )


@pytest.mark.asyncio
async def test_question_generation_returns_structured_questions(client, monkeypatch):
    """The generator should create a list of exam questions with key points and difficulty."""
    token = await create_user_and_get_token(
        client, "teacher3@example.com", "teacher", "Teacher Three"
    )

    class ApiStaticProvider:
        async def generate(self, prompt: str, schema: dict | None = None):
            return [
                {
                    "question": "Explain motion.",
                    "key_points": ["velocity", "acceleration"],
                    "difficulty": "easy",
                }
            ]

    monkeypatch.setattr("app.services.question_service.get_provider", lambda: ApiStaticProvider())

    course = await client.post(
        "/api/courses",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Physics 101",
            "code": "PHY101",
            "description": "Intro physics",
        },
    )
    topic = await client.post(
        f"/api/courses/{course.json()['id']}/topics",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Motion", "sort_order": 1},
    )
    topic_id = uuid.UUID(topic.json()["id"])

    class StaticProvider:
        async def generate(self, prompt: str, schema: dict | None = None):
            return [
                {
                    "question": "Describe uniform motion.",
                    "key_points": ["constant velocity", "zero acceleration"],
                    "difficulty": "easy",
                },
                {
                    "question": "Explain how friction changes motion.",
                    "key_points": ["opposes motion", "reduces acceleration"],
                    "difficulty": "medium",
                },
            ]

    service = QuestionService()
    questions = await service.generate_questions(
        topic_id=topic_id,
        context_chunks=[
            "Uniform motion occurs when velocity is constant.",
            "Friction opposes motion and reduces acceleration.",
        ],
        count=2,
        llm_provider=StaticProvider(),
    )

    assert len(questions) == 2
    assert all("question" in item for item in questions)
    assert all("key_points" in item for item in questions)
    assert all("difficulty" in item for item in questions)
