"""Comprehensive tests for Assessment Assignment, Scheduling & Deadlines (P2.11)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient

from app.models.viva_session import VivaSession, VivaStatus
from tests.test_courses import create_user_and_get_token


@pytest.mark.asyncio
async def test_assignment_crud_and_status_lifecycle(client: AsyncClient, db_session) -> None:
    """Teacher can create an assignment, view it, update instructions/deadlines, and delete when unstarted."""
    t_token = await create_user_and_get_token(
        client, "teacher.assign@viva.edu", "teacher", "Assignment Teacher"
    )
    headers = {"Authorization": f"Bearer {t_token}"}

    # 1. Create course & topic
    course_res = await client.post(
        "/api/courses",
        headers=headers,
        json={"name": "Database Systems", "code": "CS-DB-101", "description": "Relational DBs"},
    )
    course_id = course_res.json()["id"]

    topic_res = await client.post(
        f"/api/courses/{course_id}/topics",
        headers=headers,
        json={"name": "SQL & Normalization", "sort_order": 1},
    )
    topic_id = topic_res.json()["id"]

    # 2. Create and publish an assessment
    assessment_res = await client.post(
        "/api/assessments",
        headers=headers,
        json={
            "course_id": course_id,
            "title": "Midterm Oral Exam",
            "duration_minutes": 20,
            "max_questions": 4,
            "difficulty": "medium",
            "is_published": True,
            "topic_ids": [topic_id],
        },
    )
    assessment_id = assessment_res.json()["id"]

    # 3. Create scheduled assignment
    now = datetime.now(UTC)
    start_dt = (now - timedelta(hours=1)).isoformat()
    end_dt = (now + timedelta(days=3)).isoformat()

    assign_res = await client.post(
        "/api/assignments",
        headers=headers,
        json={
            "course_id": course_id,
            "assessment_id": assessment_id,
            "title": "CS-DB-101 Midterm Assignment",
            "instructions": "Be in a quiet room with functioning microphone.",
            "start_date": start_dt,
            "deadline": end_dt,
            "attempt_limit": 2,
            "is_active": True,
        },
    )
    assert assign_res.status_code == 201, assign_res.text
    assignment_data = assign_res.json()
    assignment_id = assignment_data["id"]
    assert assignment_data["title"] == "CS-DB-101 Midterm Assignment"
    assert assignment_data["status"] == "active"
    assert assignment_data["attempt_limit"] == 2
    assert assignment_data["course_name"] == "Database Systems"

    # 4. List teacher assignments
    list_res = await client.get("/api/assignments", headers=headers)
    assert list_res.status_code == 200
    items = list_res.json()
    assert len(items) >= 1
    found = next((item for item in items if item["id"] == assignment_id), None)
    assert found is not None
    assert found["total_submissions"] == 0

    # 5. Get assignment details
    detail_res = await client.get(f"/api/assignments/{assignment_id}", headers=headers)
    assert detail_res.status_code == 200
    assert detail_res.json()["title"] == "CS-DB-101 Midterm Assignment"

    # 6. Update assignment
    extended_deadline = (now + timedelta(days=5)).isoformat()
    upd_res = await client.put(
        f"/api/assignments/{assignment_id}",
        headers=headers,
        json={
            "title": "CS-DB-101 Midterm Assignment (Extended)",
            "instructions": "Updated instructions: 20 minutes limit.",
            "deadline": extended_deadline,
            "attempt_limit": 3,
        },
    )
    assert upd_res.status_code == 200
    assert upd_res.json()["title"] == "CS-DB-101 Midterm Assignment (Extended)"
    assert upd_res.json()["attempt_limit"] == 3

    # 7. Delete unstarted assignment
    del_res = await client.delete(f"/api/assignments/{assignment_id}", headers=headers)
    assert del_res.status_code == 200
    assert del_res.json()["action"] == "deleted"

    # Verify 404 on fetch
    fetch_after_del = await client.get(f"/api/assignments/{assignment_id}", headers=headers)
    assert fetch_after_del.status_code == 404


@pytest.mark.asyncio
async def test_assignment_requires_published_assessment_and_course_ownership(
    client: AsyncClient, db_session
) -> None:
    """Cannot assign unpublished assessments or cross-teacher courses."""
    t1_token = await create_user_and_get_token(
        client, "t1.ownership@viva.edu", "teacher", "Teacher One"
    )
    t2_token = await create_user_and_get_token(
        client, "t2.ownership@viva.edu", "teacher", "Teacher Two"
    )
    h1 = {"Authorization": f"Bearer {t1_token}"}
    h2 = {"Authorization": f"Bearer {t2_token}"}

    # T1 course
    c1_res = await client.post(
        "/api/courses",
        headers=h1,
        json={"name": "Algorithms", "code": "ALGO-101", "description": "Algo"},
    )
    c1_id = c1_res.json()["id"]

    # T1 unpublished assessment
    draft_res = await client.post(
        "/api/assessments",
        headers=h1,
        json={
            "course_id": c1_id,
            "title": "Draft Algo Quiz",
            "is_published": False,
        },
    )
    draft_id = draft_res.json()["id"]

    # Attempt to assign draft -> 422
    err_assign = await client.post(
        "/api/assignments",
        headers=h1,
        json={
            "course_id": c1_id,
            "assessment_id": draft_id,
            "title": "Unpublished Assignment",
        },
    )
    assert err_assign.status_code == 422
    assert "unpublished" in err_assign.text.lower()

    # Now publish it
    await client.post(f"/api/assessments/{draft_id}/publish?published=true", headers=h1)

    # T2 tries to assign T1's course -> 403
    t2_assign = await client.post(
        "/api/assignments",
        headers=h2,
        json={
            "course_id": c1_id,
            "assessment_id": draft_id,
            "title": "T2 Stealing Assignment",
        },
    )
    assert t2_assign.status_code == 403


@pytest.mark.asyncio
async def test_assignment_scheduling_window_enforcement(client: AsyncClient, db_session) -> None:
    """Scheduled window boundaries (start_date in future, deadline in past) are enforced server-side."""
    t_token = await create_user_and_get_token(
        client, "teacher.sched@viva.edu", "teacher", "Scheduling Teacher"
    )
    s_token = await create_user_and_get_token(
        client, "student.sched@viva.edu", "student", "Scheduling Student"
    )
    h_teach = {"Authorization": f"Bearer {t_token}"}
    h_stu = {"Authorization": f"Bearer {s_token}"}

    course_res = await client.post(
        "/api/courses",
        headers=h_teach,
        json={"name": "Discrete Math", "code": "DM-201", "description": "Discrete structures"},
    )
    course_id = course_res.json()["id"]

    assessment_res = await client.post(
        "/api/assessments",
        headers=h_teach,
        json={
            "course_id": course_id,
            "title": "Graph Theory Viva",
            "is_published": True,
        },
    )
    assessment_id = assessment_res.json()["id"]

    now = datetime.now(UTC)

    # 1. Future assignment (scheduled)
    future_start = (now + timedelta(days=2)).isoformat()
    future_end = (now + timedelta(days=5)).isoformat()
    future_assign = await client.post(
        "/api/assignments",
        headers=h_teach,
        json={
            "course_id": course_id,
            "assessment_id": assessment_id,
            "title": "Future Viva",
            "start_date": future_start,
            "deadline": future_end,
        },
    )
    future_id = future_assign.json()["id"]
    assert future_assign.json()["status"] == "scheduled"

    # Student cannot launch future assignment
    launch_future = await client.post(
        "/api/viva/sessions",
        headers=h_stu,
        json={"assignment_id": future_id},
    )
    assert launch_future.status_code == 403
    assert "not started yet" in launch_future.text.lower()

    # 2. Expired assignment (overdue/closed)
    past_start = (now - timedelta(days=5)).isoformat()
    past_end = (now - timedelta(days=1)).isoformat()
    expired_assign = await client.post(
        "/api/assignments",
        headers=h_teach,
        json={
            "course_id": course_id,
            "assessment_id": assessment_id,
            "title": "Expired Viva",
            "start_date": past_start,
            "deadline": past_end,
        },
    )
    expired_id = expired_assign.json()["id"]
    assert expired_assign.json()["status"] == "closed"

    # Student cannot launch expired assignment
    launch_expired = await client.post(
        "/api/viva/sessions",
        headers=h_stu,
        json={"assignment_id": expired_id},
    )
    assert launch_expired.status_code == 403
    assert "passed" in launch_expired.text.lower()

    # 3. Student assignment list reflects correct status badges
    stu_assignments = await client.get("/api/student/assignments", headers=h_stu)
    assert stu_assignments.status_code == 200
    items = stu_assignments.json()
    fut_item = next(x for x in items if x["id"] == future_id)
    exp_item = next(x for x in items if x["id"] == expired_id)
    assert fut_item["status"] == "scheduled"
    assert fut_item["can_launch"] is False
    assert exp_item["status"] == "overdue"
    assert exp_item["can_launch"] is False


@pytest.mark.asyncio
async def test_student_attempt_limit_and_duplicate_launch_prevention(
    client: AsyncClient, db_session
) -> None:
    """Prevents duplicate active launches, enforces attempt limits, and shows submissions."""
    t_token = await create_user_and_get_token(
        client, "teacher.attempts@viva.edu", "teacher", "Attempts Teacher"
    )
    s_token = await create_user_and_get_token(
        client, "student.attempts@viva.edu", "student", "Attempts Student"
    )
    h_teach = {"Authorization": f"Bearer {t_token}"}
    h_stu = {"Authorization": f"Bearer {s_token}"}

    # Course, assessment, and active assignment with attempt_limit=1
    course_res = await client.post(
        "/api/courses",
        headers=h_teach,
        json={"name": "Software Engineering", "code": "SE-301"},
    )
    course_id = course_res.json()["id"]

    assessment_res = await client.post(
        "/api/assessments",
        headers=h_teach,
        json={
            "course_id": course_id,
            "title": "Design Patterns Viva",
            "is_published": True,
        },
    )
    assessment_id = assessment_res.json()["id"]

    now = datetime.now(UTC)
    assign_res = await client.post(
        "/api/assignments",
        headers=h_teach,
        json={
            "course_id": course_id,
            "assessment_id": assessment_id,
            "title": "Design Patterns Assignment 1",
            "start_date": (now - timedelta(hours=1)).isoformat(),
            "deadline": (now + timedelta(days=2)).isoformat(),
            "attempt_limit": 1,
        },
    )
    assignment_id = assign_res.json()["id"]

    # 1. Student launches session
    s1_res = await client.post(
        "/api/viva/sessions",
        headers=h_stu,
        json={"assignment_id": assignment_id},
    )
    assert s1_res.status_code == 201, s1_res.text
    s1_data = s1_res.json()
    assert s1_data["assignment_id"] == assignment_id
    session_id = s1_data["id"]

    # 2. While session is IN_PROGRESS, second launch returns 409 Conflict
    dup_res = await client.post(
        "/api/viva/sessions",
        headers=h_stu,
        json={"assignment_id": assignment_id},
    )
    assert dup_res.status_code == 409
    assert "active session" in dup_res.text.lower()

    # 3. Complete the first session directly in DB
    session_record = await db_session.get(VivaSession, uuid.UUID(session_id))
    assert session_record is not None
    session_record.status = VivaStatus.COMPLETED
    session_record.total_score = 0.88
    session_record.overall_score = 0.88
    session_record.finished_at = datetime.now(UTC)
    await db_session.commit()

    # 4. Attempt limit reached -> 403 Forbidden
    limit_res = await client.post(
        "/api/viva/sessions",
        headers=h_stu,
        json={"assignment_id": assignment_id},
    )
    assert limit_res.status_code == 403
    assert "attempt limit" in limit_res.text.lower()

    # 5. Teacher submissions endpoint shows the student submission
    sub_res = await client.get(
        f"/api/assignments/{assignment_id}/submissions",
        headers=h_teach,
    )
    assert sub_res.status_code == 200
    sub_data = sub_res.json()
    assert sub_data["total_submissions"] == 1
    assert sub_data["completed_count"] == 1
    assert sub_data["average_score"] == 0.88
    assert len(sub_data["submissions"]) == 1
    assert sub_data["submissions"][0]["student_name"] == "Attempts Student"
    assert sub_data["submissions"][0]["score"] == 0.88

    # 6. Deleting assignment with existing submissions deactivates it instead of deleting
    del_res = await client.delete(
        f"/api/assignments/{assignment_id}",
        headers=h_teach,
    )
    assert del_res.status_code == 200
    assert del_res.json()["action"] == "cancelled"

    # Verify assignment is still queryable with is_active=False
    fetch_res = await client.get(f"/api/assignments/{assignment_id}", headers=h_teach)
    assert fetch_res.status_code == 200
    assert fetch_res.json()["is_active"] is False
    assert fetch_res.json()["status"] == "closed"


@pytest.mark.asyncio
async def test_cohort_targeting_and_cross_teacher_isolation(
    client: AsyncClient, db_session
) -> None:
    """Assignments targeted to specific student IDs are shielded from other students."""
    t_token = await create_user_and_get_token(
        client, "cohort.teacher@viva.edu", "teacher", "Cohort Teacher"
    )
    s1_token = await create_user_and_get_token(
        client, "cohort.student1@viva.edu", "student", "Targeted Student"
    )
    s2_token = await create_user_and_get_token(
        client, "cohort.student2@viva.edu", "student", "Untargeted Student"
    )
    h_teach = {"Authorization": f"Bearer {t_token}"}
    h_s1 = {"Authorization": f"Bearer {s1_token}"}
    h_s2 = {"Authorization": f"Bearer {s2_token}"}

    # Get student 1 id
    me_s1 = (await client.get("/api/auth/me", headers=h_s1)).json()
    s1_id = me_s1["id"]

    course_res = await client.post(
        "/api/courses",
        headers=h_teach,
        json={"name": "Advanced Compilers", "code": "CS-COMP-401"},
    )
    course_id = course_res.json()["id"]

    assessment_res = await client.post(
        "/api/assessments",
        headers=h_teach,
        json={
            "course_id": course_id,
            "title": "AST & Code Generation Viva",
            "is_published": True,
        },
    )
    assessment_id = assessment_res.json()["id"]

    # Assign specifically to student 1 only
    assign_res = await client.post(
        "/api/assignments",
        headers=h_teach,
        json={
            "course_id": course_id,
            "assessment_id": assessment_id,
            "title": "Honors Compiler Viva",
            "assigned_student_ids": [s1_id],
        },
    )
    assignment_id = assign_res.json()["id"]

    # Student 1 sees it in assignments list
    s1_list = (await client.get("/api/student/assignments", headers=h_s1)).json()
    assert any(x["id"] == assignment_id for x in s1_list)

    # Student 2 DOES NOT see it
    s2_list = (await client.get("/api/student/assignments", headers=h_s2)).json()
    assert not any(x["id"] == assignment_id for x in s2_list)

    # Student 2 attempting direct launch is rejected (403 Forbidden)
    s2_launch = await client.post(
        "/api/viva/sessions",
        headers=h_s2,
        json={"assignment_id": assignment_id},
    )
    assert s2_launch.status_code == 403
    assert "not assigned" in s2_launch.text.lower()
