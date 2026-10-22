"""Tests for course and topic CRUD and role-based access control."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.main import app
from app.models.user import User, UserRole


async def create_user_and_get_token(client: AsyncClient, email: str, role: str, name: str) -> str:
    """Helper to register a user and return access token."""
    response = await client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "password1234",
            "full_name": name,
            "role": "student",
        },
    )
    assert response.status_code == 201
    if role == "teacher":
        database = app.state.test_db_session
        account = (await database.execute(select(User).where(User.email == email))).scalar_one()
        account.role = UserRole.TEACHER
        await database.commit()
    return response.json()["access_token"]


@pytest.mark.asyncio
async def test_teacher_create_course_success(client: AsyncClient) -> None:
    """Teacher can successfully create a new course."""
    token = await create_user_and_get_token(client, "prof1@viva.edu", "teacher", "Professor Alpha")
    response = await client.post(
        "/api/courses",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Operating Systems",
            "code": "CS301",
            "description": "Processes, threads, and memory management",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Operating Systems"
    assert data["code"] == "CS301"
    assert "id" in data


@pytest.mark.asyncio
async def test_student_create_course_forbidden(client: AsyncClient) -> None:
    """Students are not permitted to create courses (403 Forbidden)."""
    student_token = await create_user_and_get_token(
        client, "stu1@viva.edu", "student", "Student One"
    )
    response = await client.post(
        "/api/courses",
        headers={"Authorization": f"Bearer {student_token}"},
        json={"name": "Hacking Course", "code": "HACK101"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_duplicate_course_code_returns_409(client: AsyncClient) -> None:
    """Duplicate course code fails with 409 Conflict."""
    token = await create_user_and_get_token(client, "prof2@viva.edu", "teacher", "Professor Beta")
    r1 = await client.post(
        "/api/courses",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Database Systems", "code": "CS401"},
    )
    assert r1.status_code == 201

    r2 = await client.post(
        "/api/courses",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Advanced Databases", "code": "CS401"},
    )
    assert r2.status_code == 409


@pytest.mark.asyncio
async def test_list_and_get_courses(client: AsyncClient) -> None:
    """Verify listing and fetching specific course details."""
    teacher_token = await create_user_and_get_token(
        client, "prof3@viva.edu", "teacher", "Professor Gamma"
    )
    student_token = await create_user_and_get_token(
        client, "stu2@viva.edu", "student", "Student Two"
    )

    create_res = await client.post(
        "/api/courses",
        headers={"Authorization": f"Bearer {teacher_token}"},
        json={"name": "Computer Networks", "code": "CS501"},
    )
    course_id = create_res.json()["id"]

    # Student lists all courses
    list_res = await client.get(
        "/api/courses",
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert list_res.status_code == 200
    courses = list_res.json()
    assert any(c["id"] == course_id for c in courses)

    # Get single course
    get_res = await client.get(
        f"/api/courses/{course_id}",
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert get_res.status_code == 200
    assert get_res.json()["code"] == "CS501"


@pytest.mark.asyncio
async def test_update_and_delete_course(client: AsyncClient) -> None:
    """Course creator can update and delete their course; other teachers cannot."""
    teacher1_token = await create_user_and_get_token(
        client, "prof4@viva.edu", "teacher", "Professor Delta"
    )
    teacher2_token = await create_user_and_get_token(
        client, "prof5@viva.edu", "teacher", "Professor Epsilon"
    )

    create_res = await client.post(
        "/api/courses",
        headers={"Authorization": f"Bearer {teacher1_token}"},
        json={"name": "Compiler Design", "code": "CS601"},
    )
    course_id = create_res.json()["id"]

    # Teacher 2 cannot update Teacher 1's course
    unauth_update = await client.put(
        f"/api/courses/{course_id}",
        headers={"Authorization": f"Bearer {teacher2_token}"},
        json={"name": "Hijacked Course"},
    )
    assert unauth_update.status_code == 403

    # Teacher 1 can update
    auth_update = await client.put(
        f"/api/courses/{course_id}",
        headers={"Authorization": f"Bearer {teacher1_token}"},
        json={"name": "Advanced Compiler Design"},
    )
    assert auth_update.status_code == 200
    assert auth_update.json()["name"] == "Advanced Compiler Design"

    # Teacher 1 can delete
    del_res = await client.delete(
        f"/api/courses/{course_id}",
        headers={"Authorization": f"Bearer {teacher1_token}"},
    )
    assert del_res.status_code == 204

    # Verification of deletion
    get_res = await client.get(
        f"/api/courses/{course_id}",
        headers={"Authorization": f"Bearer {teacher1_token}"},
    )
    assert get_res.status_code == 404


@pytest.mark.asyncio
async def test_topic_crud(client: AsyncClient) -> None:
    """Topic creation, listing, updating, and deletion within a course."""
    teacher_token = await create_user_and_get_token(
        client, "prof6@viva.edu", "teacher", "Professor Zeta"
    )
    course_res = await client.post(
        "/api/courses",
        headers={"Authorization": f"Bearer {teacher_token}"},
        json={"name": "Software Engineering", "code": "CS701"},
    )
    course_id = course_res.json()["id"]

    # 1. Add topic
    topic_res = await client.post(
        f"/api/courses/{course_id}/topics",
        headers={"Authorization": f"Bearer {teacher_token}"},
        json={"name": "Agile Methodology", "sort_order": 1},
    )
    assert topic_res.status_code == 201
    topic_id = topic_res.json()["id"]
    assert topic_res.json()["name"] == "Agile Methodology"

    # 2. List topics
    list_res = await client.get(
        f"/api/courses/{course_id}/topics",
        headers={"Authorization": f"Bearer {teacher_token}"},
    )
    assert list_res.status_code == 200
    assert len(list_res.json()) >= 1

    # 3. Update topic
    update_res = await client.put(
        f"/api/topics/{topic_id}",
        headers={"Authorization": f"Bearer {teacher_token}"},
        json={"name": "Scrum & Kanban", "sort_order": 2},
    )
    assert update_res.status_code == 200
    assert update_res.json()["name"] == "Scrum & Kanban"

    # 4. Delete topic
    del_res = await client.delete(
        f"/api/topics/{topic_id}",
        headers={"Authorization": f"Bearer {teacher_token}"},
    )
    assert del_res.status_code == 204


@pytest.mark.asyncio
async def test_saved_syllabus_analysis_and_interview_configuration(client, monkeypatch):
    token = await create_user_and_get_token(
        client, "syllabus.teacher@example.com", "teacher", "Syllabus Teacher"
    )
    headers = {"Authorization": "Bearer " + token}
    original_syllabus = "Foundations of databases.\n" + ("Normalization and indexing. " * 400)
    created = await client.post(
        "/api/courses",
        headers=headers,
        json={
            "name": "Database Systems",
            "subject": "DBMS",
            "code": "DB401",
            "academic_level": "Undergraduate",
            "syllabus_text": original_syllabus,
        },
    )
    assert created.status_code == 201, created.text
    course_id = created.json()["id"]

    class SyllabusProvider:
        async def generate(self, prompt: str, schema: dict | None = None):
            assert "Source section" in prompt
            return {
                "modules": [
                    {
                        "name": "Database Foundations",
                        "topics": [
                            {
                                "name": "Normalization",
                                "subtopics": ["normal forms"],
                                "key_concepts": ["functional dependencies"],
                                "learning_objectives": ["identify update anomalies"],
                                "prerequisites": ["relational model"],
                                "question_types": ["conceptual"],
                            }
                        ],
                    }
                ]
            }

    monkeypatch.setattr("app.api.courses.get_provider", lambda: SyllabusProvider())
    analyzed = await client.post(f"/api/courses/{course_id}/syllabus/analyze", headers=headers)
    assert analyzed.status_code == 200, analyzed.text
    result = analyzed.json()
    assert result["syllabus_text"] == original_syllabus
    assert result["syllabus_analysis"]["source_length"] == len(original_syllabus)
    topic = result["topics"][0]
    assert topic["name"] == "Normalization"
    source_references = result["syllabus_analysis"]["modules"][0]["topics"][0]["source_references"]
    assert len(source_references) >= 2
    renamed = await client.put(
        f"/api/courses/{course_id}/syllabus/topics/{topic['id']}",
        headers=headers,
        json={"name": "Normalization fundamentals"},
    )
    assert renamed.status_code == 200, renamed.text
    assert (
        renamed.json()["syllabus_analysis"]["modules"][0]["topics"][0]["name"]
        == "Normalization fundamentals"
    )

    updated = await client.put(
        f"/api/courses/{course_id}",
        headers=headers,
        json={
            "interview_config": {
                "max_questions": 7,
                "max_duration_sec": 1200,
                "difficulty": "hard",
                "topic_ids": [topic["id"]],
            }
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["interview_config"]["max_questions"] == 7
    reopened = await client.get(f"/api/courses/{course_id}", headers=headers)
    assert reopened.json()["syllabus_text"] == original_syllabus
    assert reopened.json()["interview_config"]["difficulty"] == "hard"
