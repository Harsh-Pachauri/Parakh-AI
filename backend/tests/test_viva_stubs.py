"""Tests for the basic Phase 3 viva speech pipeline."""

import uuid

import pytest
from httpx import AsyncClient

from app.models.question import Question
from tests.test_courses import create_user_and_get_token


@pytest.mark.asyncio
async def test_start_session_and_submit_answer_with_consent(
    client: AsyncClient, db_session, monkeypatch
) -> None:
    """Students can start a viva session and submit an answer when consent is recorded."""
    teacher_token = await create_user_and_get_token(
        client, "viva.teacher@viva.edu", "teacher", "Viva Teacher"
    )
    student_token = await create_user_and_get_token(
        client, "viva.student@viva.edu", "student", "Viva Student"
    )

    course = await client.post(
        "/api/courses",
        headers={"Authorization": f"Bearer {teacher_token}"},
        json={"name": "Algorithms", "code": "CS900", "description": "Intro algorithms"},
    )
    topic = await client.post(
        f"/api/courses/{course.json()['id']}/topics",
        headers={"Authorization": f"Bearer {teacher_token}"},
        json={"name": "Greedy Algorithms", "sort_order": 1},
    )

    question = Question(
        topic_id=uuid.UUID(topic.json()["id"]),
        question_text="Explain greedy choice property.",
        expected_key_points=["makes locally optimal choice", "leads to global optimum"],
    )
    db_session.add(question)
    await db_session.commit()
    await db_session.refresh(question)

    class LocalJudge:
        async def generate(self, prompt: str, schema: dict | None = None):
            return {
                "question": "What limitation can arise from this greedy choice?",
                "key_points": ["optimality"],
                "difficulty": "medium",
            }

    monkeypatch.setattr("app.services.llm_service.get_provider", lambda: LocalJudge())
    monkeypatch.setattr("app.services.viva_orchestrator.get_provider", lambda: LocalJudge())

    async def low_score(**kwargs):
        return {
            "embedding_score": 0.1,
            "llm_score": 0.2,
            "fused_score": 0.16,
            "rubric": {"correctness": 2},
        }

    monkeypatch.setattr("app.api.viva.evaluate_answer", low_score)
    monkeypatch.setattr(
        "app.api.viva.SpeechService.transcribe",
        lambda self, path: {
            "text": "A greedy algorithm makes a locally optimal choice.",
            "confidence": 0.9,
            "segments": [],
            "duration_ms": 900,
        },
    )

    session = await client.post(
        "/api/viva/sessions",
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert session.status_code == 201, session.text
    session_id = session.json()["id"]

    consent = await client.post(
        "/api/consent",
        headers={"Authorization": f"Bearer {student_token}"},
        json={
            "session_id": session_id,
            "audio_retention_consent": True,
            "transcript_consent": True,
            "camera_analysis_consent": True,
        },
    )
    assert consent.status_code == 201, consent.text

    audio = await client.post(
        f"/api/viva/sessions/{session_id}/answer",
        headers={"Authorization": f"Bearer {student_token}"},
        files={"file": ("hello.webm", b"fake-audio-bytes", "audio/webm")},
        data={"question_id": str(question.id)},
    )
    assert audio.status_code == 200, audio.text
    data = audio.json()
    assert "transcript" in data
    assert data["audio_saved"] is True
    assert data["followup"]["question_text"] == "What limitation can arise from this greedy choice?"

    cue = await client.post(
        f"/api/viva/sessions/{session_id}/behavior-flags",
        headers={"Authorization": f"Bearer {student_token}"},
        json={"cue_type": "additional_faces"},
    )
    assert cue.status_code == 201, cue.text
    assert cue.json()["cue_type"] == "additional_faces"

    next_question = await client.post(
        f"/api/viva/sessions/{session_id}/next",
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert next_question.status_code == 200, next_question.text
    payload = next_question.json()
    assert payload["question_id"] == data["followup"]["question_id"]
    assert payload["question_text"] == data["followup"]["question_text"]
    assert payload["session_id"] == session_id

    finish = await client.post(
        f"/api/viva/sessions/{session_id}/finish",
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert finish.status_code == 200, finish.text
    summary = finish.json()
    assert summary["status"] == "completed"
    assert summary["total_score"] >= 0.0

    review = await client.get(
        f"/api/viva/sessions/{session_id}/report",
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert review.status_code == 200
    assert review.json()["behavior_flags"][0]["cue_type"] == "additional_faces"


@pytest.mark.asyncio
async def test_delete_user_audio_removes_recorded_files(
    client: AsyncClient, db_session, monkeypatch
) -> None:
    """Audio deletion should remove saved audio and clear audio_path records for that user."""
    teacher_token = await create_user_and_get_token(
        client, "viva.teacher.delete@viva.edu", "teacher", "Viva Teacher Delete"
    )
    token = await create_user_and_get_token(
        client, "viva.delete@viva.edu", "student", "Viva Deleter"
    )
    create_course = await client.post(
        "/api/courses",
        headers={"Authorization": f"Bearer {teacher_token}"},
        json={"name": "Data Mining", "code": "CS901", "description": "Mining data"},
    )
    course_id = create_course.json()["id"]
    create_topic = await client.post(
        f"/api/courses/{course_id}/topics",
        headers={"Authorization": f"Bearer {teacher_token}"},
        json={"name": "Association Rules", "sort_order": 1},
    )

    question = Question(
        topic_id=uuid.UUID(create_topic.json()["id"]),
        question_text="Explain association rule mining.",
        expected_key_points=["support", "confidence", "interestingness"],
    )
    db_session.add(question)
    await db_session.commit()
    await db_session.refresh(question)

    class LocalJudge:
        async def generate(self, prompt: str, schema: dict | None = None):
            return {
                "correctness": 6,
                "completeness": 6,
                "clarity": 6,
                "justification": "Practice response.",
            }

    monkeypatch.setattr("app.services.llm_service.get_provider", lambda: LocalJudge())
    monkeypatch.setattr(
        "app.api.viva.SpeechService.transcribe",
        lambda self, path: {
            "text": "Association rules measure support and confidence.",
            "confidence": 0.9,
            "segments": [],
            "duration_ms": 900,
        },
    )

    session = await client.post("/api/viva/sessions", headers={"Authorization": f"Bearer {token}"})
    assert session.status_code == 201
    session_id = session.json()["id"]

    consent = await client.post(
        "/api/consent",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "session_id": session_id,
            "audio_retention_consent": True,
            "transcript_consent": True,
        },
    )
    assert consent.status_code == 201

    audio = await client.post(
        f"/api/viva/sessions/{session_id}/answer",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("mining.webm", b"fake-audio-bytes", "audio/webm")},
        data={"question_id": str(question.id)},
    )
    assert audio.status_code == 200
    audio_path = audio.json().get("audio_path")
    assert audio_path is not None

    delete_audio = await client.delete(
        f"/api/users/{session.json()['student_id']}/audio",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert delete_audio.status_code == 200
    payload = delete_audio.json()
    assert payload["deleted_count"] >= 1
