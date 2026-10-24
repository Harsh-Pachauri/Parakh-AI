"""End-to-End workflow verification test suite for Parakh AI.

Verifies the full lifecycle across:
1. Platform Admin -> Institution creation and admin appointment
2. Institution Admin -> Profile retrieval, teacher registration, duplicate rejection
3. Teacher -> Course creation, syllabus/topic management, session review, and audio playback
4. Student -> Registration, course discovery, viva session, consent, answering, and report
5. Audio playback & error handling
6. Cross-role and cross-institution tenant isolation
7. Database migration integrity
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.main import app
from app.models.institution import Institution
from app.models.question import Question
from app.models.user import User, UserRole


async def _create_user_and_token(client: AsyncClient, email: str, role: UserRole, name: str) -> str:
    """Helper to create a user with a specific role and return an access token."""
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
async def test_e2e_complete_parakh_ai_lifecycle(
    client: AsyncClient, db_session, monkeypatch
) -> None:
    """Full end-to-end multi-role verification covering P2.5 workflows."""

    # =========================================================================
    # WORKFLOW 1: Platform Admin creates an institution and appoints an admin
    # =========================================================================
    plat_admin_token = await _create_user_and_token(
        client, "e2e_plat_admin@viva.edu", UserRole.ADMIN, "Platform Administrator"
    )
    h_plat = {"Authorization": f"Bearer {plat_admin_token}"}

    # 1.1 List institutions initially
    inst_list_res0 = await client.get("/api/admin/institutions", headers=h_plat)
    assert inst_list_res0.status_code == 200

    # 1.2 Create Institution A (Apex University)
    inst_a_res = await client.post(
        "/api/admin/institutions",
        headers=h_plat,
        json={"name": "Apex Engineering University", "code": "AEU"},
    )
    assert inst_a_res.status_code == 201
    inst_a = inst_a_res.json()
    assert inst_a["name"] == "Apex Engineering University"
    assert inst_a["code"] == "AEU"
    assert inst_a["is_active"] is True
    inst_a_id = inst_a["id"]

    # 1.3 Duplicate institution code or name rejected
    dup_res = await client.post(
        "/api/admin/institutions",
        headers=h_plat,
        json={"name": "Another Name", "code": "AEU"},
    )
    assert dup_res.status_code == 409

    # 1.4 Appoint Institution Admin for Apex University
    appoint_res = await client.post(
        f"/api/admin/institutions/{inst_a_id}/admins",
        headers=h_plat,
        json={
            "email": "dean.apex@aeu.edu",
            "password": "deanPassword123",
            "full_name": "Dean Robert Apex",
        },
    )
    assert appoint_res.status_code == 201
    admin_a = appoint_res.json()
    assert admin_a["email"] == "dean.apex@aeu.edu"
    assert admin_a["role"] == "institution_admin"
    assert admin_a["institution_id"] == inst_a_id

    # Duplicate admin email rejected
    dup_admin_res = await client.post(
        f"/api/admin/institutions/{inst_a_id}/admins",
        headers=h_plat,
        json={
            "email": "dean.apex@aeu.edu",
            "password": "differentPassword123",
            "full_name": "Dean Copy",
        },
    )
    assert dup_admin_res.status_code == 409

    # =========================================================================
    # WORKFLOW 2: Institution Admin logs in, views profile, registers teachers
    # =========================================================================
    login_admin_res = await client.post(
        "/api/auth/login",
        json={"email": "dean.apex@aeu.edu", "password": "deanPassword123"},
    )
    assert login_admin_res.status_code == 200
    inst_admin_token = login_admin_res.json()["access_token"]
    h_inst_admin = {"Authorization": f"Bearer {inst_admin_token}"}

    # 2.1 View own institution profile
    profile_res = await client.get("/api/institution/profile", headers=h_inst_admin)
    assert profile_res.status_code == 200
    profile_data = profile_res.json()
    assert profile_data["id"] == inst_a_id
    assert profile_data["name"] == "Apex Engineering University"
    assert profile_data["code"] == "AEU"

    # 2.2 Register Teacher 1 (Alan Turing)
    t1_res = await client.post(
        "/api/institution/teachers",
        headers=h_inst_admin,
        json={
            "email": "alan.turing@aeu.edu",
            "password": "turingPassword123",
            "full_name": "Prof. Alan Turing",
        },
    )
    assert t1_res.status_code == 201
    t1_data = t1_res.json()
    assert t1_data["role"] == "teacher"
    assert t1_data["institution_id"] == inst_a_id

    # 2.3 Register Teacher 2 (Ada Lovelace)
    t2_res = await client.post(
        "/api/institution/teachers",
        headers=h_inst_admin,
        json={
            "email": "ada.lovelace@aeu.edu",
            "password": "adaPassword123",
            "full_name": "Prof. Ada Lovelace",
        },
    )
    assert t2_res.status_code == 201

    # 2.4 Duplicate teacher email rejected
    t_dup_res = await client.post(
        "/api/institution/teachers",
        headers=h_inst_admin,
        json={
            "email": "alan.turing@aeu.edu",
            "password": "newPassword123",
            "full_name": "Alan Imposter",
        },
    )
    assert t_dup_res.status_code == 409

    # 2.5 List teachers strictly within Apex University
    teachers_list_res = await client.get("/api/institution/teachers", headers=h_inst_admin)
    assert teachers_list_res.status_code == 200
    t_list = teachers_list_res.json()
    assert len(t_list) >= 2
    emails = [t["email"] for t in t_list]
    assert "alan.turing@aeu.edu" in emails
    assert "ada.lovelace@aeu.edu" in emails

    # =========================================================================
    # WORKFLOW 3: Registered Teacher logs in and creates/manages courses
    # =========================================================================
    login_t1_res = await client.post(
        "/api/auth/login",
        json={"email": "alan.turing@aeu.edu", "password": "turingPassword123"},
    )
    assert login_t1_res.status_code == 200
    t1_token = login_t1_res.json()["access_token"]
    h_t1 = {"Authorization": f"Bearer {t1_token}"}

    # Verify teacher profile reflects institution
    t1_me = await client.get("/api/auth/me", headers=h_t1)
    assert t1_me.status_code == 200
    assert t1_me.json()["role"] == "teacher"
    assert t1_me.json()["institution_id"] == inst_a_id

    # Create Course
    course_res = await client.post(
        "/api/courses",
        headers=h_t1,
        json={
            "name": "Theory of Computation",
            "code": "CS401",
            "description": "Turing machines and automata theory",
            "syllabus_text": "Turing machines, halting problem, complexity classes P and NP.",
        },
    )
    assert course_res.status_code == 201
    course_id = course_res.json()["id"]

    # Create Topic
    topic_res = await client.post(
        f"/api/courses/{course_id}/topics",
        headers=h_t1,
        json={"name": "Turing Machines", "sort_order": 1},
    )
    assert topic_res.status_code == 201
    topic_id = topic_res.json()["id"]

    # Upload Syllabus Document to topic
    doc_res = await client.post(
        f"/api/topics/{topic_id}/documents",
        headers=h_t1,
        files={
            "file": (
                "turing_machines.txt",
                b"A Turing machine is a mathematical model of computation defining an abstract machine.",
                "text/plain",
            )
        },
    )
    assert doc_res.status_code == 201

    # Create Question in topic
    question = Question(
        topic_id=uuid.UUID(topic_id),
        question_text="Describe how a Turing machine transitions between states.",
        expected_key_points=["tape symbol", "current state", "head movement", "write symbol"],
    )
    db_session.add(question)
    await db_session.commit()
    await db_session.refresh(question)

    # =========================================================================
    # WORKFLOW 4: Student registers, logs in, discovers courses, grants consent
    # =========================================================================
    student_res = await client.post(
        "/api/auth/register",
        json={
            "email": "student.e2e@viva.edu",
            "password": "studentPassword123",
            "full_name": "Student Scholar",
            "role": "student",
        },
    )
    assert student_res.status_code == 201
    student_token = student_res.json()["access_token"]
    h_student = {"Authorization": f"Bearer {student_token}"}

    # Discover courses
    courses_res = await client.get("/api/courses", headers=h_student)
    assert courses_res.status_code == 200
    assert any(c["id"] == course_id for c in courses_res.json())

    # =========================================================================
    # WORKFLOW 5: Viva session, speech answer, transcription, scoring, and review
    # =========================================================================
    # Set up LLM, speech transcription, and evaluation mocks
    class LocalJudge:
        async def generate(self, prompt: str, schema: dict | None = None):
            return {
                "question": "How does non-determinism affect a Turing machine's power?",
                "key_points": ["decidability is identical", "computational complexity changes"],
                "difficulty": "medium",
            }

    monkeypatch.setattr("app.services.llm_service.get_provider", lambda: LocalJudge())
    monkeypatch.setattr("app.services.viva_orchestrator.get_provider", lambda: LocalJudge())

    async def mock_evaluate(**kwargs):
        return {
            "embedding_score": 0.85,
            "llm_score": 0.90,
            "fused_score": 0.88,
            "rubric": {"correctness": 9, "completeness": 8, "clarity": 9},
        }

    monkeypatch.setattr("app.api.viva.evaluate_answer", mock_evaluate)
    monkeypatch.setattr(
        "app.api.viva.SpeechService.transcribe",
        lambda self, path: {
            "text": "The transition function maps the current state and tape symbol to a new state, write symbol, and head direction.",
            "confidence": 0.95,
            "segments": [],
            "duration_ms": 1200,
        },
    )

    # Start viva session
    session_res = await client.post(
        "/api/viva/sessions",
        headers=h_student,
        json={"course_id": course_id},
    )
    assert session_res.status_code == 201
    session_id = session_res.json()["id"]

    # Record consent
    consent_res = await client.post(
        "/api/consent",
        headers=h_student,
        json={
            "session_id": session_id,
            "audio_retention_consent": True,
            "transcript_consent": True,
            "camera_analysis_consent": True,
        },
    )
    assert consent_res.status_code == 201

    # Submit audio answer
    answer_res = await client.post(
        f"/api/viva/sessions/{session_id}/answer",
        headers=h_student,
        files={"file": ("speech.webm", b"RIFFfake-audio-payload", "audio/webm")},
        data={"question_id": str(question.id)},
    )
    assert answer_res.status_code == 200
    answer_data = answer_res.json()
    assert answer_data["audio_saved"] is True
    assert "transcript" in answer_data
    assert "transition function" in answer_data["transcript"].lower()

    # Log behavioral cue (e.g. looking away)
    cue_res = await client.post(
        f"/api/viva/sessions/{session_id}/behavior-flags",
        headers=h_student,
        json={"cue_type": "off_screen_gaze"},
    )
    assert cue_res.status_code == 201

    # Request next question
    next_q_res = await client.post(
        f"/api/viva/sessions/{session_id}/next",
        headers=h_student,
    )
    assert next_q_res.status_code == 200

    # Finish session
    finish_res = await client.post(
        f"/api/viva/sessions/{session_id}/finish",
        headers=h_student,
    )
    assert finish_res.status_code == 200
    assert finish_res.json()["status"] == "completed"

    # Student retrieves feedback report
    report_res = await client.get(
        f"/api/viva/sessions/{session_id}/report",
        headers=h_student,
    )
    assert report_res.status_code == 200
    report_data = report_res.json()
    assert report_data["status"] == "completed"
    assert len(report_data["answers"]) >= 1
    recorded_ans_id = report_data["answers"][0]["id"]

    # =========================================================================
    # WORKFLOW 6: Teacher review & authenticated audio playback
    # =========================================================================
    # Teacher who owns course views session in teacher sessions
    t1_sessions_res = await client.get("/api/teacher/sessions", headers=h_t1)
    assert t1_sessions_res.status_code == 200
    session_ids = [s["id"] for s in t1_sessions_res.json()]
    assert session_id in session_ids

    # Teacher accesses student audio file
    t1_audio_res = await client.get(
        f"/api/viva/sessions/{session_id}/answers/{recorded_ans_id}/audio",
        headers=h_t1,
    )
    assert t1_audio_res.status_code == 200
    assert t1_audio_res.content == b"RIFFfake-audio-payload"

    # Missing audio file returns 404 gracefully
    missing_audio_res = await client.get(
        f"/api/viva/sessions/{session_id}/answers/{uuid.uuid4()}/audio",
        headers=h_t1,
    )
    assert missing_audio_res.status_code == 404

    # =========================================================================
    # WORKFLOW 7: Cross-institution & cross-role security isolation
    # =========================================================================
    # 7.1 Create Institution B
    inst_b_res = await client.post(
        "/api/admin/institutions",
        headers=h_plat,
        json={"name": "Beta Institute of Science", "code": "BIS"},
    )
    inst_b_id = inst_b_res.json()["id"]

    await client.post(
        f"/api/admin/institutions/{inst_b_id}/admins",
        headers=h_plat,
        json={
            "email": "dean.beta@bis.edu",
            "password": "betaPassword123",
            "full_name": "Dean Beta",
        },
    )
    token_b = (
        await client.post(
            "/api/auth/login",
            json={"email": "dean.beta@bis.edu", "password": "betaPassword123"},
        )
    ).json()["access_token"]
    h_admin_b = {"Authorization": f"Bearer {token_b}"}

    # 7.2 Dean Beta's profile must strictly be Beta Institute, NOT Apex
    prof_b_res = await client.get("/api/institution/profile", headers=h_admin_b)
    assert prof_b_res.json()["id"] == inst_b_id
    assert prof_b_res.json()["code"] == "BIS"

    # 7.3 Dean Beta cannot see Apex University's teachers
    t_b_list = (await client.get("/api/institution/teachers", headers=h_admin_b)).json()
    b_emails = [t["email"] for t in t_b_list]
    assert "alan.turing@aeu.edu" not in b_emails
    assert "ada.lovelace@aeu.edu" not in b_emails

    # 7.4 Cross-role route protections (all non-admins forbidden from platform admin)
    assert (
        await client.post("/api/admin/institutions", headers=h_t1, json={"name": "X", "code": "X"})
    ).status_code == 403
    assert (await client.get("/api/admin/institutions", headers=h_t1)).status_code == 403
    assert (await client.get("/api/admin/institutions", headers=h_student)).status_code == 403
    assert (await client.get("/api/admin/institutions", headers=h_inst_admin)).status_code == 403
    assert (await client.get("/api/admin/institutions")).status_code == 401

    # 7.5 Teacher and Student cannot access institution profile or create teachers
    assert (await client.get("/api/institution/profile", headers=h_t1)).status_code == 403
    assert (await client.get("/api/institution/profile", headers=h_student)).status_code == 403
    assert (
        await client.post(
            "/api/institution/teachers",
            headers=h_t1,
            json={"email": "hack@aeu.edu", "password": "password123", "full_name": "Hack"},
        )
    ).status_code == 403

    # 7.6 Teacher from another course cannot access audio from this course
    t_other_token = await _create_user_and_token(
        client, "t_unrelated@viva.edu", UserRole.TEACHER, "Unrelated Teacher"
    )
    assert (
        await client.get(
            f"/api/viva/sessions/{session_id}/answers/{recorded_ans_id}/audio",
            headers={"Authorization": f"Bearer {t_other_token}"},
        )
    ).status_code == 403

    # 7.7 Deactivated institution rejects teacher creation
    inst_a_row = await db_session.get(Institution, uuid.UUID(inst_a_id))
    inst_a_row.is_active = False
    await db_session.commit()

    deactivated_res = await client.post(
        "/api/institution/teachers",
        headers=h_inst_admin,
        json={
            "email": "prof.late@aeu.edu",
            "password": "latePassword123",
            "full_name": "Late Prof",
        },
    )
    assert deactivated_res.status_code == 403
    assert "inactive" in deactivated_res.json()["detail"].lower()

    # Restore active status
    inst_a_row.is_active = True
    await db_session.commit()


def test_alembic_migrations_head_intact() -> None:
    """Alembic migrations must have a single linear head with no branches."""
    import pathlib

    from alembic.config import Config
    from alembic.script import ScriptDirectory

    ini_path = (
        "backend/alembic.ini" if pathlib.Path("backend/alembic.ini").exists() else "alembic.ini"
    )
    alembic_cfg = Config(ini_path)
    script = ScriptDirectory.from_config(alembic_cfg)
    heads = script.get_heads()
    assert len(heads) == 1
    assert heads[0] in ("c74d82f19a0e", "e41a9d8f3b20", "d73e91b5c2a1")
