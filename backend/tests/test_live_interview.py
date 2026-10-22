"""Integration tests for authenticated live interview turns."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.answer import Answer
from app.models.course import Course
from app.models.question import Question
from app.models.viva_session import VivaSession
from tests.test_courses import create_user_and_get_token


@pytest.mark.asyncio
async def test_live_turn_persists_answer_and_queues_contextual_question(
    client: AsyncClient, db_session, monkeypatch
) -> None:
    teacher_token = await create_user_and_get_token(
        client, "live.teacher@viva.edu", "teacher", "Live Interview Teacher"
    )
    student_token = await create_user_and_get_token(
        client, "live.student@viva.edu", "student", "Live Interview Student"
    )
    headers = {"Authorization": f"Bearer {teacher_token}"}
    course = await client.post(
        "/api/courses",
        headers=headers,
        json={
            "name": "Algorithms",
            "code": "LIVE101",
            "description": "Algorithms course",
            "syllabus_text": "Graph traversal uses queues and stacks; cycle detection is important.",
        },
    )
    topic = await client.post(
        f"/api/courses/{course.json()['id']}/topics",
        headers=headers,
        json={"name": "Graph Search", "sort_order": 1},
    )
    course_row = await db_session.get(Course, uuid.UUID(course.json()["id"]))
    assert course_row is not None
    course_row.syllabus_text = "Graph traversal and cycle detection. " * 4000
    course_row.syllabus_analysis = {
        "modules": [
            {
                "name": f"Module {index} " + ("irrelevant context " * 100),
                "topics": [
                    {
                        "name": "Graph Search",
                        "subtopics": ["Breadth-first search"] * 100,
                        "key_concepts": ["Queue-based traversal"] * 100,
                        "learning_objectives": ["irrelevant"] * 100,
                        "source_references": [{"start": 0, "end": len(course_row.syllabus_text)}],
                    }
                ],
            }
            for index in range(30)
        ]
    }
    first = Question(
        topic_id=uuid.UUID(topic.json()["id"]),
        question_text="How does breadth-first search explore a graph?",
        expected_key_points=["level by level", "queue"],
    )
    second = Question(
        topic_id=uuid.UUID(topic.json()["id"]),
        question_text="When is depth-first search useful?",
        expected_key_points=["explores deeply", "cycle detection"],
    )
    db_session.add_all([first, second])
    await db_session.commit()

    async def evaluate(**kwargs):
        assert kwargs["transcript"].strip()
        return {
            "embedding_score": 0.8,
            "llm_score": 0.9,
            "fused_score": 0.86,
            "rubric": {"correctness": 9, "completeness": 8, "clarity": 9},
        }

    class InterviewProvider:
        def __init__(self):
            self.calls = 0

        async def generate(self, prompt: str, schema: dict | None = None):
            self.calls += 1
            assert "Conversation so far:" in prompt
            assert len(prompt) < 10000
            assert schema is not None
            if self.calls == 1:
                return {
                    "action": "ask_question",
                    "acknowledgement": "Good explanation of the queue's role.",
                    "question": "How does depth-first search differ in its traversal order?",
                    "topic_id": topic.json()["id"],
                    "question_source": "question_bank",
                    "question_bank_id": str(second.id),
                    "difficulty": "medium",
                    "question_type": "conceptual",
                    "is_cross_question": False,
                    "reason": "Assess contrast in graph traversal.",
                    "expected_concepts": ["explores one branch deeply", "uses a stack"],
                    "coverage_update": {"topic_id": topic.json()["id"], "status": "in_progress"},
                }
            return {
                "action": "ask_follow_up",
                "acknowledgement": "You connected the stack to depth-first exploration.",
                "question": "How can a visited set prevent repeated work when a graph contains cycles?",
                "topic_id": topic.json()["id"],
                "question_source": "generated",
                "question_bank_id": "__generated__",
                "difficulty": "medium",
                "question_type": "analytical",
                "is_cross_question": True,
                "reason": "Probe cycle handling based on the candidate's response.",
                "expected_concepts": ["visited set", "avoid revisiting nodes"],
                "coverage_update": {"topic_id": topic.json()["id"], "status": "needs_review"},
            }

    provider = InterviewProvider()
    monkeypatch.setattr("app.api.viva.evaluate_answer", evaluate)
    monkeypatch.setattr("app.api.viva.get_provider", lambda: provider)

    auth = {"Authorization": f"Bearer {student_token}"}
    created = await client.post("/api/viva/sessions", headers=auth)
    assert created.status_code == 201, created.text
    session_id = created.json()["id"]
    session_row = await db_session.scalar(
        select(VivaSession).where(VivaSession.id == uuid.UUID(session_id))
    )
    assert session_row is not None
    session_row.config = {
        **session_row.config,
        "question_order": [str(first.id), str(second.id)],
    }
    await db_session.commit()
    current = await client.post(f"/api/viva/sessions/{session_id}/next", headers=auth)
    assert current.status_code == 200, current.text

    response = await client.post(
        f"/api/viva/sessions/{session_id}/turn",
        headers=auth,
        json={
            "question_id": current.json()["question_id"],
            "transcript": "Breadth first search visits each level and uses a queue.",
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["transcript"] == "Breadth first search visits each level and uses a queue."
    assert data["interviewer_text"].startswith("Good explanation")
    assert data["next_question"]["question_text"].startswith("When is depth-first")
    assert data["completed"] is False

    saved = await db_session.execute(
        select(Answer).where(Answer.session_id == uuid.UUID(session_id))
    )
    assert len(saved.scalars().all()) == 1

    duplicate = await client.post(
        f"/api/viva/sessions/{session_id}/turn",
        headers=auth,
        json={
            "question_id": current.json()["question_id"],
            "transcript": "A duplicate answer.",
        },
    )
    assert duplicate.status_code == 409

    session = await db_session.scalar(
        select(VivaSession).where(VivaSession.id == uuid.UUID(session_id))
    )
    assert session is not None
    assert data["next_question"]["question_id"] in session.config["question_order"]

    cross_question = await client.post(
        f"/api/viva/sessions/{session_id}/turn",
        headers=auth,
        json={
            "question_id": data["next_question"]["question_id"],
            "transcript": "Depth first search uses a stack to explore one branch and detects cycles.",
        },
    )
    assert cross_question.status_code == 200, cross_question.text
    cross_data = cross_question.json()
    assert cross_data["next_question"]["is_cross_question"] is True
    assert "visited set" in cross_data["next_question"]["question_text"]
    generated_question = await db_session.scalar(
        select(Question).where(Question.prompt_version == "live_interview_v2")
    )
    assert generated_question is not None
    assert generated_question.expected_key_points == ["visited set", "avoid revisiting nodes"]
