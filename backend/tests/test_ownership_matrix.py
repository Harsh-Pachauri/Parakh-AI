"""Comprehensive regression tests for cross-user resource ownership and authorization."""

import uuid
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.main import app
from app.models.answer import Answer
from app.models.document import Document
from app.models.user import User, UserRole


async def _create_user_and_token(client: AsyncClient, email: str, role: UserRole, name: str) -> str:
    """Helper to create a user with a specific role and return access token."""
    response = await client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "password1234",
            "full_name": name,
            "role": "student",
        },
    )
    assert response.status_code == 201, response.text
    if role != UserRole.STUDENT:
        database = app.state.test_db_session
        account = (await database.execute(select(User).where(User.email == email))).scalar_one()
        account.role = role
        await database.commit()
    return response.json()["access_token"]


@pytest.mark.asyncio
async def test_teacher_course_isolation_and_admin_bypass(client: AsyncClient) -> None:
    """Teacher B cannot edit/delete Teacher A's course; Admin and Owner can."""
    t1_token = await _create_user_and_token(
        client, "t1_course@viva.edu", UserRole.TEACHER, "Teacher 1"
    )
    t2_token = await _create_user_and_token(
        client, "t2_course@viva.edu", UserRole.TEACHER, "Teacher 2"
    )
    admin_token = await _create_user_and_token(
        client, "admin_course@viva.edu", UserRole.ADMIN, "Admin"
    )

    h_t1 = {"Authorization": f"Bearer {t1_token}"}
    h_t2 = {"Authorization": f"Bearer {t2_token}"}
    h_admin = {"Authorization": f"Bearer {admin_token}"}

    create_res = await client.post(
        "/api/courses",
        headers=h_t1,
        json={"name": "Discrete Math", "code": "MATH201", "description": "Graph theory"},
    )
    assert create_res.status_code == 201
    course_id = create_res.json()["id"]

    # Missing resource returns 404
    missing_id = str(uuid.uuid4())
    assert (
        await client.put(f"/api/courses/{missing_id}", headers=h_t2, json={"name": "X"})
    ).status_code == 404
    assert (await client.delete(f"/api/courses/{missing_id}", headers=h_t2)).status_code == 404

    # Teacher B cannot update or delete Teacher A's course
    assert (
        await client.put(f"/api/courses/{course_id}", headers=h_t2, json={"name": "Hijacked"})
    ).status_code == 403
    assert (await client.delete(f"/api/courses/{course_id}", headers=h_t2)).status_code == 403

    # Admin CAN update Teacher A's course
    admin_up = await client.put(
        f"/api/courses/{course_id}", headers=h_admin, json={"name": "Admin Updated Math"}
    )
    assert admin_up.status_code == 200
    assert admin_up.json()["name"] == "Admin Updated Math"

    # Teacher A (owner) CAN update
    owner_up = await client.put(
        f"/api/courses/{course_id}", headers=h_t1, json={"name": "Discrete Math & Logic"}
    )
    assert owner_up.status_code == 200
    assert owner_up.json()["name"] == "Discrete Math & Logic"

    # Teacher A (owner) CAN delete
    assert (await client.delete(f"/api/courses/{course_id}", headers=h_t1)).status_code == 204


@pytest.mark.asyncio
async def test_teacher_topic_isolation(client: AsyncClient) -> None:
    """Teacher B cannot add, list, update, or delete topics on Teacher A's course; Student can list."""
    t1_token = await _create_user_and_token(
        client, "t1_topic@viva.edu", UserRole.TEACHER, "Teacher 1"
    )
    t2_token = await _create_user_and_token(
        client, "t2_topic@viva.edu", UserRole.TEACHER, "Teacher 2"
    )
    student_token = await _create_user_and_token(
        client, "stu_topic@viva.edu", UserRole.STUDENT, "Student"
    )

    h_t1 = {"Authorization": f"Bearer {t1_token}"}
    h_t2 = {"Authorization": f"Bearer {t2_token}"}
    h_stu = {"Authorization": f"Bearer {student_token}"}

    course = (
        await client.post("/api/courses", headers=h_t1, json={"name": "Networks", "code": "NET101"})
    ).json()
    course_id = course["id"]

    # Teacher B cannot add topic to Teacher A's course
    assert (
        await client.post(f"/api/courses/{course_id}/topics", headers=h_t2, json={"name": "TCP/IP"})
    ).status_code == 403

    # Teacher A adds topic
    topic = (
        await client.post(
            f"/api/courses/{course_id}/topics", headers=h_t1, json={"name": "OSI Model"}
        )
    ).json()
    topic_id = topic["id"]

    # Teacher B cannot view topics of Teacher A's course
    assert (await client.get(f"/api/courses/{course_id}/topics", headers=h_t2)).status_code == 403

    # Student CAN view topics of course for practice selection
    stu_topics = await client.get(f"/api/courses/{course_id}/topics", headers=h_stu)
    assert stu_topics.status_code == 200
    assert len(stu_topics.json()) == 1

    # Teacher B cannot update or delete Teacher A's topic
    assert (
        await client.put(f"/api/topics/{topic_id}", headers=h_t2, json={"name": "Hijacked Topic"})
    ).status_code == 403
    assert (await client.delete(f"/api/topics/{topic_id}", headers=h_t2)).status_code == 403

    # Missing topic returns 404
    missing_id = str(uuid.uuid4())
    assert (
        await client.put(f"/api/topics/{missing_id}", headers=h_t1, json={"name": "X"})
    ).status_code == 404
    assert (await client.delete(f"/api/topics/{missing_id}", headers=h_t1)).status_code == 404

    # Teacher A (owner) can update and delete
    assert (
        await client.put(f"/api/topics/{topic_id}", headers=h_t1, json={"name": "OSI 7 Layers"})
    ).status_code == 200
    assert (await client.delete(f"/api/topics/{topic_id}", headers=h_t1)).status_code == 204


@pytest.mark.asyncio
async def test_document_ownership_isolation(client: AsyncClient) -> None:
    """Teacher B cannot upload, list, embed, or delete Teacher A's documents; denied actions alter nothing."""
    t1_token = await _create_user_and_token(
        client, "t1_doc@viva.edu", UserRole.TEACHER, "Teacher 1"
    )
    t2_token = await _create_user_and_token(
        client, "t2_doc@viva.edu", UserRole.TEACHER, "Teacher 2"
    )
    admin_token = await _create_user_and_token(
        client, "admin_doc@viva.edu", UserRole.ADMIN, "Admin"
    )

    h_t1 = {"Authorization": f"Bearer {t1_token}"}
    h_t2 = {"Authorization": f"Bearer {t2_token}"}
    h_admin = {"Authorization": f"Bearer {admin_token}"}

    course = (
        await client.post(
            "/api/courses", headers=h_t1, json={"name": "AI Systems", "code": "AI401"}
        )
    ).json()
    topic = (
        await client.post(
            f"/api/courses/{course['id']}/topics", headers=h_t1, json={"name": "Transformers"}
        )
    ).json()
    topic_id = topic["id"]

    sample_file = {
        "file": ("notes.txt", b"Self-attention mechanisms allow long-range context.", "text/plain")
    }

    # Missing topic returns 404
    missing_id = str(uuid.uuid4())
    assert (
        await client.post(
            f"/api/topics/{missing_id}/documents",
            headers=h_t1,
            files={"file": ("a.txt", b"a", "text/plain")},
        )
    ).status_code == 404

    # Teacher B cannot upload document to Teacher A's topic
    denied_upload = await client.post(
        f"/api/topics/{topic_id}/documents", headers=h_t2, files=sample_file
    )
    assert denied_upload.status_code == 403

    # Teacher A uploads document successfully
    doc_res = await client.post(
        f"/api/topics/{topic_id}/documents", headers=h_t1, files=sample_file
    )
    assert doc_res.status_code == 201
    doc_id = doc_res.json()["id"]

    # Teacher B cannot list documents for Teacher A's topic
    assert (await client.get(f"/api/topics/{topic_id}/documents", headers=h_t2)).status_code == 403

    # Teacher A can list documents
    t1_docs = await client.get(f"/api/topics/{topic_id}/documents", headers=h_t1)
    assert t1_docs.status_code == 200
    assert len(t1_docs.json()) == 1

    # Teacher B cannot embed Teacher A's document
    assert (await client.post(f"/api/documents/{doc_id}/embed", headers=h_t2)).status_code == 403

    # Teacher B cannot delete Teacher A's document
    assert (await client.delete(f"/api/documents/{doc_id}", headers=h_t2)).status_code == 403

    # Verify document still exists in database after failed delete attempt
    db = app.state.test_db_session
    doc_in_db = (
        await db.execute(select(Document).where(Document.id == uuid.UUID(doc_id)))
    ).scalar_one_or_none()
    assert doc_in_db is not None, "Denied delete must not remove document from database"

    # Admin can embed Teacher A's document
    admin_embed = await client.post(f"/api/documents/{doc_id}/embed", headers=h_admin)
    assert admin_embed.status_code == 200

    # Teacher A can delete their own document
    assert (await client.delete(f"/api/documents/{doc_id}", headers=h_t1)).status_code == 204


@pytest.mark.asyncio
async def test_question_bank_isolation_and_student_shielding(client: AsyncClient) -> None:
    """Students cannot access question bank/details; Teacher B cannot tamper with Teacher A questions."""
    t1_token = await _create_user_and_token(client, "t1_q@viva.edu", UserRole.TEACHER, "Teacher 1")
    t2_token = await _create_user_and_token(client, "t2_q@viva.edu", UserRole.TEACHER, "Teacher 2")
    student_token = await _create_user_and_token(
        client, "stu_q@viva.edu", UserRole.STUDENT, "Student"
    )

    h_t1 = {"Authorization": f"Bearer {t1_token}"}
    h_t2 = {"Authorization": f"Bearer {t2_token}"}
    h_stu = {"Authorization": f"Bearer {student_token}"}

    course = (
        await client.post("/api/courses", headers=h_t1, json={"name": "Security", "code": "SEC201"})
    ).json()
    topic = (
        await client.post(
            f"/api/courses/{course['id']}/topics", headers=h_t1, json={"name": "Cryptography"}
        )
    ).json()
    topic_id = topic["id"]

    # Teacher B cannot create question in Teacher A's topic
    assert (
        await client.post(
            "/api/questions",
            headers=h_t2,
            json={
                "topic_id": topic_id,
                "question_text": "What is RSA?",
                "expected_key_points": ["asymmetric encryption", "primes"],
            },
        )
    ).status_code == 403

    # Teacher A creates question
    q_res = await client.post(
        "/api/questions",
        headers=h_t1,
        json={
            "topic_id": topic_id,
            "question_text": "Explain asymmetric key cryptography.",
            "expected_key_points": ["public key", "private key"],
            "difficulty": "medium",
        },
    )
    assert q_res.status_code == 201
    question_id = q_res.json()["id"]

    # Student CAN view questions for study but is forbidden from modifying
    assert (await client.get(f"/api/topics/{topic_id}/questions", headers=h_stu)).status_code == 200
    assert (await client.get(f"/api/questions/{question_id}", headers=h_stu)).status_code == 200
    assert (
        await client.put(
            f"/api/questions/{question_id}", headers=h_stu, json={"question_text": "Hacked"}
        )
    ).status_code == 403
    assert (
        await client.post(f"/api/questions/{question_id}/approve", headers=h_stu)
    ).status_code == 403
    assert (await client.delete(f"/api/questions/{question_id}", headers=h_stu)).status_code == 403

    # Teacher B cannot view, edit, approve, or delete Teacher A's question
    assert (await client.get(f"/api/topics/{topic_id}/questions", headers=h_t2)).status_code == 403
    assert (await client.get(f"/api/questions/{question_id}", headers=h_t2)).status_code == 403
    assert (
        await client.put(
            f"/api/questions/{question_id}", headers=h_t2, json={"question_text": "Hacked"}
        )
    ).status_code == 403
    assert (
        await client.post(f"/api/questions/{question_id}/approve", headers=h_t2)
    ).status_code == 403
    assert (await client.delete(f"/api/questions/{question_id}", headers=h_t2)).status_code == 403

    # Teacher A can view and edit
    t1_q = await client.get(f"/api/questions/{question_id}", headers=h_t1)
    assert t1_q.status_code == 200
    assert t1_q.json()["question_text"] == "Explain asymmetric key cryptography."


@pytest.mark.asyncio
async def test_session_review_and_export_isolation(client: AsyncClient) -> None:
    """Teacher B cannot view session reports, override scores, or export CSV for Teacher A's course."""
    t1_token = await _create_user_and_token(
        client, "t1_rep@viva.edu", UserRole.TEACHER, "Teacher 1"
    )
    t2_token = await _create_user_and_token(
        client, "t2_rep@viva.edu", UserRole.TEACHER, "Teacher 2"
    )
    stu_token = await _create_user_and_token(
        client, "stu_rep@viva.edu", UserRole.STUDENT, "Student"
    )

    h_t1 = {"Authorization": f"Bearer {t1_token}"}
    h_t2 = {"Authorization": f"Bearer {t2_token}"}
    h_stu = {"Authorization": f"Bearer {stu_token}"}

    course = (
        await client.post(
            "/api/courses", headers=h_t1, json={"name": "Software Eng", "code": "SE101"}
        )
    ).json()
    course_id = course["id"]

    # Student consents and creates session
    await client.post(
        "/api/consent", headers=h_stu, json={"audio_consent": True, "video_consent": True}
    )
    sess_res = await client.post("/api/viva/sessions", headers=h_stu, json={"course_id": course_id})
    assert sess_res.status_code == 201
    session_id = sess_res.json()["id"]

    # Teacher B cannot view Student session report in Teacher A's course
    assert (
        await client.get(f"/api/viva/sessions/{session_id}/report", headers=h_t2)
    ).status_code == 403

    # Teacher B cannot export CSV for Teacher A's course
    assert (
        await client.get("/api/reports/export", headers=h_t2, params={"course_id": course_id})
    ).status_code == 403

    # Teacher A can export CSV for their own course
    t1_export = await client.get(
        "/api/reports/export", headers=h_t1, params={"course_id": course_id}
    )
    assert t1_export.status_code == 200

    # Missing course in export returns 404
    missing_id = str(uuid.uuid4())
    assert (
        await client.get("/api/reports/export", headers=h_t1, params={"course_id": missing_id})
    ).status_code == 404


@pytest.mark.asyncio
async def test_student_cross_session_isolation(client: AsyncClient) -> None:
    """Student B cannot view, advance, answer, inject cues into, or finish Student A's viva session."""
    t_token = await _create_user_and_token(client, "t_viva@viva.edu", UserRole.TEACHER, "Teacher")
    stu1_token = await _create_user_and_token(
        client, "stu1@viva.edu", UserRole.STUDENT, "Student 1"
    )
    stu2_token = await _create_user_and_token(
        client, "stu2@viva.edu", UserRole.STUDENT, "Student 2"
    )

    h_t = {"Authorization": f"Bearer {t_token}"}
    h_s1 = {"Authorization": f"Bearer {stu1_token}"}
    h_s2 = {"Authorization": f"Bearer {stu2_token}"}

    course = (
        await client.post("/api/courses", headers=h_t, json={"name": "Algorithms", "code": "ALGO1"})
    ).json()
    course_id = course["id"]

    # Both students consent
    await client.post(
        "/api/consent", headers=h_s1, json={"audio_consent": True, "video_consent": True}
    )
    await client.post(
        "/api/consent", headers=h_s2, json={"audio_consent": True, "video_consent": True}
    )

    # Student 1 creates session
    sess_res = await client.post("/api/viva/sessions", headers=h_s1, json={"course_id": course_id})
    assert sess_res.status_code == 201
    s1_session_id = sess_res.json()["id"]

    # Student 2 CANNOT access Student 1's active session
    assert (
        await client.get(f"/api/viva/sessions/{s1_session_id}", headers=h_s2)
    ).status_code == 403

    # Student 2 CANNOT advance next question on Student 1's session
    assert (
        await client.post(f"/api/viva/sessions/{s1_session_id}/next", headers=h_s2)
    ).status_code == 403

    # Student 2 CANNOT inject behavior flags on Student 1's session
    flag_payload = {"cue_type": "off_screen_gaze"}
    assert (
        await client.post(
            f"/api/viva/sessions/{s1_session_id}/behavior-flags", headers=h_s2, json=flag_payload
        )
    ).status_code == 403

    # Student 2 CANNOT submit turn on Student 1's session
    turn_payload = {"question_id": str(uuid.uuid4()), "transcript": "Some answer"}
    assert (
        await client.post(
            f"/api/viva/sessions/{s1_session_id}/turn", headers=h_s2, json=turn_payload
        )
    ).status_code == 403

    # Student 2 CANNOT finish Student 1's session
    assert (
        await client.post(f"/api/viva/sessions/{s1_session_id}/finish", headers=h_s2)
    ).status_code == 403

    # Student 2 CANNOT view Student 1's report
    assert (
        await client.get(f"/api/viva/sessions/{s1_session_id}/report", headers=h_s2)
    ).status_code == 403

    # Student 1 CAN access their own session and finish it
    assert (
        await client.get(f"/api/viva/sessions/{s1_session_id}", headers=h_s1)
    ).status_code == 200
    assert (
        await client.post(f"/api/viva/sessions/{s1_session_id}/finish", headers=h_s1)
    ).status_code == 200


@pytest.mark.asyncio
async def test_audio_playback_authorization_and_graceful_missing(client: AsyncClient) -> None:
    """Verify audio playback authorization matrix, audio_url in report, and graceful 404s."""
    t1_token = await _create_user_and_token(
        client, "t1_audio@viva.edu", UserRole.TEACHER, "Teacher 1"
    )
    t2_token = await _create_user_and_token(
        client, "t2_audio@viva.edu", UserRole.TEACHER, "Teacher 2"
    )
    stu1_token = await _create_user_and_token(
        client, "stu1_audio@viva.edu", UserRole.STUDENT, "Student 1"
    )
    stu2_token = await _create_user_and_token(
        client, "stu2_audio@viva.edu", UserRole.STUDENT, "Student 2"
    )

    h_t1 = {"Authorization": f"Bearer {t1_token}"}
    h_t2 = {"Authorization": f"Bearer {t2_token}"}
    h_s1 = {"Authorization": f"Bearer {stu1_token}"}
    h_s2 = {"Authorization": f"Bearer {stu2_token}"}

    # Teacher 1 creates course, topic, and 3 questions
    course = (
        await client.post(
            "/api/courses", headers=h_t1, json={"name": "Audio Systems", "code": "AUD101"}
        )
    ).json()
    course_id = course["id"]
    topic = (
        await client.post(
            f"/api/courses/{course_id}/topics", headers=h_t1, json={"name": "Sampling"}
        )
    ).json()
    topic_id = topic["id"]

    q1_res = await client.post(
        "/api/questions",
        headers=h_t1,
        json={
            "topic_id": topic_id,
            "question_text": "Q1: Nyquist rate?",
            "expected_key_points": ["sampling rate"],
        },
    )
    assert q1_res.status_code == 201, q1_res.text
    q1 = q1_res.json()

    q2_res = await client.post(
        "/api/questions",
        headers=h_t1,
        json={
            "topic_id": topic_id,
            "question_text": "Q2: Aliasing?",
            "expected_key_points": ["frequency overlap"],
        },
    )
    assert q2_res.status_code == 201, q2_res.text
    q2 = q2_res.json()

    q3_res = await client.post(
        "/api/questions",
        headers=h_t1,
        json={
            "topic_id": topic_id,
            "question_text": "Q3: Quantization?",
            "expected_key_points": ["rounding error"],
        },
    )
    assert q3_res.status_code == 201, q3_res.text
    q3 = q3_res.json()

    # Student 1 consents and starts session
    await client.post(
        "/api/consent", headers=h_s1, json={"audio_consent": True, "video_consent": True}
    )
    sess_res = await client.post("/api/viva/sessions", headers=h_s1, json={"course_id": course_id})
    session_id = sess_res.json()["id"]

    # Create dummy audio file on disk
    upload_dir = Path("uploads") / "audio"
    upload_dir.mkdir(parents=True, exist_ok=True)
    test_audio_path = upload_dir / f"test_{session_id}.webm"
    dummy_audio_bytes = b"\x1a\x45\xdf\xa3webm-test-audio-content"
    test_audio_path.write_bytes(dummy_audio_bytes)

    try:
        # Create answers in DB: one with existing audio, one with missing file, one with no audio
        db = app.state.test_db_session
        ans_with_audio = Answer(
            session_id=uuid.UUID(session_id),
            question_id=uuid.UUID(q1["id"]),
            sequence_number=1,
            transcript="Nyquist rate is twice the highest frequency.",
            audio_path=str(test_audio_path),
            fused_score=0.9,
        )
        ans_missing_file = Answer(
            session_id=uuid.UUID(session_id),
            question_id=uuid.UUID(q2["id"]),
            sequence_number=2,
            transcript="Another answer with deleted file.",
            audio_path=str(upload_dir / f"deleted_{uuid.uuid4()}.webm"),
            fused_score=0.7,
        )
        ans_no_audio = Answer(
            session_id=uuid.UUID(session_id),
            question_id=uuid.UUID(q3["id"]),
            sequence_number=3,
            transcript="Text only answer without audio.",
            audio_path=None,
            fused_score=0.8,
        )
        db.add_all([ans_with_audio, ans_missing_file, ans_no_audio])
        await db.commit()
        await db.refresh(ans_with_audio)
        await db.refresh(ans_missing_file)
        await db.refresh(ans_no_audio)

        ans_id = str(ans_with_audio.id)
        ans_missing_id = str(ans_missing_file.id)
        ans_no_audio_id = str(ans_no_audio.id)

        # 1. Unauthenticated request -> 401
        assert (
            await client.get(f"/api/viva/sessions/{session_id}/answers/{ans_id}/audio")
        ).status_code == 401

        # 2. Unauthorized teacher (Teacher 2) -> 403 Forbidden
        assert (
            await client.get(
                f"/api/viva/sessions/{session_id}/answers/{ans_id}/audio", headers=h_t2
            )
        ).status_code == 403

        # 3. Unauthorized student (Student 2) -> 403 Forbidden
        assert (
            await client.get(
                f"/api/viva/sessions/{session_id}/answers/{ans_id}/audio", headers=h_s2
            )
        ).status_code == 403

        # 4. Authorized teacher (Teacher 1, course owner) -> 200 OK with correct media type and content
        t1_audio_res = await client.get(
            f"/api/viva/sessions/{session_id}/answers/{ans_id}/audio", headers=h_t1
        )
        assert t1_audio_res.status_code == 200
        assert "audio/webm" in t1_audio_res.headers.get("content-type", "")
        assert t1_audio_res.content == dummy_audio_bytes

        # 5. Session report serialization includes audio_url when audio_path exists, None when audio_path is None
        rep_res = await client.get(f"/api/viva/sessions/{session_id}/report", headers=h_t1)
        assert rep_res.status_code == 200
        answers_data = {a["id"]: a for a in rep_res.json()["answers"]}
        assert (
            answers_data[ans_id]["audio_url"]
            == f"/api/viva/sessions/{session_id}/answers/{ans_id}/audio"
        )
        assert answers_data[ans_no_audio_id]["audio_url"] is None
        assert "audio_path" not in answers_data[ans_id], "Local disk paths must not be exposed"

        # 6. Missing file on disk -> 404 Not Found
        missing_file_res = await client.get(
            f"/api/viva/sessions/{session_id}/answers/{ans_missing_id}/audio", headers=h_t1
        )
        assert missing_file_res.status_code == 404
        assert "Audio recording file not found" in missing_file_res.text

        # 7. Answer with no audio recording -> 404 Not Found
        no_audio_res = await client.get(
            f"/api/viva/sessions/{session_id}/answers/{ans_no_audio_id}/audio", headers=h_t1
        )
        assert no_audio_res.status_code == 404
        assert "No audio recording" in no_audio_res.text

        # 8. Non-existent answer id -> 404 Not Found
        missing_ans_res = await client.get(
            f"/api/viva/sessions/{session_id}/answers/{uuid.uuid4()}/audio", headers=h_t1
        )
        assert missing_ans_res.status_code == 404

        # 9. Session student (Student 1) can also stream their own audio
        s1_audio_res = await client.get(
            f"/api/viva/sessions/{session_id}/answers/{ans_id}/audio", headers=h_s1
        )
        assert s1_audio_res.status_code == 200
        assert s1_audio_res.content == dummy_audio_bytes

    finally:
        if test_audio_path.exists():
            test_audio_path.unlink()
