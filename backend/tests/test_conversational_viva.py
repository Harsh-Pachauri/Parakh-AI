"""Tests for P2.14 — Humanized AI Viva Experience."""

import uuid

import pytest
from httpx import AsyncClient

from app.services.conversational_service import ConversationalService
from tests.test_courses import create_user_and_get_token


def test_conversational_acknowledgements_accuracy_and_tone() -> None:
    """Acknowledgements strictly reflect evaluation results without false praise or harsh criticism."""
    # Strong answers (>= 0.75) receive positive recognition of key concepts
    for score in [0.75, 0.85, 0.95]:
        ack = ConversationalService.get_empathetic_acknowledgement(
            score, "A complete, thorough answer explaining the concept."
        )
        assert any(
            phrase in ack
            for phrase in [
                "Well explained",
                "Great response",
                "Nicely explained",
                "Good explanation",
            ]
        )
        assert not any(bad in ack for bad in ["tricky", "No worries", "tough one"])

    # Partially correct answers (0.50 - 0.74) receive encouraging, constructive notes
    for score in [0.50, 0.60, 0.70]:
        ack = ConversationalService.get_empathetic_acknowledgement(
            score, "A partial explanation touching some points."
        )
        assert any(
            phrase in ack
            for phrase in ["right track", "Good effort", "basic concept", "Solid attempt"]
        )
        assert not any(bad in ack for bad in ["Well explained", "tricky", "No worries"])

    # Incorrect or struggling answers (< 0.50) are supportive without claiming correctness
    for score in [0.10, 0.35, 0.45]:
        ack = ConversationalService.get_empathetic_acknowledgement(
            score, "I think maybe it is something else."
        )
        assert any(
            phrase in ack
            for phrase in ["No worries", "tough one", "Good try", "giving that a shot"]
        )
        # Crucial: Never falsely claim the answer was well explained
        assert not any(
            false_praise in ack
            for false_praise in ["Well explained", "Great response", "Nicely explained"]
        )

    # Very short or unclear answers (< 15 chars)
    ack_short = ConversationalService.get_empathetic_acknowledgement(0.5, "yes")
    assert "trying to explain" in ack_short or "thought process" in ack_short


def test_conversational_transitions_by_context() -> None:
    """Transitions naturally bridge question changes based on difficulty and topic shifts."""
    # Stepping up difficulty after strong score
    step_up = ConversationalService.get_conversational_transition(
        prev_difficulty="medium", next_difficulty="hard", is_same_topic=False, score=0.85
    )
    assert any(w in step_up for w in ["challenging", "step further", "momentum"])

    # Stepping down difficulty to foundational level
    step_down = ConversationalService.get_conversational_transition(
        prev_difficulty="hard", next_difficulty="medium", is_same_topic=False, score=0.40
    )
    assert any(w in step_down for w in ["foundational", "step back", "core principle"])

    # Revisiting weak topic
    revisit = ConversationalService.get_conversational_transition(
        prev_difficulty="medium",
        next_difficulty="medium",
        is_same_topic=False,
        is_revisiting=True,
        score=0.60,
    )
    assert any(w in revisit for w in ["revisit an idea", "check your understanding"])

    # Same topic continuation
    same_top = ConversationalService.get_conversational_transition(
        prev_difficulty="medium",
        next_difficulty="medium",
        is_same_topic=True,
        is_revisiting=False,
        score=0.70,
    )
    assert any(
        w in same_top for w in ["build on that idea", "another angle", "stay with this topic"]
    )


def test_viva_openings_and_closings() -> None:
    """Openings and closings personalize gracefully and respect assessment mode."""
    # Practice opening
    opening = ConversationalService.get_viva_opening(student_name="Ananya Sen", is_adaptive=True)
    assert "Ananya" in opening
    assert any(w in opening for w in ["relax", "thinking", "warm-up", "learn as we go"])

    # Assessment opening
    asst_opening = ConversationalService.get_viva_opening(
        student_name="Ananya Sen", is_adaptive=False, assessment_title="Data Structures Midterm"
    )
    assert "Data Structures Midterm" in asst_opening
    assert "Ananya" in asst_opening

    # High score closing
    closing_high = ConversationalService.get_session_closing_message(
        0.85, student_name="Ananya Sen", answer_count=4
    )
    assert "Ananya" in closing_high
    assert "mastery" in closing_high or "confidence" in closing_high

    # Developing score closing (supportive, encouraging next practice)
    closing_dev = ConversationalService.get_session_closing_message(
        0.40, student_name="Ananya Sen", answer_count=4
    )
    assert "Ananya" in closing_dev
    assert "showing up" in closing_dev or "great start" in closing_dev
    assert "mastery" not in closing_dev


@pytest.mark.asyncio
async def test_viva_api_next_and_turn_humanized_integration(
    client: AsyncClient, db_session, monkeypatch
) -> None:
    """The viva API endpoints incorporate warm greetings, empathetic feedback, and natural bridges."""
    t_token = await create_user_and_get_token(
        client, "hum.teacher@viva.edu", "teacher", "Human Teacher"
    )
    s_token = await create_user_and_get_token(
        client, "hum.student@viva.edu", "student", "Aarav Sharma"
    )
    h_teach = {"Authorization": f"Bearer {t_token}"}
    h_stu = {"Authorization": f"Bearer {s_token}"}

    c_res = await client.post(
        "/api/courses", headers=h_teach, json={"name": "Compiler Design", "code": "CD-401"}
    )
    course_id = uuid.UUID(c_res.json()["id"])

    t_res = await client.post(
        f"/api/courses/{course_id}/topics",
        headers=h_teach,
        json={"name": "Parsing", "sort_order": 1},
    )
    topic_id = uuid.UUID(t_res.json()["id"])

    q1_res = await client.post(
        "/api/questions",
        headers=h_teach,
        json={
            "course_id": str(course_id),
            "topic_id": str(topic_id),
            "question_text": "What is LL(1) parsing?",
            "expected_key_points": ["Top-down", "Lookahead of 1"],
            "difficulty": "medium",
        },
    )
    q1_id = uuid.UUID(q1_res.json()["id"])

    # Start session as student
    start_res = await client.post(
        "/api/viva/sessions",
        headers=h_stu,
        json={
            "course_id": str(course_id),
            "max_questions": 1,
        },
    )
    assert start_res.status_code == 201
    session_id = start_res.json()["id"]

    # First question fetched on /next should contain a warm opening greeting
    next_res = await client.post(f"/api/viva/sessions/{session_id}/next", headers=h_stu)
    assert next_res.status_code == 200
    q_data = next_res.json()
    assert q_data["opening_greeting"] is not None
    assert "Aarav" in q_data["opening_greeting"]

    # Submit an answer on /turn (mock evaluate_answer)
    async def mock_eval(**kwargs):
        return {
            "embedding_score": 0.85,
            "llm_score": 0.85,
            "fused_score": 0.85,
            "rubric": {"correctness": 9.0, "completeness": 8.0, "clarity": 8.5},
        }

    monkeypatch.setattr("app.api.viva.evaluate_answer", mock_eval)

    turn_res = await client.post(
        f"/api/viva/sessions/{session_id}/turn",
        headers=h_stu,
        json={
            "question_id": str(q1_id),
            "transcript": "LL(1) parsing is a top-down predictive parsing method using 1 lookahead token.",
        },
    )
    assert turn_res.status_code == 200
    turn_data = turn_res.json()
    assert turn_data["completed"] is True
    # Closing interviewer text should be warm and supportive
    assert "Aarav" in turn_data["interviewer_text"]
    assert any(
        w in turn_data["interviewer_text"]
        for w in ["mastery", "confidence", "Well done", "concludes"]
    )
