"""Regression and production readiness tests for Parakh AI."""

import uuid
from pathlib import Path

import pytest
from httpx import AsyncClient

from app.config import Settings
from app.models.answer import Answer
from app.models.question import Question
from app.models.user import UserRole
from app.models.viva_session import VivaSession
from tests.test_courses import create_user_and_get_token
from tests.test_institutions import _create_user_and_token


@pytest.mark.asyncio
async def test_oversized_document_rejected(client: AsyncClient, monkeypatch) -> None:
    """Document uploads exceeding MAX_UPLOAD_SIZE_MB must be rejected."""
    teacher_token = await create_user_and_get_token(
        client, "doc_size_teacher@viva.edu", "teacher", "Doc Size Teacher"
    )
    h_teacher = {"Authorization": f"Bearer {teacher_token}"}

    course = (
        await client.post(
            "/api/courses",
            headers=h_teacher,
            json={"name": "File Test Course", "code": "FTC101"},
        )
    ).json()

    topic = (
        await client.post(
            f"/api/courses/{course['id']}/topics",
            headers=h_teacher,
            json={"name": "File Upload Topic", "sort_order": 1},
        )
    ).json()

    # Simulate a file larger than the configured limit by setting limit to 1MB
    monkeypatch.setattr(
        "app.services.document_service.get_settings",
        lambda: Settings(MAX_UPLOAD_SIZE_MB=1),
    )

    oversized_bytes = b"X" * (1024 * 1024 + 100)  # > 1MB
    response = await client.post(
        f"/api/topics/{topic['id']}/documents",
        headers=h_teacher,
        files={"file": ("huge_doc.txt", oversized_bytes, "text/plain")},
    )
    assert response.status_code == 400
    assert "exceeds maximum allowed size" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_oversized_audio_rejected(client: AsyncClient, db_session, monkeypatch) -> None:
    """Audio submissions exceeding MAX_UPLOAD_SIZE_MB must return 413 Payload Too Large."""
    teacher_token = await create_user_and_get_token(
        client, "audio_teacher@viva.edu", "teacher", "Audio Teacher"
    )
    student_token = await create_user_and_get_token(
        client, "audio_size_student@viva.edu", "student", "Audio Size Student"
    )
    h_teacher = {"Authorization": f"Bearer {teacher_token}"}
    h_student = {"Authorization": f"Bearer {student_token}"}

    course = (
        await client.post(
            "/api/courses",
            headers=h_teacher,
            json={"name": "Audio Course", "code": "AC101"},
        )
    ).json()

    topic = (
        await client.post(
            f"/api/courses/{course['id']}/topics",
            headers=h_teacher,
            json={"name": "Audio Topic", "sort_order": 1},
        )
    ).json()

    question = Question(
        topic_id=uuid.UUID(topic["id"]),
        question_text="Audio question test?",
        expected_key_points=["point 1"],
    )
    db_session.add(question)
    await db_session.commit()
    await db_session.refresh(question)

    session_res = await client.post(
        "/api/viva/sessions",
        headers=h_student,
        json={"course_id": course["id"]},
    )
    assert session_res.status_code == 201
    session = session_res.json()

    # Simulate max upload size = 1MB
    monkeypatch.setattr(
        "app.api.viva.get_settings",
        lambda: Settings(MAX_UPLOAD_SIZE_MB=1),
    )

    oversized_audio = b"RIFF" + b"\x00" * (1024 * 1024 + 50)
    response = await client.post(
        f"/api/viva/sessions/{session['id']}/answer",
        headers=h_student,
        files={"file": ("huge_audio.webm", oversized_audio, "audio/webm")},
        data={"question_id": str(question.id)},
    )
    assert response.status_code == 413
    assert "exceeds maximum allowed size" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_audio_cleanup_removes_both_webm_and_converted_wav(
    client: AsyncClient, db_session
) -> None:
    """Audio deletion removes both the raw .webm and any generated .wav alongside it."""
    teacher_token = await create_user_and_get_token(
        client, "cleanup_teacher@viva.edu", "teacher", "Cleanup Teacher"
    )
    student_token = await _create_user_and_token(
        client, "cleanup_student@viva.edu", UserRole.STUDENT, "Cleanup Student"
    )
    h_teacher = {"Authorization": f"Bearer {teacher_token}"}
    h_student = {"Authorization": f"Bearer {student_token}"}

    me = (await client.get("/api/auth/me", headers=h_student)).json()
    user_id = uuid.UUID(me["id"])

    course = (
        await client.post(
            "/api/courses",
            headers=h_teacher,
            json={"name": "Cleanup Course", "code": "CC101"},
        )
    ).json()

    topic = (
        await client.post(
            f"/api/courses/{course['id']}/topics",
            headers=h_teacher,
            json={"name": "Cleanup Topic", "sort_order": 1},
        )
    ).json()

    question = Question(
        topic_id=uuid.UUID(topic["id"]),
        question_text="Cleanup test question?",
        expected_key_points=["point 1"],
    )
    db_session.add(question)
    await db_session.commit()
    await db_session.refresh(question)

    # Create dummy answer record and dummy audio files on disk
    upload_dir = Path("uploads") / "audio"
    upload_dir.mkdir(parents=True, exist_ok=True)

    dummy_session_id = uuid.uuid4()
    viva_session = VivaSession(
        id=dummy_session_id,
        student_id=user_id,
        course_id=uuid.UUID(course["id"]),
        status="in_progress",
    )
    db_session.add(viva_session)

    raw_file = upload_dir / f"{dummy_session_id}_{user_id}_test.webm"
    wav_file = upload_dir / f"{dummy_session_id}_{user_id}_test.wav"
    raw_file.write_bytes(b"dummy webm")
    wav_file.write_bytes(b"dummy wav")

    dummy_answer = Answer(
        session_id=dummy_session_id,
        question_id=question.id,
        sequence_number=1,
        transcript="Test transcript",
        audio_path=str(raw_file),
    )
    db_session.add(dummy_answer)
    await db_session.commit()

    assert raw_file.exists()
    assert wav_file.exists()

    # Invoke delete audio endpoint
    delete_res = await client.delete(f"/api/users/{user_id}/audio", headers=h_student)
    assert delete_res.status_code == 200
    assert delete_res.json()["deleted_count"] >= 1

    # Verify both files removed from disk
    assert not raw_file.exists()
    assert not wav_file.exists()


def test_settings_secret_key_validation() -> None:
    """Settings must reject short or empty secret keys."""
    with pytest.raises(ValueError, match="SECRET_KEY must be at least 16 characters long"):
        Settings(SECRET_KEY="short")

    valid_settings = Settings(SECRET_KEY="a-very-secure-random-secret-key-12345")
    assert valid_settings.SECRET_KEY == "a-very-secure-random-secret-key-12345"
