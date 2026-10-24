"""Tests for Student Dashboard APIs and viva session listings."""

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient

from app.models.viva_session import VivaSession, VivaStatus
from tests.test_courses import create_user_and_get_token


@pytest.mark.asyncio
async def test_list_sessions_empty_for_new_student(client: AsyncClient) -> None:
    """A new student with no viva attempts receives an empty list."""
    token = await create_user_and_get_token(
        client, "fresh.student@viva.edu", "student", "Fresh Student"
    )

    response = await client.get(
        "/api/viva/sessions",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_list_sessions_includes_course_metadata_and_scores(
    client: AsyncClient, db_session
) -> None:
    """Viva sessions list includes course name, code, total_score, and timestamps."""
    teacher_token = await create_user_and_get_token(
        client, "sd.teacher@viva.edu", "teacher", "Dashboard Teacher"
    )
    student_token = await create_user_and_get_token(
        client, "sd.student@viva.edu", "student", "Dashboard Student"
    )

    course_res = await client.post(
        "/api/courses",
        headers={"Authorization": f"Bearer {teacher_token}"},
        json={"name": "Computer Networks", "code": "CS401", "description": "Network layers"},
    )
    assert course_res.status_code == 201
    course_id = uuid.UUID(course_res.json()["id"])

    # Create a viva session with score directly in db for test verification
    # Find student user id
    me_res = await client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {student_token}"},
    )
    student_id = uuid.UUID(me_res.json()["id"])

    session = VivaSession(
        student_id=student_id,
        course_id=course_id,
        status=VivaStatus.COMPLETED,
        max_questions=3,
        total_score=0.88,
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
    )
    db_session.add(session)
    await db_session.commit()
    await db_session.refresh(session)

    # Call GET /api/viva/sessions
    res = await client.get(
        "/api/viva/sessions",
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 1
    session_data = data[0]
    assert session_data["id"] == str(session.id)
    assert session_data["course_id"] == str(course_id)
    assert session_data["course_name"] == "Computer Networks"
    assert session_data["course_code"] == "CS401"
    assert session_data["status"] == "completed"
    assert session_data["total_score"] == 0.88
    assert session_data["finished_at"] is not None
    assert session_data["created_at"] is not None


@pytest.mark.asyncio
async def test_list_sessions_strict_student_isolation(client: AsyncClient, db_session) -> None:
    """Students cannot see other students' sessions."""
    teacher_token = await create_user_and_get_token(
        client, "sd.iso.teacher@viva.edu", "teacher", "Iso Teacher"
    )
    student_a_token = await create_user_and_get_token(
        client, "student.a@viva.edu", "student", "Student A"
    )
    student_b_token = await create_user_and_get_token(
        client, "student.b@viva.edu", "student", "Student B"
    )

    course_res = await client.post(
        "/api/courses",
        headers={"Authorization": f"Bearer {teacher_token}"},
        json={"name": "Compiler Design", "code": "CS502", "description": "Compilers"},
    )
    course_id = uuid.UUID(course_res.json()["id"])

    user_a_res = await client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {student_a_token}"}
    )
    student_a_id = uuid.UUID(user_a_res.json()["id"])

    session_a = VivaSession(
        student_id=student_a_id,
        course_id=course_id,
        status=VivaStatus.COMPLETED,
        max_questions=5,
        total_score=0.92,
        started_at=datetime.now(UTC),
    )
    db_session.add(session_a)
    await db_session.commit()

    # Student A sees their session
    res_a = await client.get(
        "/api/viva/sessions", headers={"Authorization": f"Bearer {student_a_token}"}
    )
    assert res_a.status_code == 200
    assert len(res_a.json()) == 1
    assert res_a.json()[0]["id"] == str(session_a.id)

    # Student B sees zero sessions
    res_b = await client.get(
        "/api/viva/sessions", headers={"Authorization": f"Bearer {student_b_token}"}
    )
    assert res_b.status_code == 200
    assert len(res_b.json()) == 0
