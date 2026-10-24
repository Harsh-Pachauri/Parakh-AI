"""Tests for AI-Powered Student Weakness Detection & Personalized Practice (P2.9)."""

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient

from app.models.answer import Answer
from app.models.question import Question
from app.models.score_override import ScoreOverride
from app.models.topic import Topic
from app.models.viva_session import VivaSession, VivaStatus
from tests.test_courses import create_user_and_get_token


@pytest.mark.asyncio
async def test_student_insights_empty_when_no_sessions(client: AsyncClient, db_session) -> None:
    """A student with no viva attempts receives has_data=False and initial topic recommendations."""
    teacher_token = await create_user_and_get_token(
        client, "teacher.init@viva.edu", "teacher", "Course Teacher"
    )
    student_token = await create_user_and_get_token(
        client, "student.empty@viva.edu", "student", "Fresh Student"
    )

    # Create a course with topics
    course_res = await client.post(
        "/api/courses",
        headers={"Authorization": f"Bearer {teacher_token}"},
        json={"name": "Discrete Mathematics", "code": "CS201", "description": "Logic and sets"},
    )
    assert course_res.status_code == 201
    course_id = uuid.UUID(course_res.json()["id"])

    topic = Topic(course_id=course_id, name="Set Theory & Relations")
    db_session.add(topic)
    await db_session.commit()

    # Call GET /api/viva/insights
    res = await client.get(
        "/api/viva/insights",
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["has_data"] is False
    assert data["total_evaluated_sessions"] == 0
    assert data["total_evaluated_answers"] == 0
    assert data["overall_average_score"] is None
    assert data["overall_average_score_percent"] == "—"
    assert data["weaknesses"] == []
    assert data["strengths"] == []
    assert data["developing"] == []
    assert len(data["recommendations"]) >= 1
    rec = data["recommendations"][0]
    assert rec["course_id"] == str(course_id)
    assert rec["topic_name"] == "Set Theory & Relations"
    assert rec["start_url"] == f"/viva/{course_id}?topic={topic.id}"


@pytest.mark.asyncio
async def test_student_insights_weakness_and_strength_classification(
    client: AsyncClient, db_session
) -> None:
    """Accurately classifies topics into weaknesses (<65%) and strengths (>=80%) with dimension scores and evidence."""
    teacher_token = await create_user_and_get_token(
        client, "t.diag@viva.edu", "teacher", "Diagnostic Teacher"
    )
    student_token = await create_user_and_get_token(
        client, "s.diag@viva.edu", "student", "Diagnostic Student"
    )

    s_me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {student_token}"})
    student_id = uuid.UUID(s_me.json()["id"])

    # Create course
    course_res = await client.post(
        "/api/courses",
        headers={"Authorization": f"Bearer {teacher_token}"},
        json={"name": "Data Structures & Algorithms", "code": "CS202", "description": "DSA"},
    )
    course_id = uuid.UUID(course_res.json()["id"])

    # Weak topic (<65%)
    topic_weak = Topic(course_id=course_id, name="Recursion & Dynamic Programming")
    # Strong topic (>=80%)
    topic_strong = Topic(course_id=course_id, name="Arrays & Strings")
    db_session.add_all([topic_weak, topic_strong])
    await db_session.commit()
    await db_session.refresh(topic_weak)
    await db_session.refresh(topic_strong)

    q_weak = Question(
        topic_id=topic_weak.id,
        question_text="Explain memoization in dynamic programming.",
        expected_key_points=["cache overlapping subproblems", "top-down approach"],
    )
    q_strong = Question(
        topic_id=topic_strong.id,
        question_text="Explain two-pointer technique on arrays.",
        expected_key_points=["left and right pointers", "O(N) time complexity"],
    )
    db_session.add_all([q_weak, q_strong])
    await db_session.commit()
    await db_session.refresh(q_weak)
    await db_session.refresh(q_strong)

    # Completed session
    session = VivaSession(
        student_id=student_id,
        course_id=course_id,
        status=VivaStatus.COMPLETED,
        max_questions=2,
        total_score=0.70,
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
    )
    db_session.add(session)
    await db_session.commit()
    await db_session.refresh(session)

    # Answer 1: Weak performance (50%)
    ans_weak = Answer(
        session_id=session.id,
        question_id=q_weak.id,
        sequence_number=1,
        transcript="Memoization is like saving things in memory maybe.",
        fused_score=0.50,
        rubric_breakdown={
            "correctness": 4.5,
            "completeness": 3.0,
            "clarity": 5.5,
            "justification": "Failed to mention overlapping subproblems or recursive call caching.",
        },
    )

    # Answer 2: Strong performance (90%)
    ans_strong = Answer(
        session_id=session.id,
        question_id=q_strong.id,
        sequence_number=2,
        transcript="Two pointers traverse from both ends toward each other in linear time.",
        fused_score=0.90,
        rubric_breakdown={
            "correctness": 9.0,
            "completeness": 9.0,
            "clarity": 8.5,
            "justification": "Clear and thorough explanation of bidirectional array traversal.",
        },
    )
    db_session.add_all([ans_weak, ans_strong])
    await db_session.commit()

    # Query insights
    res = await client.get(
        "/api/viva/insights",
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert res.status_code == 200
    data = res.json()

    assert data["has_data"] is True
    assert data["total_evaluated_sessions"] == 1
    assert data["total_evaluated_answers"] == 2
    assert data["overall_average_score"] == 0.70
    assert data["overall_average_score_percent"] == "70%"

    # Weakness check
    assert len(data["weaknesses"]) == 1
    w = data["weaknesses"][0]
    assert w["topic_id"] == str(topic_weak.id)
    assert w["topic_name"] == "Recursion & Dynamic Programming"
    assert w["average_score"] == 0.50
    assert w["average_score_percent"] == "50%"
    assert w["status"] == "weakness"
    assert w["evaluated_answers_count"] == 1
    assert w["dimension_scores"]["completeness"] == 3.0
    assert w["dimension_scores"]["correctness"] == 4.5
    assert "completeness" in w["primary_gap"]
    assert any("overlapping subproblems" in snippet for snippet in w["feedback_themes"])

    # Strength check
    assert len(data["strengths"]) == 1
    s = data["strengths"][0]
    assert s["topic_id"] == str(topic_strong.id)
    assert s["topic_name"] == "Arrays & Strings"
    assert s["average_score"] == 0.90
    assert s["average_score_percent"] == "90%"
    assert s["status"] == "strength"

    # Targeted practice recommendation check
    assert len(data["recommendations"]) >= 1
    rec = data["recommendations"][0]
    assert rec["topic_id"] == str(topic_weak.id)
    assert rec["priority"] == "high"
    assert rec["start_url"] == f"/viva/{course_id}?topic={topic_weak.id}"
    assert "50%" in rec["reason"]


@pytest.mark.asyncio
async def test_student_insights_teacher_score_override_respected(
    client: AsyncClient, db_session
) -> None:
    """When a teacher overrides an answer score, the override is used for weakness diagnostics."""
    teacher_token = await create_user_and_get_token(
        client, "t.override@viva.edu", "teacher", "Teacher Override"
    )
    student_token = await create_user_and_get_token(
        client, "s.override@viva.edu", "student", "Student Override"
    )

    t_me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {teacher_token}"})
    s_me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {student_token}"})
    teacher_id = uuid.UUID(t_me.json()["id"])
    student_id = uuid.UUID(s_me.json()["id"])

    # Course + Topic + Question
    course_res = await client.post(
        "/api/courses",
        headers={"Authorization": f"Bearer {teacher_token}"},
        json={"name": "Operating Systems", "code": "CS301", "description": "OS Concepts"},
    )
    course_id = uuid.UUID(course_res.json()["id"])

    topic = Topic(course_id=course_id, name="Deadlocks & Synchronization")
    db_session.add(topic)
    await db_session.commit()
    await db_session.refresh(topic)

    q = Question(
        topic_id=topic.id,
        question_text="State the four Coffman conditions.",
        expected_key_points=["mutual exclusion", "hold and wait", "no preemption", "circular wait"],
    )
    db_session.add(q)
    await db_session.commit()
    await db_session.refresh(q)

    session = VivaSession(
        student_id=student_id,
        course_id=course_id,
        status=VivaStatus.COMPLETED,
        max_questions=1,
        total_score=0.85,
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
    )
    db_session.add(session)
    await db_session.commit()
    await db_session.refresh(session)

    # Automated score was 0.85 (strength)
    answer = Answer(
        session_id=session.id,
        question_id=q.id,
        sequence_number=1,
        transcript="Mutual exclusion, hold and wait, no preemption, and circular wait.",
        fused_score=0.85,
    )
    db_session.add(answer)
    await db_session.commit()
    await db_session.refresh(answer)

    # Teacher overrides score to 0.45 due to lack of conceptual understanding in follow-up
    override = ScoreOverride(
        answer_id=answer.id,
        teacher_id=teacher_id,
        original_score=0.85,
        override_score=0.45,
        justification="Could not explain circular wait when probed verbally.",
    )
    db_session.add(override)
    await db_session.commit()

    # Query insights for student
    res = await client.get(
        "/api/viva/insights",
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert res.status_code == 200
    data = res.json()

    # Should be classified as weakness (45%), NOT strength (85%)
    assert len(data["weaknesses"]) == 1
    w = data["weaknesses"][0]
    assert w["topic_id"] == str(topic.id)
    assert w["average_score"] == 0.45
    assert w["average_score_percent"] == "45%"
    assert w["status"] == "weakness"
    assert len(data["strengths"]) == 0


@pytest.mark.asyncio
async def test_student_insights_strict_student_isolation(client: AsyncClient, db_session) -> None:
    """Students cannot access or leak each other's diagnostic insights and weakness profiles."""
    teacher_token = await create_user_and_get_token(
        client, "t.iso.diag@viva.edu", "teacher", "Iso Teacher"
    )
    student_a_token = await create_user_and_get_token(
        client, "stud.a.diag@viva.edu", "student", "Student A"
    )
    student_b_token = await create_user_and_get_token(
        client, "stud.b.diag@viva.edu", "student", "Student B"
    )

    sa_me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {student_a_token}"})
    student_a_id = uuid.UUID(sa_me.json()["id"])

    course_res = await client.post(
        "/api/courses",
        headers={"Authorization": f"Bearer {teacher_token}"},
        json={"name": "Compiler Design", "code": "CS402", "description": "Compilers"},
    )
    course_id = uuid.UUID(course_res.json()["id"])

    topic = Topic(course_id=course_id, name="Lexical Analysis")
    db_session.add(topic)
    await db_session.commit()
    await db_session.refresh(topic)

    q = Question(
        topic_id=topic.id, question_text="What is a DFA?", expected_key_points=["deterministic"]
    )
    db_session.add(q)
    await db_session.commit()
    await db_session.refresh(q)

    # Session only for Student A
    session_a = VivaSession(
        student_id=student_a_id,
        course_id=course_id,
        status=VivaStatus.COMPLETED,
        max_questions=1,
        total_score=0.30,
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
    )
    db_session.add(session_a)
    await db_session.commit()
    await db_session.refresh(session_a)

    ans_a = Answer(
        session_id=session_a.id,
        question_id=q.id,
        sequence_number=1,
        fused_score=0.30,
    )
    db_session.add(ans_a)
    await db_session.commit()

    # Student B queries insights
    res_b = await client.get(
        "/api/viva/insights",
        headers={"Authorization": f"Bearer {student_b_token}"},
    )
    assert res_b.status_code == 200
    data_b = res_b.json()
    assert data_b["has_data"] is False
    assert data_b["weaknesses"] == []
    assert data_b["total_evaluated_sessions"] == 0

    # Student A queries insights
    res_a = await client.get(
        "/api/viva/insights",
        headers={"Authorization": f"Bearer {student_a_token}"},
    )
    assert res_a.status_code == 200
    data_a = res_a.json()
    assert data_a["has_data"] is True
    assert len(data_a["weaknesses"]) == 1
    assert data_a["weaknesses"][0]["topic_id"] == str(topic.id)


@pytest.mark.asyncio
async def test_teacher_analytics_class_weaknesses_detection(
    client: AsyncClient, db_session
) -> None:
    """Teacher analytics aggregate topic scores and flags class-wide weaknesses (<65%)."""
    t_token = await create_user_and_get_token(
        client, "t.cw@viva.edu", "teacher", "Class Weakness Teacher"
    )
    s1_token = await create_user_and_get_token(client, "s1.cw@viva.edu", "student", "CW Student 1")
    s2_token = await create_user_and_get_token(client, "s2.cw@viva.edu", "student", "CW Student 2")

    s1_me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {s1_token}"})
    s2_me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {s2_token}"})
    s1_id = uuid.UUID(s1_me.json()["id"])
    s2_id = uuid.UUID(s2_me.json()["id"])

    course_res = await client.post(
        "/api/courses",
        headers={"Authorization": f"Bearer {t_token}"},
        json={"name": "Database Systems", "code": "CS304", "description": "RDBMS"},
    )
    course_id = uuid.UUID(course_res.json()["id"])

    weak_topic = Topic(course_id=course_id, name="B+ Tree Indexing")
    good_topic = Topic(course_id=course_id, name="SQL Select & Joins")
    db_session.add_all([weak_topic, good_topic])
    await db_session.commit()
    await db_session.refresh(weak_topic)
    await db_session.refresh(good_topic)

    q_weak = Question(topic_id=weak_topic.id, question_text="Explain B+ tree leaf nodes.")
    q_good = Question(topic_id=good_topic.id, question_text="Explain Inner vs Outer join.")
    db_session.add_all([q_weak, q_good])
    await db_session.commit()
    await db_session.refresh(q_weak)
    await db_session.refresh(q_good)

    # Student 1 session
    sess1 = VivaSession(
        student_id=s1_id, course_id=course_id, status=VivaStatus.COMPLETED, total_score=0.60
    )
    # Student 2 session
    sess2 = VivaSession(
        student_id=s2_id, course_id=course_id, status=VivaStatus.COMPLETED, total_score=0.65
    )
    db_session.add_all([sess1, sess2])
    await db_session.commit()
    await db_session.refresh(sess1)
    await db_session.refresh(sess2)

    # Answers: B+ Tree scores: s1: 0.50, s2: 0.60 -> topic avg 0.55 (<65% -> class weakness)
    ans1_w = Answer(session_id=sess1.id, question_id=q_weak.id, sequence_number=1, fused_score=0.50)
    ans2_w = Answer(session_id=sess2.id, question_id=q_weak.id, sequence_number=1, fused_score=0.60)

    # Answers: SQL scores: s1: 0.85, s2: 0.85 -> topic avg 0.85 (not weakness)
    ans1_g = Answer(session_id=sess1.id, question_id=q_good.id, sequence_number=2, fused_score=0.85)
    ans2_g = Answer(session_id=sess2.id, question_id=q_good.id, sequence_number=2, fused_score=0.85)

    db_session.add_all([ans1_w, ans2_w, ans1_g, ans2_g])
    await db_session.commit()

    # Query /api/teacher/analytics
    analytics_res = await client.get(
        "/api/teacher/analytics",
        headers={"Authorization": f"Bearer {t_token}"},
    )
    assert analytics_res.status_code == 200
    data = analytics_res.json()

    assert "class_weaknesses" in data
    cw_list = data["class_weaknesses"]
    assert len(cw_list) == 1
    cw = cw_list[0]
    assert cw["topic_id"] == str(weak_topic.id)
    assert cw["topic_name"] == "B+ Tree Indexing"
    assert cw["average_score"] == 0.55
    assert cw["average_score_percent"] == "55%"
    assert cw["student_count"] == 2
    assert cw["attempt_count"] == 2
    assert cw["is_class_weakness"] is True
    assert "Class-wide review recommended" in cw["recommendation"]


@pytest.mark.asyncio
async def test_student_insights_unscored_and_in_progress_sessions_ignored_safely(
    client: AsyncClient, db_session
) -> None:
    """In-progress sessions and answers without fused scores or rubrics are ignored safely without errors."""
    teacher_token = await create_user_and_get_token(
        client, "t.unscored@viva.edu", "teacher", "Unscored Teacher"
    )
    student_token = await create_user_and_get_token(
        client, "s.unscored@viva.edu", "student", "Unscored Student"
    )

    s_me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {student_token}"})
    student_id = uuid.UUID(s_me.json()["id"])

    course_res = await client.post(
        "/api/courses",
        headers={"Authorization": f"Bearer {teacher_token}"},
        json={"name": "Software Architecture", "code": "CS450", "description": "Architecture"},
    )
    course_id = uuid.UUID(course_res.json()["id"])

    topic = Topic(course_id=course_id, name="Microservices & Monoliths")
    db_session.add(topic)
    await db_session.commit()
    await db_session.refresh(topic)

    q = Question(topic_id=topic.id, question_text="Compare microservices vs monoliths.")
    db_session.add(q)
    await db_session.commit()
    await db_session.refresh(q)

    # 1. In-progress session
    in_prog_sess = VivaSession(
        student_id=student_id,
        course_id=course_id,
        status=VivaStatus.IN_PROGRESS,
        max_questions=3,
        total_score=None,
    )
    db_session.add(in_prog_sess)
    await db_session.commit()
    await db_session.refresh(in_prog_sess)

    # 2. Completed session but with unscored answer
    comp_sess = VivaSession(
        student_id=student_id,
        course_id=course_id,
        status=VivaStatus.COMPLETED,
        max_questions=1,
        total_score=None,
    )
    db_session.add(comp_sess)
    await db_session.commit()
    await db_session.refresh(comp_sess)

    unscored_ans = Answer(
        session_id=comp_sess.id,
        question_id=q.id,
        sequence_number=1,
        transcript=None,
        fused_score=None,
        rubric_breakdown=None,
    )
    db_session.add(unscored_ans)
    await db_session.commit()

    res = await client.get(
        "/api/viva/insights",
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert res.status_code == 200
    data = res.json()
    # No scored answers -> has_data should be False
    assert data["has_data"] is False
    assert data["weaknesses"] == []
    assert data["strengths"] == []


@pytest.mark.asyncio
async def test_viva_start_with_targeted_topic(client: AsyncClient, db_session) -> None:
    """Starting a viva session with targeted topic_ids saves the topic filter into the session config."""
    teacher_token = await create_user_and_get_token(
        client, "t.target@viva.edu", "teacher", "Target Teacher"
    )
    student_token = await create_user_and_get_token(
        client, "s.target@viva.edu", "student", "Target Student"
    )

    course_res = await client.post(
        "/api/courses",
        headers={"Authorization": f"Bearer {teacher_token}"},
        json={"name": "Theory of Computation", "code": "CS350", "description": "TOC"},
    )
    course_id = uuid.UUID(course_res.json()["id"])

    t1 = Topic(course_id=course_id, name="Regular Languages & DFA")
    t2 = Topic(course_id=course_id, name="Turing Machines")
    db_session.add_all([t1, t2])
    await db_session.commit()
    await db_session.refresh(t1)
    await db_session.refresh(t2)

    # Add an approved question to t1
    q1 = Question(
        topic_id=t1.id,
        question_text="What defines a regular language?",
        expected_key_points=["finite automaton", "regular expression"],
        is_approved=True,
    )
    db_session.add(q1)
    await db_session.commit()

    # Student starts targeted viva for t1
    start_res = await client.post(
        "/api/viva/sessions",
        headers={"Authorization": f"Bearer {student_token}"},
        json={
            "course_id": str(course_id),
            "topic_ids": [str(t1.id)],
        },
    )
    assert start_res.status_code == 201
    session_data = start_res.json()
    assert str(session_data["course_id"]) == str(course_id)

    db_sess = await db_session.get(VivaSession, uuid.UUID(session_data["id"]))
    assert db_sess is not None
    assert db_sess.config["topic_ids"] == [str(t1.id)]
