"""Comprehensive tests for Detailed Performance Reports & Export (P2.12)."""

import csv
import io
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient

from app.models.answer import Answer
from app.models.viva_session import VivaSession, VivaStatus
from tests.test_courses import create_user_and_get_token


@pytest.mark.asyncio
async def test_student_performance_report_metrics_and_pdf(client: AsyncClient, db_session) -> None:
    """Students can retrieve their detailed oral performance report with topic breakdown, score trends, and PDF."""
    s_token = await create_user_and_get_token(
        client, "stu.reports@viva.edu", "student", "Report Student"
    )
    t_token = await create_user_and_get_token(
        client, "teach.reports@viva.edu", "teacher", "Report Teacher"
    )
    h_stu = {"Authorization": f"Bearer {s_token}"}
    h_teach = {"Authorization": f"Bearer {t_token}"}

    # Setup Course, Topics, Questions
    course_res = await client.post(
        "/api/courses",
        headers=h_teach,
        json={"name": "Computer Networks", "code": "NET-202"},
    )
    course_id = uuid.UUID(course_res.json()["id"])

    t1_res = await client.post(
        f"/api/courses/{course_id}/topics",
        headers=h_teach,
        json={"name": "Transport Layer", "sort_order": 1},
    )
    t1_id = uuid.UUID(t1_res.json()["id"])

    t2_res = await client.post(
        f"/api/courses/{course_id}/topics",
        headers=h_teach,
        json={"name": "Routing Protocols", "sort_order": 2},
    )
    t2_id = uuid.UUID(t2_res.json()["id"])

    q1_res = await client.post(
        "/api/questions",
        headers=h_teach,
        json={
            "course_id": str(course_id),
            "topic_id": str(t1_id),
            "question_text": "How does TCP 3-way handshake establish reliability?",
            "expected_key_points": ["SYN", "SYN-ACK", "ACK", "Sequence numbers"],
            "difficulty": "medium",
        },
    )
    q1_id = uuid.UUID(q1_res.json()["id"])

    q2_res = await client.post(
        "/api/questions",
        headers=h_teach,
        json={
            "course_id": str(course_id),
            "topic_id": str(t2_id),
            "question_text": "Compare distance-vector and link-state routing algorithms.",
            "expected_key_points": ["Bellman-Ford", "Dijkstra", "Convergence", "Topology"],
            "difficulty": "hard",
        },
    )
    q2_id = uuid.UUID(q2_res.json()["id"])

    # Launch student session
    start_res = await client.post(
        "/api/viva/sessions",
        headers=h_stu,
        json={"course_id": str(course_id)},
    )
    session_id = uuid.UUID(start_res.json()["id"])

    # Populate evaluated answers directly in DB to test scoring aggregation & rubrics
    session_row = await db_session.get(VivaSession, session_id)
    assert session_row is not None
    session_row.status = VivaStatus.COMPLETED
    session_row.total_score = 0.82
    session_row.overall_score = 0.82
    session_row.finished_at = datetime.now(UTC)

    ans1 = Answer(
        session_id=session_id,
        question_id=q1_id,
        sequence_number=1,
        transcript="Client sends SYN, server returns SYN-ACK, client ACKs with initial sequence numbers.",
        embedding_score=0.90,
        llm_score=0.92,
        fused_score=0.91,
        rubric_breakdown={"correctness": 0.95, "completeness": 0.90, "clarity": 0.88},
    )
    ans2 = Answer(
        session_id=session_id,
        question_id=q2_id,
        sequence_number=2,
        transcript="Distance-vector exchanges table with neighbors. Link state floods LSA packets using Dijkstra.",
        embedding_score=0.72,
        llm_score=0.74,
        fused_score=0.73,
        rubric_breakdown={"correctness": 0.75, "completeness": 0.70, "clarity": 0.74},
    )
    db_session.add_all([ans1, ans2])
    await db_session.commit()

    # 1. Test JSON Detailed Performance Report
    rep_res = await client.get("/api/reports/student/me", headers=h_stu)
    assert rep_res.status_code == 200, rep_res.text
    data = rep_res.json()

    assert data["student"]["email"] == "stu.reports@viva.edu"
    assert data["overall"]["completed_sessions"] == 1
    assert data["overall"]["average_score_percent"] == "82%"

    # Dimension averages
    dims = data["overall"]["dimension_averages"]
    assert dims["correctness"] == 0.85
    assert dims["completeness"] == 0.80
    assert dims["clarity"] == 0.81

    # Topic breakdown
    topics = data["topic_breakdown"]
    assert len(topics) == 2
    t_transport = next(t for t in topics if t["topic_name"] == "Transport Layer")
    t_routing = next(t for t in topics if t["topic_name"] == "Routing Protocols")
    assert t_transport["status"] == "strength"
    assert t_transport["average_score_percent"] == "91%"
    assert t_routing["status"] == "developing"
    assert t_routing["average_score_percent"] == "73%"

    # Score history & recent attempts
    assert len(data["score_history"]) == 1
    assert data["score_history"][0]["score_percent"] == "82%"
    assert len(data["recent_attempts"]) == 1
    assert data["recent_attempts"][0]["type"] == "practice"

    # 2. Test PDF Report Download
    pdf_res = await client.get("/api/reports/student/me/pdf", headers=h_stu)
    assert pdf_res.status_code == 200
    assert pdf_res.headers["content-type"] == "application/pdf"
    assert "attachment; filename=" in pdf_res.headers["content-disposition"]
    assert pdf_res.content.startswith(b"%PDF-")
    assert len(pdf_res.content) > 1000


@pytest.mark.asyncio
async def test_empty_student_report_handled_gracefully(client: AsyncClient, db_session) -> None:
    """A student with no viva sessions receives a sensible empty report without server errors."""
    s_token = await create_user_and_get_token(
        client, "stu.empty@viva.edu", "student", "Empty Student"
    )
    headers = {"Authorization": f"Bearer {s_token}"}

    rep_res = await client.get("/api/reports/student/me", headers=headers)
    assert rep_res.status_code == 200
    data = rep_res.json()

    assert data["overall"]["total_sessions"] == 0
    assert data["overall"]["completed_sessions"] == 0
    assert data["overall"]["average_score"] is None
    assert data["overall"]["average_score_percent"] == "—"
    assert data["topic_breakdown"] == []
    assert data["score_history"] == []
    assert "Start a viva session" in data["coaching_summary"]

    # PDF generation for empty state also succeeds
    pdf_res = await client.get("/api/reports/student/me/pdf", headers=headers)
    assert pdf_res.status_code == 200
    assert pdf_res.content.startswith(b"%PDF-")


@pytest.mark.asyncio
async def test_teacher_student_report_scoping_and_isolation(
    client: AsyncClient, db_session
) -> None:
    """Teachers can only access reports for students within courses they instruct."""
    t1_token = await create_user_and_get_token(
        client, "t1.scoping@viva.edu", "teacher", "Teacher One"
    )
    t2_token = await create_user_and_get_token(
        client, "t2.scoping@viva.edu", "teacher", "Teacher Two"
    )
    s_token = await create_user_and_get_token(
        client, "stu.scoping@viva.edu", "student", "Scoping Student"
    )
    h_t1 = {"Authorization": f"Bearer {t1_token}"}
    h_t2 = {"Authorization": f"Bearer {t2_token}"}
    h_s = {"Authorization": f"Bearer {s_token}"}

    # Get student ID
    s_me = (await client.get("/api/auth/me", headers=h_s)).json()
    student_id = s_me["id"]

    # Teacher 1 creates course
    c1_res = await client.post(
        "/api/courses",
        headers=h_t1,
        json={"name": "Compiler Design", "code": "COMP-401"},
    )
    c1_id = c1_res.json()["id"]

    # Student launches session in Teacher 1's course
    s_sess = await client.post(
        "/api/viva/sessions",
        headers=h_s,
        json={"course_id": c1_id},
    )
    session_id = uuid.UUID(s_sess.json()["id"])

    # Complete session
    s_row = await db_session.get(VivaSession, session_id)
    s_row.status = VivaStatus.COMPLETED
    s_row.total_score = 0.88
    await db_session.commit()

    # Teacher 1 accesses student's report -> 200 OK
    t1_rep = await client.get(
        f"/api/reports/teacher/student/{student_id}",
        headers=h_t1,
    )
    assert t1_rep.status_code == 200
    assert t1_rep.json()["overall"]["completed_sessions"] == 1
    assert t1_rep.json()["overall"]["average_score_percent"] == "88%"

    # Teacher 1 downloads PDF
    t1_pdf = await client.get(
        f"/api/reports/teacher/student/{student_id}/pdf",
        headers=h_t1,
    )
    assert t1_pdf.status_code == 200
    assert t1_pdf.content.startswith(b"%PDF-")

    # Teacher 2 (unrelated teacher) accesses student's report -> 403 Forbidden
    t2_rep = await client.get(
        f"/api/reports/teacher/student/{student_id}",
        headers=h_t2,
    )
    assert t2_rep.status_code == 403
    assert "access" in t2_rep.text.lower()


@pytest.mark.asyncio
async def test_teacher_class_report_filters_and_pdf(client: AsyncClient, db_session) -> None:
    """Teachers can view class-level aggregated reports with date/topic filters and download PDF."""
    t_token = await create_user_and_get_token(
        client, "t.classrep@viva.edu", "teacher", "Class Rep Teacher"
    )
    s1_token = await create_user_and_get_token(
        client, "s1.classrep@viva.edu", "student", "Student One"
    )
    s2_token = await create_user_and_get_token(
        client, "s2.classrep@viva.edu", "student", "Student Two"
    )
    h_teach = {"Authorization": f"Bearer {t_token}"}
    h_s1 = {"Authorization": f"Bearer {s1_token}"}
    h_s2 = {"Authorization": f"Bearer {s2_token}"}

    # Course & Topic
    course_res = await client.post(
        "/api/courses",
        headers=h_teach,
        json={"name": "Cloud Computing", "code": "CLOUD-301"},
    )
    course_id = uuid.UUID(course_res.json()["id"])

    t1_res = await client.post(
        f"/api/courses/{course_id}/topics",
        headers=h_teach,
        json={"name": "Containerization & K8s", "sort_order": 1},
    )
    t1_id = uuid.UUID(t1_res.json()["id"])

    q1_res = await client.post(
        "/api/questions",
        headers=h_teach,
        json={
            "course_id": str(course_id),
            "topic_id": str(t1_id),
            "question_text": "What are Kubernetes Pods and ReplicaSets?",
            "expected_key_points": ["Pod container", "Replica count"],
            "difficulty": "medium",
        },
    )
    q1_id = uuid.UUID(q1_res.json()["id"])

    # Student 1 session (Score: 0.90 - Mastery)
    sess1_res = await client.post(
        "/api/viva/sessions", headers=h_s1, json={"course_id": str(course_id)}
    )
    sess1_id = uuid.UUID(sess1_res.json()["id"])
    s1_row = await db_session.get(VivaSession, sess1_id)
    s1_row.status = VivaStatus.COMPLETED
    s1_row.total_score = 0.90
    s1_row.finished_at = datetime.now(UTC)

    ans1 = Answer(
        session_id=sess1_id,
        question_id=q1_id,
        sequence_number=1,
        transcript="Pods encapsulate containers; ReplicaSets ensure pod replicas remain healthy.",
        embedding_score=0.90,
        fused_score=0.90,
    )
    db_session.add(ans1)

    # Student 2 session (Score: 0.55 - Developing / Weakness)
    sess2_res = await client.post(
        "/api/viva/sessions", headers=h_s2, json={"course_id": str(course_id)}
    )
    sess2_id = uuid.UUID(sess2_res.json()["id"])
    s2_row = await db_session.get(VivaSession, sess2_id)
    s2_row.status = VivaStatus.COMPLETED
    s2_row.total_score = 0.55
    s2_row.finished_at = datetime.now(UTC)

    ans2 = Answer(
        session_id=sess2_id,
        question_id=q1_id,
        sequence_number=1,
        transcript="Pod is like a container, replicaset copies them.",
        embedding_score=0.55,
        fused_score=0.55,
    )
    db_session.add(ans2)
    await db_session.commit()

    # 1. Fetch Class Report
    class_res = await client.get(
        "/api/reports/teacher/class",
        headers=h_teach,
        params={"course_id": str(course_id)},
    )
    assert class_res.status_code == 200, class_res.text
    c_data = class_res.json()

    assert c_data["summary"]["total_students"] == 2
    assert c_data["summary"]["completed_sessions"] == 2
    assert c_data["summary"]["average_score_percent"] in ("72%", "73%")

    # Distribution checks
    dist = c_data["score_distribution"]
    assert dist["mastery"] == 1
    assert dist["developing"] == 1
    assert dist["proficient"] == 0

    # 2. Filter by topic
    topic_filter_res = await client.get(
        "/api/reports/teacher/class",
        headers=h_teach,
        params={"course_id": str(course_id), "topic_id": str(t1_id)},
    )
    assert topic_filter_res.status_code == 200

    # 3. Download Class PDF Report
    pdf_res = await client.get(
        "/api/reports/teacher/class/pdf",
        headers=h_teach,
        params={"course_id": str(course_id)},
    )
    assert pdf_res.status_code == 200
    assert pdf_res.headers["content-type"] == "application/pdf"
    assert pdf_res.content.startswith(b"%PDF-")


@pytest.mark.asyncio
async def test_csv_export_escaping_and_filters(client: AsyncClient, db_session) -> None:
    """CSV export properly escapes commas, quotes, and newlines in transcripts and feedback."""
    t_token = await create_user_and_get_token(
        client, "t.csvescape@viva.edu", "teacher", "CSV Escape Teacher"
    )
    s_token = await create_user_and_get_token(
        client, "s.csvescape@viva.edu", "student", "CSV Escape Student"
    )
    h_teach = {"Authorization": f"Bearer {t_token}"}
    h_stu = {"Authorization": f"Bearer {s_token}"}

    course_res = await client.post(
        "/api/courses",
        headers=h_teach,
        json={"name": "Software Architecture", "code": "ARCH-501"},
    )
    course_id = uuid.UUID(course_res.json()["id"])

    t_res = await client.post(
        f"/api/courses/{course_id}/topics",
        headers=h_teach,
        json={"name": "Microservices & ACID", "sort_order": 1},
    )
    topic_id = uuid.UUID(t_res.json()["id"])

    # Question with commas and quotes
    complex_q_text = (
        'Explain "CAP theorem", focusing on "Consistency, Availability, and Partition-tolerance".'
    )
    q_res = await client.post(
        "/api/questions",
        headers=h_teach,
        json={
            "course_id": str(course_id),
            "topic_id": str(topic_id),
            "question_text": complex_q_text,
            "expected_key_points": ["Consistency", "Availability", "Partition"],
            "difficulty": "hard",
        },
    )
    q_id = uuid.UUID(q_res.json()["id"])

    sess_res = await client.post(
        "/api/viva/sessions", headers=h_stu, json={"course_id": str(course_id)}
    )
    sess_id = uuid.UUID(sess_res.json()["id"])
    s_row = await db_session.get(VivaSession, sess_id)
    s_row.status = VivaStatus.COMPLETED
    s_row.total_score = 0.85

    # Answer transcript with newlines, commas, and quotes
    complex_transcript = (
        "According to Brewer's conjecture,\n"
        "in the presence of a network partition, you must choose:\n"
        '1) "Consistency" (CP), or\n'
        '2) "Availability" (AP).'
    )
    ans = Answer(
        session_id=sess_id,
        question_id=q_id,
        sequence_number=1,
        transcript=complex_transcript,
        embedding_score=0.85,
        fused_score=0.85,
    )
    db_session.add(ans)
    await db_session.commit()

    # Export CSV
    csv_res = await client.get(
        "/api/reports/export",
        headers=h_teach,
        params={"course_id": str(course_id)},
    )
    assert csv_res.status_code == 200
    assert csv_res.headers["content-type"].startswith("text/csv")
    csv_text = csv_res.text

    # Parse with Python standard csv.reader to verify integrity of escaping
    reader = csv.reader(io.StringIO(csv_text))
    rows = list(reader)
    assert len(rows) == 2  # Header + 1 Answer row
    header, data_row = rows[0], rows[1]

    assert "session_id" in header
    assert "question_text" in header
    assert "transcript" in header

    # Verify that the parsed fields preserved the exact quotes and newlines safely
    q_idx = header.index("question_text")
    tr_idx = header.index("transcript")
    assert data_row[q_idx] == complex_q_text
    assert '1) "Consistency" (CP)' in data_row[tr_idx]


@pytest.mark.asyncio
async def test_cross_role_and_date_validation(client: AsyncClient, db_session) -> None:
    """Students cannot access teacher reports, and invalid date ranges are rejected."""
    s_token = await create_user_and_get_token(
        client, "stu.unauth@viva.edu", "student", "Unauth Student"
    )
    t_token = await create_user_and_get_token(
        client, "teach.dates@viva.edu", "teacher", "Date Teacher"
    )
    h_stu = {"Authorization": f"Bearer {s_token}"}
    h_teach = {"Authorization": f"Bearer {t_token}"}

    # Student cannot call teacher class report or student report
    assert (await client.get("/api/reports/teacher/class", headers=h_stu)).status_code == 403
    assert (
        await client.get(f"/api/reports/teacher/student/{uuid.uuid4()}", headers=h_stu)
    ).status_code == 403
    assert (await client.get("/api/reports/export", headers=h_stu)).status_code == 403

    # Teacher invalid date range: from_date > to_date -> 422
    now = datetime.now(UTC)
    invalid_dates_res = await client.get(
        "/api/reports/teacher/class",
        headers=h_teach,
        params={
            "from_date": (now + timedelta(days=2)).isoformat(),
            "to_date": (now - timedelta(days=2)).isoformat(),
        },
    )
    assert invalid_dates_res.status_code == 422
    assert "earlier than" in invalid_dates_res.text.lower()
