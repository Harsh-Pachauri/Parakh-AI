"""Tests for Teacher Dashboard & Class Performance Analytics (P2.8)."""

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient

from app.models.answer import Answer
from app.models.institution import Institution
from app.models.question import Question
from app.models.topic import Topic
from app.models.viva_session import VivaSession, VivaStatus
from tests.test_courses import create_user_and_get_token


@pytest.mark.asyncio
async def test_teacher_analytics_authorization_enforced(client: AsyncClient, db_session) -> None:
    """Only teachers and platform admins can access teacher analytics; students and institution admins are rejected."""
    student_token = await create_user_and_get_token(
        client, "unauth.student@viva.edu", "student", "Unauth Student"
    )

    inst = Institution(name="Auth Inst", code="AUTH_INST", is_active=True)
    db_session.add(inst)
    await db_session.commit()
    await db_session.refresh(inst)

    inst_admin_token = await create_user_and_get_token(
        client, "inst.admin.auth@viva.edu", "institution_admin", "Inst Admin"
    )

    # Student -> 403
    res_student = await client.get(
        "/api/teacher/analytics",
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert res_student.status_code == 403

    # Institution Admin -> 403
    res_inst_admin = await client.get(
        "/api/teacher/analytics",
        headers={"Authorization": f"Bearer {inst_admin_token}"},
    )
    assert res_inst_admin.status_code == 403

    # Teacher sessions endpoint also rejects students
    res_sessions_student = await client.get(
        "/api/teacher/sessions",
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert res_sessions_student.status_code == 403


@pytest.mark.asyncio
async def test_teacher_analytics_empty_when_no_courses(client: AsyncClient) -> None:
    """Teacher with no courses receives safe empty structures."""
    teacher_token = await create_user_and_get_token(
        client, "fresh.teacher@viva.edu", "teacher", "Fresh Teacher"
    )

    res = await client.get(
        "/api/teacher/analytics",
        headers={"Authorization": f"Bearer {teacher_token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["summary"]["total_students"] == 0
    assert data["summary"]["total_sessions"] == 0
    assert data["summary"]["completed_sessions"] == 0
    assert data["summary"]["in_progress_sessions"] == 0
    assert data["summary"]["average_score"] is None
    assert data["summary"]["average_score_percent"] == "—"
    assert data["students"] == []
    assert data["courses"] == []
    assert data["topics"] == []
    assert data["recent_activity"] == []


@pytest.mark.asyncio
async def test_teacher_analytics_cross_teacher_isolation(client: AsyncClient, db_session) -> None:
    """Teachers can only see analytics for their own courses and cannot query other teachers' courses."""
    t1_token = await create_user_and_get_token(client, "t1.iso@viva.edu", "teacher", "Teacher 1")
    t2_token = await create_user_and_get_token(client, "t2.iso@viva.edu", "teacher", "Teacher 2")
    student_token = await create_user_and_get_token(
        client, "stud.iso@viva.edu", "student", "Iso Student"
    )

    # T1 course
    c1_res = await client.post(
        "/api/courses",
        headers={"Authorization": f"Bearer {t1_token}"},
        json={"name": "Data Structures", "code": "CS101", "description": "DS course"},
    )
    c1_id = uuid.UUID(c1_res.json()["id"])

    # T2 course
    c2_res = await client.post(
        "/api/courses",
        headers={"Authorization": f"Bearer {t2_token}"},
        json={"name": "Computer Architecture", "code": "CS102", "description": "Arch course"},
    )
    c2_id = uuid.UUID(c2_res.json()["id"])

    # Get student id
    me_res = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {student_token}"})
    student_id = uuid.UUID(me_res.json()["id"])

    # Session in T1 course
    s1 = VivaSession(
        student_id=student_id,
        course_id=c1_id,
        status=VivaStatus.COMPLETED,
        max_questions=3,
        total_score=0.85,
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
    )
    # Session in T2 course
    s2 = VivaSession(
        student_id=student_id,
        course_id=c2_id,
        status=VivaStatus.COMPLETED,
        max_questions=3,
        total_score=0.95,
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
    )
    db_session.add_all([s1, s2])
    await db_session.commit()

    # T1 analytics should only show C1 session (score 0.85, not 0.95)
    t1_res = await client.get(
        "/api/teacher/analytics", headers={"Authorization": f"Bearer {t1_token}"}
    )
    assert t1_res.status_code == 200
    t1_data = t1_res.json()
    assert t1_data["summary"]["total_sessions"] == 1
    assert t1_data["summary"]["average_score"] == 0.85
    assert len(t1_data["courses"]) == 1
    assert t1_data["courses"][0]["course_id"] == str(c1_id)

    # T1 trying to access C2 analytics -> 403 Forbidden
    t1_c2_res = await client.get(
        f"/api/teacher/analytics?course_id={c2_id}",
        headers={"Authorization": f"Bearer {t1_token}"},
    )
    assert t1_c2_res.status_code == 403

    # T1 trying to access C2 sessions -> 403 Forbidden
    t1_c2_sessions = await client.get(
        f"/api/teacher/sessions?course_id={c2_id}",
        headers={"Authorization": f"Bearer {t1_token}"},
    )
    assert t1_c2_sessions.status_code == 403


@pytest.mark.asyncio
async def test_teacher_analytics_metric_calculations_and_topics(
    client: AsyncClient, db_session
) -> None:
    """Metrics correctly calculate total students, sessions, average scores, student drill-down, and topic attempts."""
    t_token = await create_user_and_get_token(
        client, "metric.teacher@viva.edu", "teacher", "Metric Teacher"
    )
    s1_token = await create_user_and_get_token(
        client, "metric.s1@viva.edu", "student", "Student One"
    )
    s2_token = await create_user_and_get_token(
        client, "metric.s2@viva.edu", "student", "Student Two"
    )

    s1_me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {s1_token}"})
    s2_me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {s2_token}"})
    s1_id = uuid.UUID(s1_me.json()["id"])
    s2_id = uuid.UUID(s2_me.json()["id"])

    # Course + Topic + Question
    c_res = await client.post(
        "/api/courses",
        headers={"Authorization": f"Bearer {t_token}"},
        json={"name": "Software Engineering", "code": "CS303", "description": "SE"},
    )
    c_id = uuid.UUID(c_res.json()["id"])

    topic = Topic(course_id=c_id, name="Design Patterns")
    db_session.add(topic)
    await db_session.commit()
    await db_session.refresh(topic)

    question = Question(
        topic_id=topic.id,
        question_text="Explain Singleton pattern.",
        expected_key_points=["single instance", "global access point"],
    )
    db_session.add(question)
    await db_session.commit()
    await db_session.refresh(question)

    # Student 1: 2 completed sessions (scores 0.80 and 0.90 -> student avg 0.85)
    sess1 = VivaSession(
        student_id=s1_id,
        course_id=c_id,
        status=VivaStatus.COMPLETED,
        max_questions=3,
        total_score=0.80,
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
    )
    sess2 = VivaSession(
        student_id=s1_id,
        course_id=c_id,
        status=VivaStatus.COMPLETED,
        max_questions=3,
        total_score=0.90,
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
    )
    # Student 2: 1 in-progress session (total_score None)
    sess3 = VivaSession(
        student_id=s2_id,
        course_id=c_id,
        status=VivaStatus.IN_PROGRESS,
        max_questions=3,
        total_score=None,
        started_at=datetime.now(UTC),
    )
    db_session.add_all([sess1, sess2, sess3])
    await db_session.commit()
    await db_session.refresh(sess1)

    # Add an answer to sess1 linking to topic
    answer = Answer(
        session_id=sess1.id,
        question_id=question.id,
        sequence_number=1,
        transcript="Singleton ensures only one instance exists.",
        fused_score=0.85,
    )
    db_session.add(answer)
    await db_session.commit()

    res = await client.get("/api/teacher/analytics", headers={"Authorization": f"Bearer {t_token}"})
    assert res.status_code == 200
    data = res.json()

    # Summary
    summary = data["summary"]
    assert summary["total_students"] == 2
    assert summary["total_sessions"] == 3
    assert summary["completed_sessions"] == 2
    assert summary["in_progress_sessions"] == 1
    # Average score: (0.80 + 0.90) / 2 = 0.85 (ignores sess3 which is in_progress/None)
    assert summary["average_score"] == 0.85
    assert summary["average_score_percent"] == "85%"

    # Students list
    students = data["students"]
    assert len(students) == 2
    s1_entry = next(s for s in students if s["student_id"] == str(s1_id))
    assert s1_entry["student_name"] == "Student One"
    assert s1_entry["student_email"] == "metric.s1@viva.edu"
    assert s1_entry["total_sessions"] == 2
    assert s1_entry["completed_sessions"] == 2
    assert s1_entry["average_score"] == 0.85
    assert len(s1_entry["sessions"]) == 2

    s2_entry = next(s for s in students if s["student_id"] == str(s2_id))
    assert s2_entry["total_sessions"] == 1
    assert s2_entry["completed_sessions"] == 0
    assert s2_entry["average_score"] is None
    assert s2_entry["average_score_percent"] == "—"

    # Topics list
    topics = data["topics"]
    assert len(topics) == 1
    assert topics[0]["topic_name"] == "Design Patterns"
    assert topics[0]["attempt_count"] == 1

    # Recent activity
    assert len(data["recent_activity"]) == 3


@pytest.mark.asyncio
async def test_teacher_analytics_filtering_by_course(client: AsyncClient, db_session) -> None:
    """Filtering by course_id limits analytics and metrics strictly to that course."""
    t_token = await create_user_and_get_token(
        client, "filter.t@viva.edu", "teacher", "Filter Teacher"
    )
    s_token = await create_user_and_get_token(
        client, "filter.s@viva.edu", "student", "Filter Student"
    )

    s_me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {s_token}"})
    s_id = uuid.UUID(s_me.json()["id"])

    c1 = await client.post(
        "/api/courses",
        headers={"Authorization": f"Bearer {t_token}"},
        json={"name": "Course A", "code": "CA1", "description": "A"},
    )
    c2 = await client.post(
        "/api/courses",
        headers={"Authorization": f"Bearer {t_token}"},
        json={"name": "Course B", "code": "CB1", "description": "B"},
    )
    c1_id = uuid.UUID(c1.json()["id"])
    c2_id = uuid.UUID(c2.json()["id"])

    sess_a = VivaSession(
        student_id=s_id,
        course_id=c1_id,
        status=VivaStatus.COMPLETED,
        total_score=0.70,
        started_at=datetime.now(UTC),
    )
    sess_b = VivaSession(
        student_id=s_id,
        course_id=c2_id,
        status=VivaStatus.COMPLETED,
        total_score=0.90,
        started_at=datetime.now(UTC),
    )
    db_session.add_all([sess_a, sess_b])
    await db_session.commit()

    # Filter by course A only
    res_a = await client.get(
        f"/api/teacher/analytics?course_id={c1_id}", headers={"Authorization": f"Bearer {t_token}"}
    )
    assert res_a.status_code == 200
    data_a = res_a.json()
    assert data_a["summary"]["total_sessions"] == 1
    assert data_a["summary"]["average_score"] == 0.70
    assert len(data_a["courses"]) == 1
    assert data_a["courses"][0]["course_name"] == "Course A"

    # Filter sessions list by student_id
    res_stud = await client.get(
        f"/api/teacher/sessions?student_id={s_id}", headers={"Authorization": f"Bearer {t_token}"}
    )
    assert res_stud.status_code == 200
    assert len(res_stud.json()) == 2
