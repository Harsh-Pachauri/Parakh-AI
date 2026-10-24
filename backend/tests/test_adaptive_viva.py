"""Tests for P2.13 — Adaptive AI Viva Engine."""

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient

from app.models.answer import Answer
from app.models.question import Question, QuestionDifficulty
from app.models.topic import Topic
from app.models.viva_session import VivaSession, VivaStatus
from app.services.adaptive_service import AdaptiveVivaService
from tests.test_courses import create_user_and_get_token


def test_adaptive_difficulty_progression_rules() -> None:
    """Difficulty progression adapts gradually, avoiding dramatic swings and falling back safely."""
    # 1. Baseline with no prior scores
    assert AdaptiveVivaService.compute_next_difficulty("medium", []) == QuestionDifficulty.MEDIUM
    assert AdaptiveVivaService.compute_next_difficulty("easy", []) == QuestionDifficulty.EASY
    assert AdaptiveVivaService.compute_next_difficulty("hard", []) == QuestionDifficulty.HARD
    # Baseline with poor historical performance starts foundational
    assert (
        AdaptiveVivaService.compute_next_difficulty("medium", [], historical_topic_avg=0.40)
        == QuestionDifficulty.EASY
    )

    # 2. Single answer does not cause dramatic swings
    assert AdaptiveVivaService.compute_next_difficulty("easy", [0.95]) == QuestionDifficulty.EASY
    assert AdaptiveVivaService.compute_next_difficulty("hard", [0.20]) == QuestionDifficulty.HARD
    assert (
        AdaptiveVivaService.compute_next_difficulty("medium", [0.90]) == QuestionDifficulty.MEDIUM
    )

    # 3. Two consecutive strong answers step up difficulty
    assert (
        AdaptiveVivaService.compute_next_difficulty("easy", [0.80, 0.85])
        == QuestionDifficulty.MEDIUM
    )
    assert (
        AdaptiveVivaService.compute_next_difficulty("medium", [0.82, 0.88])
        == QuestionDifficulty.HARD
    )
    assert (
        AdaptiveVivaService.compute_next_difficulty("hard", [0.90, 0.95]) == QuestionDifficulty.HARD
    )

    # 4. Two consecutive weak answers step down difficulty to reinforce foundations
    assert (
        AdaptiveVivaService.compute_next_difficulty("hard", [0.35, 0.40])
        == QuestionDifficulty.MEDIUM
    )
    assert (
        AdaptiveVivaService.compute_next_difficulty("medium", [0.45, 0.30])
        == QuestionDifficulty.EASY
    )
    assert (
        AdaptiveVivaService.compute_next_difficulty("easy", [0.40, 0.30]) == QuestionDifficulty.EASY
    )

    # 5. Mixed performance maintains steady difficulty
    assert (
        AdaptiveVivaService.compute_next_difficulty("medium", [0.90, 0.45])
        == QuestionDifficulty.MEDIUM
    )
    assert (
        AdaptiveVivaService.compute_next_difficulty("hard", [0.55, 0.70]) == QuestionDifficulty.HARD
    )


@pytest.mark.asyncio
async def test_weak_topic_prioritization_and_no_duplicates(client: AsyncClient, db_session) -> None:
    """The adaptive engine prioritizes weak topics and never asks duplicate questions in a session."""
    s_token = await create_user_and_get_token(
        client, "adapt.student@viva.edu", "student", "Adaptive Student"
    )
    t_token = await create_user_and_get_token(
        client, "adapt.teacher@viva.edu", "teacher", "Adaptive Teacher"
    )
    h_stu = {"Authorization": f"Bearer {s_token}"}
    h_teach = {"Authorization": f"Bearer {t_token}"}

    # Create Course and 2 Topics (Topic A: Weak, Topic B: Strong)
    c_res = await client.post(
        "/api/courses", headers=h_teach, json={"name": "Operating Systems", "code": "OS-301"}
    )
    course_id = uuid.UUID(c_res.json()["id"])

    t_weak_res = await client.post(
        f"/api/courses/{course_id}/topics",
        headers=h_teach,
        json={"name": "Memory Management", "sort_order": 1},
    )
    t_weak_id = uuid.UUID(t_weak_res.json()["id"])

    t_strong_res = await client.post(
        f"/api/courses/{course_id}/topics",
        headers=h_teach,
        json={"name": "Process Scheduling", "sort_order": 2},
    )
    t_strong_id = uuid.UUID(t_strong_res.json()["id"])

    # Populate question bank
    q1_res = await client.post(
        "/api/questions",
        headers=h_teach,
        json={
            "course_id": str(course_id),
            "topic_id": str(t_weak_id),
            "question_text": "What is paging and address translation?",
            "expected_key_points": ["Page table", "Virtual address", "Physical address"],
            "difficulty": "medium",
        },
    )
    q1_id = uuid.UUID(q1_res.json()["id"])

    q2_res = await client.post(
        "/api/questions",
        headers=h_teach,
        json={
            "course_id": str(course_id),
            "topic_id": str(t_weak_id),
            "question_text": "Explain page faults and page replacement algorithms.",
            "expected_key_points": ["Page fault interrupt", "LRU", "FIFO"],
            "difficulty": "hard",
        },
    )
    q2_id = uuid.UUID(q2_res.json()["id"])

    q3_res = await client.post(
        "/api/questions",
        headers=h_teach,
        json={
            "course_id": str(course_id),
            "topic_id": str(t_strong_id),
            "question_text": "Compare Round Robin with FCFS scheduling.",
            "expected_key_points": ["Time quantum", "Preemption", "Convoy effect"],
            "difficulty": "medium",
        },
    )
    q3_id = uuid.UUID(q3_res.json()["id"])

    # Get student user ID
    me_res = await client.get("/api/auth/me", headers=h_stu)
    student_id = uuid.UUID(me_res.json()["id"])

    # Simulate historical performance: Student performed weakly on Memory Management (score 0.40)
    # and strongly on Process Scheduling (score 0.90)
    hist_session = VivaSession(
        student_id=student_id,
        course_id=course_id,
        status=VivaStatus.COMPLETED,
        max_questions=2,
        current_question_index=2,
        total_score=0.65,
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
        config={"is_adaptive": True},
    )
    db_session.add(hist_session)
    await db_session.flush()

    ans_weak = Answer(
        session_id=hist_session.id,
        question_id=q1_id,
        sequence_number=1,
        transcript="I am not very sure about virtual memory page tables.",
        embedding_score=0.40,
        llm_score=0.40,
        fused_score=0.40,
        rubric_breakdown={"correctness": 4.0, "completeness": 3.0, "clarity": 5.0},
    )
    ans_strong = Answer(
        session_id=hist_session.id,
        question_id=q3_id,
        sequence_number=2,
        transcript="Round Robin uses a fixed time slice to prevent CPU hogging and convoy effect.",
        embedding_score=0.90,
        llm_score=0.90,
        fused_score=0.90,
        rubric_breakdown={"correctness": 9.0, "completeness": 9.0, "clarity": 9.0},
    )
    db_session.add_all([ans_weak, ans_strong])
    await db_session.commit()

    # Verify student topic performance
    topic_perf = await AdaptiveVivaService.get_student_topic_performance(
        db_session, student_id, course_id
    )
    assert topic_perf[t_weak_id]["status"] == "weak"
    assert topic_perf[t_weak_id]["avg_score"] == 0.40
    assert topic_perf[t_strong_id]["status"] == "strong"
    assert topic_perf[t_strong_id]["avg_score"] == 0.90

    # Start a new practice viva session
    start_res = await client.post(
        "/api/viva/sessions",
        headers=h_stu,
        json={
            "course_id": str(course_id),
            "max_questions": 3,
        },
    )
    assert start_res.status_code == 201
    s_data = start_res.json()
    assert s_data["is_adaptive"] is True
    session_id = uuid.UUID(s_data["id"])

    # First question fetched should prioritize the weak topic (Memory Management)
    next_q1_res = await client.post(f"/api/viva/sessions/{session_id}/next", headers=h_stu)
    assert next_q1_res.status_code == 200
    q1_fetched = next_q1_res.json()
    # It must select a question from the weak topic
    assert q1_fetched["question_id"] in [str(q1_id), str(q2_id)]

    # Fetching again should NOT duplicate the same question
    next_q2_res = await client.post(f"/api/viva/sessions/{session_id}/next", headers=h_stu)
    assert next_q2_res.status_code == 200
    q2_fetched = next_q2_res.json()
    assert q2_fetched["question_id"] != q1_fetched["question_id"]


@pytest.mark.asyncio
async def test_difficulty_fallback_when_preferred_level_empty(
    client: AsyncClient, db_session
) -> None:
    """When questions at the preferred difficulty are exhausted, fallback to suitable alternatives."""
    t_token = await create_user_and_get_token(
        client, "fb.teacher@viva.edu", "teacher", "Fallback Teacher"
    )
    s_token = await create_user_and_get_token(
        client, "fb.student@viva.edu", "student", "Fallback Student"
    )
    h_teach = {"Authorization": f"Bearer {t_token}"}
    h_stu = {"Authorization": f"Bearer {s_token}"}

    c_res = await client.post(
        "/api/courses", headers=h_teach, json={"name": "Discrete Math", "code": "DM-101"}
    )
    course_id = uuid.UUID(c_res.json()["id"])

    t_res = await client.post(
        f"/api/courses/{course_id}/topics",
        headers=h_teach,
        json={"name": "Graph Theory", "sort_order": 1},
    )
    topic_id = uuid.UUID(t_res.json()["id"])

    # Create ONLY an EASY question and HARD question (NO medium question)
    q_easy_res = await client.post(
        "/api/questions",
        headers=h_teach,
        json={
            "course_id": str(course_id),
            "topic_id": str(topic_id),
            "question_text": "What is a vertex and edge?",
            "expected_key_points": ["Node", "Connection"],
            "difficulty": "easy",
        },
    )
    q_easy_id = uuid.UUID(q_easy_res.json()["id"])

    me_res = await client.get("/api/auth/me", headers=h_stu)
    student_id = uuid.UUID(me_res.json()["id"])

    # Start session requesting medium difficulty
    session = VivaSession(
        student_id=student_id,
        course_id=course_id,
        status=VivaStatus.IN_PROGRESS,
        max_questions=2,
        current_question_index=0,
        config={"is_adaptive": True, "difficulty": "medium", "asked_question_ids": []},
    )
    db_session.add(session)
    await db_session.commit()
    await db_session.refresh(session)

    # Calling select_adaptive_question with target_difficulty=MEDIUM
    topic_obj = await db_session.get(Topic, topic_id)
    selected_q = await AdaptiveVivaService.select_adaptive_question(
        db=db_session,
        session=session,
        topic=topic_obj,
        target_difficulty=QuestionDifficulty.MEDIUM,
        exclude_question_ids=set(),
    )
    # Must successfully fall back to the available easy question rather than failing or returning None
    assert selected_q is not None
    assert selected_q.id == q_easy_id


@pytest.mark.asyncio
async def test_adaptive_session_summary_generation_and_access(
    client: AsyncClient, db_session
) -> None:
    """Adaptive sessions produce learning summaries with difficulty progression, improvement tracking, and auth guards."""
    s_token = await create_user_and_get_token(
        client, "sum.student@viva.edu", "student", "Summary Student"
    )
    s2_token = await create_user_and_get_token(
        client, "other.student@viva.edu", "student", "Other Student"
    )
    t_token = await create_user_and_get_token(
        client, "sum.teacher@viva.edu", "teacher", "Summary Teacher"
    )
    h_stu = {"Authorization": f"Bearer {s_token}"}
    h_other = {"Authorization": f"Bearer {s2_token}"}
    h_teach = {"Authorization": f"Bearer {t_token}"}

    c_res = await client.post(
        "/api/courses", headers=h_teach, json={"name": "Database Systems", "code": "DB-401"}
    )
    course_id = uuid.UUID(c_res.json()["id"])

    t1_res = await client.post(
        f"/api/courses/{course_id}/topics",
        headers=h_teach,
        json={"name": "Indexing", "sort_order": 1},
    )
    t1_id = uuid.UUID(t1_res.json()["id"])

    t2_res = await client.post(
        f"/api/courses/{course_id}/topics",
        headers=h_teach,
        json={"name": "Concurrency", "sort_order": 2},
    )
    t2_id = uuid.UUID(t2_res.json()["id"])

    q1 = Question(
        topic_id=t1_id,
        question_text="What is a B+ tree index?",
        expected_key_points=["Balanced", "Leaf nodes linked"],
        difficulty=QuestionDifficulty.MEDIUM,
        is_approved=True,
    )
    q2 = Question(
        topic_id=t1_id,
        question_text="How does clustered index differ from secondary index?",
        expected_key_points=["Physical sort", "Pointer table"],
        difficulty=QuestionDifficulty.HARD,
        is_approved=True,
    )
    q3 = Question(
        topic_id=t2_id,
        question_text="Explain 2-Phase Locking.",
        expected_key_points=["Growing phase", "Shrinking phase"],
        difficulty=QuestionDifficulty.MEDIUM,
        is_approved=True,
    )
    db_session.add_all([q1, q2, q3])
    await db_session.commit()

    me_res = await client.get("/api/auth/me", headers=h_stu)
    student_id = uuid.UUID(me_res.json()["id"])

    session = VivaSession(
        student_id=student_id,
        course_id=course_id,
        status=VivaStatus.IN_PROGRESS,
        max_questions=3,
        current_question_index=3,
        config={
            "is_adaptive": True,
            "difficulty_progression": ["medium", "hard", "medium"],
            "topics_practiced": ["Indexing", "Concurrency"],
        },
    )
    db_session.add(session)
    await db_session.flush()

    # Answers: Indexing improved (0.60 -> 0.85), Concurrency struggled (0.45)
    a1 = Answer(
        session_id=session.id,
        question_id=q1.id,
        sequence_number=1,
        transcript="B+ trees are self-balancing trees.",
        fused_score=0.60,
        rubric_breakdown={"correctness": 6.0, "completeness": 5.0, "clarity": 7.0},
    )
    a2 = Answer(
        session_id=session.id,
        question_id=q2.id,
        sequence_number=2,
        transcript="Clustered index determines the physical order of data rows on disk.",
        fused_score=0.85,
        rubric_breakdown={"correctness": 9.0, "completeness": 8.0, "clarity": 8.5},
    )
    a3 = Answer(
        session_id=session.id,
        question_id=q3.id,
        sequence_number=3,
        transcript="I don't know much about phase locking.",
        fused_score=0.45,
        rubric_breakdown={"correctness": 4.0, "completeness": 3.0, "clarity": 5.0},
    )
    db_session.add_all([a1, a2, a3])
    await db_session.commit()

    # Finish session via API
    finish_res = await client.post(f"/api/viva/sessions/{session.id}/finish", headers=h_stu)
    assert finish_res.status_code == 200
    f_data = finish_res.json()
    assert f_data["status"] == "completed"

    # Retrieve adaptive summary
    sum_res = await client.get(f"/api/viva/sessions/{session.id}/adaptive-summary", headers=h_stu)
    assert sum_res.status_code == 200
    summary = sum_res.json()

    assert summary["is_adaptive"] is True
    assert summary["difficulty_progression"] == ["medium", "hard", "medium"]
    assert len(summary["topics_practiced"]) >= 2

    # Improvement in Indexing (0.60 -> 0.85) should be detected
    assert any(item["topic_name"] == "Indexing" for item in summary["topics_showing_improvement"])

    # Concurrency (0.45) should be marked as needing attention
    assert any(item["topic_name"] == "Concurrency" for item in summary["topics_needing_attention"])

    # Suggestions should prioritize Concurrency
    assert any(s["topic_name"] == "Concurrency" for s in summary["suggested_next_topics"])

    # Unauthorized access rejection: Another student cannot access this summary
    other_res = await client.get(
        f"/api/viva/sessions/{session.id}/adaptive-summary", headers=h_other
    )
    assert other_res.status_code == 403

    # Course teacher can access it
    teach_res = await client.get(
        f"/api/viva/sessions/{session.id}/adaptive-summary", headers=h_teach
    )
    assert teach_res.status_code == 200


@pytest.mark.asyncio
async def test_fixed_assessment_and_assignment_remain_unaffected(
    client: AsyncClient, db_session
) -> None:
    """Custom assessments and scheduled assignments remain completely static and un-adaptive."""
    t_token = await create_user_and_get_token(
        client, "fixed.teach@viva.edu", "teacher", "Fixed Teacher"
    )
    s_token = await create_user_and_get_token(
        client, "fixed.stu@viva.edu", "student", "Fixed Student"
    )
    h_teach = {"Authorization": f"Bearer {t_token}"}
    h_stu = {"Authorization": f"Bearer {s_token}"}

    c_res = await client.post(
        "/api/courses", headers=h_teach, json={"name": "Software Engineering", "code": "SE-202"}
    )
    course_id = uuid.UUID(c_res.json()["id"])

    t_res = await client.post(
        f"/api/courses/{course_id}/topics",
        headers=h_teach,
        json={"name": "Design Patterns", "sort_order": 1},
    )
    topic_id = uuid.UUID(t_res.json()["id"])

    q1_res = await client.post(
        "/api/questions",
        headers=h_teach,
        json={
            "course_id": str(course_id),
            "topic_id": str(topic_id),
            "question_text": "Explain Singleton pattern.",
            "expected_key_points": ["Single instance"],
            "difficulty": "easy",
        },
    )
    q1_id = uuid.UUID(q1_res.json()["id"])

    q2_res = await client.post(
        "/api/questions",
        headers=h_teach,
        json={
            "course_id": str(course_id),
            "topic_id": str(topic_id),
            "question_text": "Explain Factory pattern.",
            "expected_key_points": ["Interface", "Subclasses decide"],
            "difficulty": "medium",
        },
    )
    q2_id = uuid.UUID(q2_res.json()["id"])

    # Create published assessment with fixed question order [q2, q1]
    asst_res = await client.post(
        "/api/assessments",
        headers=h_teach,
        json={
            "course_id": str(course_id),
            "title": "Design Patterns Midterm",
            "question_ids": [str(q2_id), str(q1_id)],
            "duration_minutes": 15,
            "is_published": True,
        },
    )
    asst_id = uuid.UUID(asst_res.json()["id"])

    # Student starts assessment session
    start_res = await client.post(
        "/api/viva/sessions",
        headers=h_stu,
        json={
            "assessment_id": str(asst_id),
        },
    )
    assert start_res.status_code == 201
    s_data = start_res.json()
    assert s_data["is_adaptive"] is False
    assert s_data["practice_mode"] == "fixed"
    session_id = uuid.UUID(s_data["id"])

    # First question MUST be q2 (the teacher's explicitly configured first question)
    next_q1_res = await client.post(f"/api/viva/sessions/{session_id}/next", headers=h_stu)
    assert next_q1_res.status_code == 200
    assert next_q1_res.json()["question_id"] == str(q2_id)

    # Second question MUST be q1 (the teacher's explicitly configured second question)
    next_q2_res = await client.post(f"/api/viva/sessions/{session_id}/next", headers=h_stu)
    assert next_q2_res.status_code == 200
    assert next_q2_res.json()["question_id"] == str(q1_id)
