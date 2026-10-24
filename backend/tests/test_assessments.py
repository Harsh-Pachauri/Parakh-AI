"""Comprehensive tests for Question Bank CSV Import & Custom Viva Builder (P2.10)."""

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient

from app.models.viva_session import VivaSession, VivaStatus
from tests.test_courses import create_user_and_get_token


@pytest.mark.asyncio
async def test_csv_template_and_bulk_import(client: AsyncClient, db_session) -> None:
    """Teachers can download the CSV template and bulk import questions for their courses."""
    t_token = await create_user_and_get_token(client, "t.csv@viva.edu", "teacher", "CSV Teacher")
    headers = {"Authorization": f"Bearer {t_token}"}

    # 1. Download template
    tmpl_res = await client.get("/api/questions/csv-template", headers=headers)
    assert tmpl_res.status_code == 200
    assert "question_text" in tmpl_res.text
    assert "expected_key_points" in tmpl_res.text

    # 2. Setup Course & Topics
    course_res = await client.post(
        "/api/courses",
        headers=headers,
        json={"name": "Operating Systems", "code": "OS101", "description": "OS course"},
    )
    course_id = course_res.json()["id"]

    topic1_res = await client.post(
        f"/api/courses/{course_id}/topics",
        headers=headers,
        json={"name": "Process Management", "sort_order": 1},
    )
    t1_id = topic1_res.json()["id"]

    await client.post(
        f"/api/courses/{course_id}/topics",
        headers=headers,
        json={"name": "Memory Management", "sort_order": 2},
    )

    # 3. Valid CSV import by topic name and topic ID
    csv_payload = (
        "question_text,expected_key_points,difficulty,question_type,explanation,topic_name\n"
        '"What is a process control block (PCB)?","Process state;Program counter;CPU registers;Scheduling info",easy,conceptual,"PCB stores process context for context switching.","Process Management"\n'
        f'"Explain thrashing and working set model.","Excessive paging;CPU utilization drops;Page fault frequency",hard,analytical,"Thrashing happens when processes do not have enough frames.","{t1_id}"\n'
        '"","Missing text point 1",medium,conceptual,"",Process Management\n'
        '"Valid question with missing points but has explanation.","",medium,conceptual,"Explanation used as fallback key point.","Memory Management"\n'
    )

    import_res = await client.post(
        "/api/questions/import-csv",
        headers=headers,
        data={"csv_text": csv_payload, "course_id": course_id},
    )
    assert import_res.status_code == 200
    data = import_res.json()
    assert data["imported_count"] == 3  # Rows 1, 2, 4 are valid; row 3 had no text
    assert data["failed_count"] == 1
    assert any("Question text is required" in err for err in data["errors"])

    # 4. Verify questions exist in question bank
    bank_res = await client.get(
        "/api/questions",
        headers=headers,
        params={"course_id": course_id},
    )
    assert bank_res.status_code == 200
    assert bank_res.json()["total"] == 3


@pytest.mark.asyncio
async def test_assessment_crud_and_publishing_lifecycle(client: AsyncClient, db_session) -> None:
    """Teacher can create draft assessments, edit settings, lock questions, and toggle publishing."""
    t_token = await create_user_and_get_token(
        client, "t.assess@viva.edu", "teacher", "Assessment Teacher"
    )
    headers = {"Authorization": f"Bearer {t_token}"}

    # Setup course & questions
    c_res = await client.post(
        "/api/courses",
        headers=headers,
        json={"name": "Computer Architecture", "code": "CA202"},
    )
    course_id = c_res.json()["id"]

    t_res = await client.post(
        f"/api/courses/{course_id}/topics",
        headers=headers,
        json={"name": "Pipelining"},
    )
    topic_id = t_res.json()["id"]

    q1_res = await client.post(
        "/api/questions",
        headers=headers,
        json={
            "topic_id": topic_id,
            "question_text": "Explain pipeline hazards.",
            "expected_key_points": ["structural hazard", "data hazard", "control hazard"],
            "difficulty": "medium",
        },
    )
    q1_id = q1_res.json()["id"]

    q2_res = await client.post(
        "/api/questions",
        headers=headers,
        json={
            "topic_id": topic_id,
            "question_text": "What is branch prediction?",
            "expected_key_points": ["speculative execution", "branch target buffer"],
            "difficulty": "hard",
        },
    )
    q2_id = q2_res.json()["id"]

    # 1. Create Assessment (Draft by default)
    create_res = await client.post(
        "/api/assessments",
        headers=headers,
        json={
            "course_id": course_id,
            "title": "Midterm Oral Exam",
            "description": "Oral exam on pipelining and architecture",
            "instructions": "Speak clearly and state key hardware mechanisms.",
            "duration_minutes": 20,
            "max_questions": 2,
            "difficulty": "medium",
            "is_published": False,
            "topic_ids": [topic_id],
            "question_ids": [q1_id, q2_id],
        },
    )
    assert create_res.status_code == 201
    assessment = create_res.json()
    assert assessment["title"] == "Midterm Oral Exam"
    assert assessment["is_published"] is False
    assert assessment["question_count"] == 2
    assert assessment["course_name"] == "Computer Architecture"
    assessment_id = assessment["id"]

    # 2. List Teacher Assessments
    list_res = await client.get("/api/assessments", headers=headers)
    assert list_res.status_code == 200
    assert len(list_res.json()) == 1
    assert list_res.json()[0]["id"] == assessment_id

    # 3. Update Assessment
    update_res = await client.put(
        f"/api/assessments/{assessment_id}",
        headers=headers,
        json={
            "title": "Final Oral Exam — Computer Architecture",
            "duration_minutes": 25,
        },
    )
    assert update_res.status_code == 200
    assert update_res.json()["title"] == "Final Oral Exam — Computer Architecture"
    assert update_res.json()["duration_minutes"] == 25

    # 4. Toggle Publish
    pub_res = await client.post(
        f"/api/assessments/{assessment_id}/publish?published=true",
        headers=headers,
    )
    assert pub_res.status_code == 200
    assert pub_res.json()["is_published"] is True

    # 5. Fetch Assessment with Questions
    get_res = await client.get(f"/api/assessments/{assessment_id}", headers=headers)
    assert get_res.status_code == 200
    get_data = get_res.json()
    assert len(get_data["questions"]) == 2
    assert get_data["questions"][0]["id"] == q1_id
    assert get_data["questions"][1]["id"] == q2_id


@pytest.mark.asyncio
async def test_assessment_ownership_and_cross_teacher_isolation(
    client: AsyncClient, db_session
) -> None:
    """Teachers cannot modify or delete assessments belonging to other teachers."""
    t1_token = await create_user_and_get_token(client, "t1.iso.assess@viva.edu", "teacher", "T1")
    t2_token = await create_user_and_get_token(client, "t2.iso.assess@viva.edu", "teacher", "T2")
    h1 = {"Authorization": f"Bearer {t1_token}"}
    h2 = {"Authorization": f"Bearer {t2_token}"}

    # T1 creates course and assessment
    c1 = (await client.post("/api/courses", headers=h1, json={"name": "C1", "code": "C1"})).json()
    a1 = (
        await client.post(
            "/api/assessments",
            headers=h1,
            json={"course_id": c1["id"], "title": "T1 Assessment"},
        )
    ).json()

    # T2 attempts to update T1's assessment -> 403
    t2_update = await client.put(
        f"/api/assessments/{a1['id']}",
        headers=h2,
        json={"title": "Hacked Title"},
    )
    assert t2_update.status_code == 403

    # T2 attempts to publish T1's assessment -> 403
    t2_pub = await client.post(
        f"/api/assessments/{a1['id']}/publish",
        headers=h2,
    )
    assert t2_pub.status_code == 403

    # T2 attempts to delete T1's assessment -> 403
    t2_del = await client.delete(
        f"/api/assessments/{a1['id']}",
        headers=h2,
    )
    assert t2_del.status_code == 403

    # T2 listing only shows T2's assessments
    t2_list = await client.get("/api/assessments", headers=h2)
    assert t2_list.status_code == 200
    assert t2_list.json() == []


@pytest.mark.asyncio
async def test_student_cannot_access_unpublished_assessment(
    client: AsyncClient, db_session
) -> None:
    """Students cannot access or start unpublished draft assessments."""
    t_token = await create_user_and_get_token(client, "t.draft@viva.edu", "teacher", "T Draft")
    s_token = await create_user_and_get_token(client, "s.draft@viva.edu", "student", "S Draft")
    h_teacher = {"Authorization": f"Bearer {t_token}"}
    h_student = {"Authorization": f"Bearer {s_token}"}

    c = (
        await client.post(
            "/api/courses", headers=h_teacher, json={"name": "Math", "code": "MTH101"}
        )
    ).json()
    # Unpublished assessment
    draft_assess = (
        await client.post(
            "/api/assessments",
            headers=h_teacher,
            json={"course_id": c["id"], "title": "Unpublished Midterm", "is_published": False},
        )
    ).json()

    # Student cannot get details -> 403 Forbidden
    s_get = await client.get(f"/api/assessments/{draft_assess['id']}", headers=h_student)
    assert s_get.status_code == 403

    # Student cannot start viva session with unpublished assessment -> 403 Forbidden
    s_start = await client.post(
        "/api/viva/sessions",
        headers=h_student,
        json={"assessment_id": draft_assess["id"]},
    )
    assert s_start.status_code == 403

    # Student does not see unpublished assessments in /api/student/assessments
    s_list = await client.get("/api/student/assessments", headers=h_student)
    assert s_list.status_code == 200
    assert not any(item["id"] == draft_assess["id"] for item in s_list.json())


@pytest.mark.asyncio
async def test_student_launches_published_custom_viva_assessment(
    client: AsyncClient, db_session
) -> None:
    """Student can view published assessment and start viva with pre-locked custom questions."""
    t_token = await create_user_and_get_token(client, "t.pub@viva.edu", "teacher", "T Pub")
    s_token = await create_user_and_get_token(client, "s.pub@viva.edu", "student", "S Pub")
    h_teacher = {"Authorization": f"Bearer {t_token}"}
    h_student = {"Authorization": f"Bearer {s_token}"}

    course = (
        await client.post(
            "/api/courses", headers=h_teacher, json={"name": "Security", "code": "SEC401"}
        )
    ).json()
    topic = (
        await client.post(
            f"/api/courses/{course['id']}/topics", headers=h_teacher, json={"name": "Cryptography"}
        )
    ).json()

    # Create 2 custom questions
    q1 = (
        await client.post(
            "/api/questions",
            headers=h_teacher,
            json={
                "topic_id": topic["id"],
                "question_text": "Differentiate symmetric and asymmetric encryption.",
                "expected_key_points": ["single key vs key pair", "performance vs key exchange"],
                "difficulty": "medium",
            },
        )
    ).json()

    q2 = (
        await client.post(
            "/api/questions",
            headers=h_teacher,
            json={
                "topic_id": topic["id"],
                "question_text": "What is a digital signature and how does it guarantee non-repudiation?",
                "expected_key_points": ["hash signing with private key", "public key verification"],
                "difficulty": "hard",
            },
        )
    ).json()

    # Create published assessment with locked question order
    assess = (
        await client.post(
            "/api/assessments",
            headers=h_teacher,
            json={
                "course_id": course["id"],
                "title": "Cryptography Oral Proficiency Exam",
                "description": "Official oral examination for SEC401",
                "instructions": "Demonstrate understanding of encryption and signing.",
                "duration_minutes": 15,
                "max_questions": 2,
                "difficulty": "hard",
                "is_published": True,
                "question_ids": [q1["id"], q2["id"]],
            },
        )
    ).json()

    # 1. Student lists available assessments
    avail_res = await client.get("/api/student/assessments", headers=h_student)
    assert avail_res.status_code == 200
    avail_items = avail_res.json()
    assert len(avail_items) >= 1
    found = next((item for item in avail_items if item["id"] == assess["id"]), None)
    assert found is not None
    assert found["title"] == "Cryptography Oral Proficiency Exam"
    assert found["course_code"] == "SEC401"
    assert found["duration_minutes"] == 15
    assert found["question_count"] == 2
    assert found["start_url"] == f"/viva/{course['id']}?assessment={assess['id']}"

    # 2. Student starts custom viva session
    start_res = await client.post(
        "/api/viva/sessions",
        headers=h_student,
        json={"assessment_id": assess["id"]},
    )
    assert start_res.status_code == 201
    sess_data = start_res.json()
    assert sess_data["assessment_id"] == assess["id"]
    assert sess_data["assessment_title"] == "Cryptography Oral Proficiency Exam"
    assert sess_data["course_id"] == course["id"]
    assert sess_data["max_questions"] == 2

    # Verify questions locked in database session config
    session_row = await db_session.get(VivaSession, uuid.UUID(sess_data["id"]))
    assert session_row is not None
    assert session_row.config["question_order"] == [q1["id"], q2["id"]]
    assert session_row.config["assessment_id"] == assess["id"]


@pytest.mark.asyncio
async def test_assessment_rejects_questions_from_other_courses(
    client: AsyncClient, db_session
) -> None:
    """Assessments reject question_ids that belong to a different course."""
    t_token = await create_user_and_get_token(
        client, "t.mismatch@viva.edu", "teacher", "T Mismatch"
    )
    headers = {"Authorization": f"Bearer {t_token}"}

    c1 = (
        await client.post(
            "/api/courses", headers=headers, json={"name": "Course 1", "code": "C101"}
        )
    ).json()
    c2 = (
        await client.post(
            "/api/courses", headers=headers, json={"name": "Course 2", "code": "C102"}
        )
    ).json()

    (
        await client.post(
            f"/api/courses/{c1['id']}/topics", headers=headers, json={"name": "Top 1"}
        )
    ).json()
    top2 = (
        await client.post(
            f"/api/courses/{c2['id']}/topics", headers=headers, json={"name": "Top 2"}
        )
    ).json()

    # Question belongs to course 2
    q_c2 = (
        await client.post(
            "/api/questions",
            headers=headers,
            json={
                "topic_id": top2["id"],
                "question_text": "C2 Question",
                "expected_key_points": ["point"],
            },
        )
    ).json()

    # Attempt to create assessment for course 1 with question from course 2 -> 422
    res = await client.post(
        "/api/assessments",
        headers=headers,
        json={
            "course_id": c1["id"],
            "title": "Cross-Course Assessment",
            "question_ids": [q_c2["id"]],
        },
    )
    assert res.status_code == 422
    assert "questions do not belong to this course" in res.json()["detail"]


@pytest.mark.asyncio
async def test_student_assessments_lists_attempts_and_scores(
    client: AsyncClient, db_session
) -> None:
    """Student assessment listing displays attempt count and latest score."""
    t_token = await create_user_and_get_token(client, "t.attempt@viva.edu", "teacher", "T Attempt")
    s_token = await create_user_and_get_token(client, "s.attempt@viva.edu", "student", "S Attempt")
    h_teacher = {"Authorization": f"Bearer {t_token}"}
    h_student = {"Authorization": f"Bearer {s_token}"}

    s_me = (await client.get("/api/auth/me", headers=h_student)).json()
    s_id = uuid.UUID(s_me["id"])

    course = (
        await client.post(
            "/api/courses", headers=h_teacher, json={"name": "Networks", "code": "NET301"}
        )
    ).json()
    c_id = uuid.UUID(course["id"])

    assess = (
        await client.post(
            "/api/assessments",
            headers=h_teacher,
            json={
                "course_id": course["id"],
                "title": "Networking Final Oral",
                "is_published": True,
            },
        )
    ).json()
    a_id = assess["id"]

    # Record a completed session for this assessment in database
    sess = VivaSession(
        student_id=s_id,
        course_id=c_id,
        status=VivaStatus.COMPLETED,
        total_score=0.92,
        config={"assessment_id": a_id, "assessment_title": "Networking Final Oral"},
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
    )
    db_session.add(sess)
    await db_session.commit()

    # Query /api/student/assessments
    res = await client.get("/api/student/assessments", headers=h_student)
    assert res.status_code == 200
    items = res.json()
    match = next((item for item in items if item["id"] == a_id), None)
    assert match is not None
    assert match["user_attempts_count"] == 1
    assert match["latest_score_percent"] == "92%"
