"""Tests for QuestionService, LLM prompt versioning, deduplication, and question CRUD endpoints."""

import uuid

import pytest
from fastapi import status
from sqlalchemy import select

from app.llm.base import LLMProvider
from app.llm.groq import GroqProvider
from app.models.prompt_version import PromptVersion
from app.models.question import Question
from app.services.llm_service import get_provider
from app.services.question_service import QuestionService
from tests.test_courses import create_user_and_get_token


class MockStaticLLMProvider(LLMProvider):
    """Predictable mock provider returning schema-conformant exam questions."""

    async def generate(self, prompt: str, schema: dict | None = None):
        return [
            {
                "question": "Explain how virtual methods facilitate polymorphism in C++.",
                "key_points": ["vtable lookup", "dynamic dispatch", "base class pointer"],
                "difficulty": "medium",
            },
            {
                "question": "Define encapsulation and explain why class member variables are kept private.",
                "key_points": ["information hiding", "access specifiers", "invariants protection"],
                "difficulty": "easy",
            },
        ]


@pytest.mark.asyncio
async def test_question_service_with_mocked_llm(db_session):
    """QuestionService should parse mocked LLM output and persist questions and prompt version."""
    topic_id = uuid.uuid4()
    service = QuestionService()

    questions = await service.generate_questions(
        topic_id=topic_id,
        context_chunks=["Virtual methods allow overriding. Encapsulation hides state."],
        count=2,
        topic_name="OOP Fundamentals",
        llm_provider=MockStaticLLMProvider(),
        db=db_session,
    )

    assert len(questions) == 2
    assert questions[0]["difficulty"] == "medium"
    assert len(questions[0]["key_points"]) == 3
    assert questions[1]["difficulty"] == "easy"

    # Verify questions in database
    db_result = await db_session.execute(select(Question).where(Question.topic_id == topic_id))
    persisted = db_result.scalars().all()
    assert len(persisted) == 2
    assert persisted[0].prompt_version == "question_gen_v1"

    # Verify PromptVersion was saved in DB
    pv_result = await db_session.execute(
        select(PromptVersion).where(PromptVersion.name == "question_gen")
    )
    pv = pv_result.scalar_one_or_none()
    assert pv is not None
    assert pv.version == "v1"
    assert pv.is_active is True


@pytest.mark.asyncio
async def test_question_deduplication(db_session):
    """Re-generating questions should not duplicate existing question entries in the database."""
    topic_id = uuid.uuid4()
    service = QuestionService()

    # First generation
    first_batch = await service.generate_questions(
        topic_id=topic_id,
        context_chunks=["Polymorphism concept"],
        count=2,
        llm_provider=MockStaticLLMProvider(),
        db=db_session,
    )
    assert len(first_batch) == 2

    # Second generation with identical provider output
    second_batch = await service.generate_questions(
        topic_id=topic_id,
        context_chunks=["Polymorphism concept"],
        count=2,
        llm_provider=MockStaticLLMProvider(),
        db=db_session,
    )
    assert len(second_batch) <= 2

    # Database count must still be 2, not 4
    db_result = await db_session.execute(select(Question).where(Question.topic_id == topic_id))
    all_questions = db_result.scalars().all()
    assert len(all_questions) == 2


def test_groq_is_the_only_provider(monkeypatch):
    """No alternative or local LLM is selected when Groq is unavailable."""
    from types import SimpleNamespace

    monkeypatch.setattr(
        "app.llm.groq.get_settings",
        lambda: SimpleNamespace(
            GROQ_API_KEY="test-key",
            GROQ_MODEL="openai/gpt-oss-120b",
            GROQ_TIMEOUT_SECONDS=3.0,
        ),
    )
    assert isinstance(get_provider(), GroqProvider)


@pytest.mark.asyncio
async def test_question_api_crud_flow(client, monkeypatch):
    """End-to-end question CRUD lifecycle: generate -> list -> get -> update -> approve -> delete."""
    # 1. Register teacher
    t_token = await create_user_and_get_token(
        client, "prof_questions@example.com", "teacher", "Prof Q"
    )
    t_headers = {"Authorization": f"Bearer {t_token}"}

    class StaticProvider:
        async def generate(self, prompt: str, schema: dict | None = None):
            return [
                {
                    "question": "What is a data structure?",
                    "key_points": ["organizes data"],
                    "difficulty": "easy",
                }
            ]

    monkeypatch.setattr("app.services.question_service.get_provider", lambda: StaticProvider())

    # 2. Register student
    s_res = await client.post(
        "/api/auth/register",
        json={
            "email": "student_q@example.com",
            "password": "password123",
            "full_name": "Student Q",
            "role": "student",
        },
    )
    s_token = s_res.json()["access_token"]
    s_headers = {"Authorization": f"Bearer {s_token}"}

    # 3. Create course & topic
    c_res = await client.post(
        "/api/courses",
        headers=t_headers,
        json={"name": "Algorithms", "code": "CS201", "description": "Algo"},
    )
    course_id = c_res.json()["id"]

    topic_res = await client.post(
        f"/api/courses/{course_id}/topics",
        headers=t_headers,
        json={"name": "Sorting Algorithms", "sort_order": 1},
    )
    topic_id = topic_res.json()["id"]

    # 4. Generate questions via API
    gen_res = await client.post(
        f"/api/topics/{topic_id}/questions/generate", headers=t_headers, json={"count": 3}
    )
    assert gen_res.status_code == status.HTTP_200_OK
    questions = gen_res.json()
    assert len(questions) >= 1
    q_id = questions[0]["id"]

    # 5. List questions
    list_res = await client.get(f"/api/topics/{topic_id}/questions", headers=s_headers)
    assert list_res.status_code == status.HTTP_200_OK
    assert len(list_res.json()) >= 1

    # 6. Get single question
    get_res = await client.get(f"/api/questions/{q_id}", headers=s_headers)
    assert get_res.status_code == status.HTTP_200_OK
    assert get_res.json()["id"] == q_id

    # 7. Student forbidden from editing question
    forbidden_edit = await client.put(
        f"/api/questions/{q_id}", headers=s_headers, json={"question_text": "Hacked Question?"}
    )
    assert forbidden_edit.status_code == status.HTTP_403_FORBIDDEN

    # 8. Teacher updates question
    edit_res = await client.put(
        f"/api/questions/{q_id}",
        headers=t_headers,
        json={
            "question_text": "Explain the average and worst-case complexities of Quicksort.",
            "expected_key_points": ["O(n log n) average", "O(n^2) worst case", "Pivot selection"],
            "difficulty": "hard",
        },
    )
    assert edit_res.status_code == status.HTTP_200_OK
    assert edit_res.json()["difficulty"] == "hard"
    assert "Quicksort" in edit_res.json()["question_text"]

    # 9. Teacher approves question
    approve_res = await client.post(f"/api/questions/{q_id}/approve", headers=t_headers)
    assert approve_res.status_code == status.HTTP_200_OK
    assert approve_res.json()["is_approved"] is True

    # 10. Teacher deletes question
    del_res = await client.delete(f"/api/questions/{q_id}", headers=t_headers)
    assert del_res.status_code == status.HTTP_204_NO_CONTENT

    # 11. Verify deleted
    verify_res = await client.get(f"/api/questions/{q_id}", headers=t_headers)
    assert verify_res.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_teacher_question_bank_crud_search_and_ownership(client):
    owner_token = await create_user_and_get_token(
        client, "bank.owner@example.com", "teacher", "Bank Owner"
    )
    other_token = await create_user_and_get_token(
        client, "bank.other@example.com", "teacher", "Other Teacher"
    )
    owner_headers = {"Authorization": "Bearer " + owner_token}
    other_headers = {"Authorization": "Bearer " + other_token}
    course = await client.post(
        "/api/courses",
        headers=owner_headers,
        json={"name": "Databases", "code": "DB301", "syllabus_text": "Normalization and indexes."},
    )
    topic = await client.post(
        f"/api/courses/{course.json()['id']}/topics",
        headers=owner_headers,
        json={"name": "Normalization"},
    )
    created = await client.post(
        "/api/questions",
        headers=owner_headers,
        json={
            "topic_id": topic.json()["id"],
            "question_text": "Explain third normal form.",
            "expected_key_points": ["functional dependencies", "transitive dependency"],
            "difficulty": "medium",
            "question_type": "conceptual",
            "tags": ["dbms"],
        },
    )
    assert created.status_code == 201, created.text
    question_id = created.json()["id"]

    listing = await client.get(
        "/api/questions",
        headers=owner_headers,
        params={"search": "third normal", "course_id": course.json()["id"], "limit": 5},
    )
    assert listing.status_code == 200, listing.text
    assert listing.json()["total"] == 1
    assert listing.json()["items"][0]["id"] == question_id

    forbidden = await client.put(
        f"/api/questions/{question_id}",
        headers=other_headers,
        json={"question_text": "Unauthorized edit"},
    )
    assert forbidden.status_code == 403
    updated = await client.put(
        f"/api/questions/{question_id}",
        headers=owner_headers,
        json={"question_text": "Explain 3NF and its role.", "tags": ["normalization", "dbms"]},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["question_text"] == "Explain 3NF and its role."

    persisted = await client.get(f"/api/questions/{question_id}", headers=owner_headers)
    assert persisted.json()["tags"] == ["normalization", "dbms"]
    deleted = await client.delete(f"/api/questions/{question_id}", headers=owner_headers)
    assert deleted.status_code == 204
    assert (await client.get("/api/questions", headers=owner_headers)).json()["total"] == 0


@pytest.mark.asyncio
async def test_question_create_rejects_missing_expected_points(client):
    token = await create_user_and_get_token(
        client, "bank.invalid@example.com", "teacher", "Bank Invalid"
    )
    headers = {"Authorization": "Bearer " + token}
    course = await client.post(
        "/api/courses",
        headers=headers,
        json={"name": "Networks", "code": "NET201"},
    )
    topic = await client.post(
        f"/api/courses/{course.json()['id']}/topics",
        headers=headers,
        json={"name": "Routing"},
    )
    response = await client.post(
        "/api/questions",
        headers=headers,
        json={"topic_id": topic.json()["id"], "question_text": "Explain routing."},
    )
    assert response.status_code == 422
