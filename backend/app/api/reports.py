"""Teacher session review, analytics, and CSV export endpoints."""

import csv
import io
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_db, require_role
from app.models.answer import Answer
from app.models.course import Course
from app.models.question import Question
from app.models.score_override import ScoreOverride
from app.models.topic import Topic
from app.models.user import User, UserRole
from app.models.viva_session import VivaSession, VivaStatus
from app.services.pdf_service import generate_class_report_pdf, generate_student_report_pdf

router = APIRouter(tags=["Reports"])


async def _session(db: AsyncSession, session_id: uuid.UUID) -> VivaSession:
    result = await db.execute(
        select(VivaSession)
        .options(
            selectinload(VivaSession.answers).selectinload(Answer.question),
            selectinload(VivaSession.answers).selectinload(Answer.score_override),
            selectinload(VivaSession.student),
            selectinload(VivaSession.course),
        )
        .where(VivaSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


def _check_access(session: VivaSession, user: User) -> None:
    if user.role == UserRole.STUDENT and session.student_id != user.id:
        raise HTTPException(status_code=403, detail="You do not have access to this session")
    if user.role == UserRole.TEACHER and session.course.teacher_id != user.id:
        raise HTTPException(status_code=403, detail="You do not have access to this session")


def _serialize(session: VivaSession) -> dict:
    return {
        "id": str(session.id),
        "session_id": str(session.id),
        "student_id": str(session.student_id),
        "student_name": session.student.full_name if session.student else "Student",
        "student_email": session.student.email if session.student else "",
        "course_id": str(session.course_id),
        "course_name": session.course.name if session.course else "",
        "course_code": session.course.code if session.course else "",
        "status": session.status.value,
        "total_score": session.total_score,
        "created_at": session.created_at.isoformat(),
        "started_at": session.started_at.isoformat() if session.started_at else None,
        "finished_at": session.finished_at.isoformat() if session.finished_at else None,
        "behavior_flags": (session.config or {}).get("behavior_flags", []),
        "is_adaptive": (session.config or {}).get("is_adaptive", False),
        "practice_mode": (session.config or {}).get("practice_mode", "standard"),
        "adaptive_summary": (session.config or {}).get("adaptive_summary"),
        "difficulty_progression": (session.config or {}).get("difficulty_progression", []),
        "answers": [
            {
                "id": str(a.id),
                "question_id": str(a.question_id),
                "question_text": a.question.question_text,
                "transcript": a.transcript,
                "embedding_score": a.embedding_score,
                "llm_score": a.llm_score,
                "fused_score": a.fused_score,
                "rubric_breakdown": a.rubric_breakdown,
                "override_score": a.score_override.override_score if a.score_override else None,
                "override_justification": a.score_override.justification
                if a.score_override
                else None,
                "audio_url": (
                    f"/api/viva/sessions/{session.id}/answers/{a.id}/audio"
                    if a.audio_path
                    else None
                ),
            }
            for a in session.answers
        ],
    }


@router.get("/viva/sessions/{session_id}/report")
async def get_report(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    session = await _session(db, session_id)
    _check_access(session, user)
    return _serialize(session)


def _normalize_utc_dt(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def _calculate_score_distribution(scores: list[float]) -> dict[str, Any]:
    total = len(scores)
    if total == 0:
        return {
            "mastery": 0,
            "mastery_pct": "0%",
            "proficient": 0,
            "proficient_pct": "0%",
            "developing": 0,
            "developing_pct": "0%",
            "attention": 0,
            "attention_pct": "0%",
        }
    m = sum(1 for s in scores if s >= 0.80)
    p = sum(1 for s in scores if 0.65 <= s < 0.80)
    d = sum(1 for s in scores if 0.50 <= s < 0.65)
    a = sum(1 for s in scores if s < 0.50)
    return {
        "mastery": m,
        "mastery_pct": f"{round(m / total * 100)}%",
        "proficient": p,
        "proficient_pct": f"{round(p / total * 100)}%",
        "developing": d,
        "developing_pct": f"{round(d / total * 100)}%",
        "attention": a,
        "attention_pct": f"{round(a / total * 100)}%",
    }


def _build_student_performance_data(
    student: User,
    sessions: list[VivaSession],
    course: Course | None = None,
) -> dict[str, Any]:
    """Calculate thorough student performance metrics, rubric dimensions, topics, and attempt history."""
    total_sessions = len(sessions)
    completed_sessions = [s for s in sessions if s.status == VivaStatus.COMPLETED]
    in_progress_sessions = [s for s in sessions if s.status != VivaStatus.COMPLETED]
    scored_sessions = [
        s for s in completed_sessions if (s.total_score is not None or s.total_score is not None)
    ]

    scores = [
        float(s.total_score if s.total_score is not None else s.total_score)
        for s in scored_sessions
    ]
    avg_score = round(sum(scores) / len(scores), 4) if scores else None
    avg_score_pct = f"{round(avg_score * 100)}%" if avg_score is not None else "—"

    # Rubric Dimensions across all answers in completed sessions
    all_answers: list[Answer] = [a for s in completed_sessions for a in s.answers]
    cor_scores: list[float] = []
    cmp_scores: list[float] = []
    cla_scores: list[float] = []

    for a in all_answers:
        rb = a.rubric_breakdown or {}
        if "correctness" in rb and rb["correctness"] is not None:
            cor_scores.append(float(rb["correctness"]))
        if "completeness" in rb and rb["completeness"] is not None:
            cmp_scores.append(float(rb["completeness"]))
        if "clarity" in rb and rb["clarity"] is not None:
            cla_scores.append(float(rb["clarity"]))

    dim_averages = {
        "correctness": round(sum(cor_scores) / len(cor_scores), 4) if cor_scores else None,
        "completeness": round(sum(cmp_scores) / len(cmp_scores), 4) if cmp_scores else None,
        "clarity": round(sum(cla_scores) / len(cla_scores), 4) if cla_scores else None,
    }

    # Score History (Chronological)
    sorted_scored = sorted(
        scored_sessions,
        key=lambda s: (
            s.created_at.timestamp()
            if s.created_at.tzinfo
            else s.created_at.replace(tzinfo=UTC).timestamp()
        ),
    )
    score_history = [
        {
            "session_id": str(s.id),
            "date": s.created_at.isoformat() if s.created_at else None,
            "score": float(s.total_score if s.total_score is not None else s.total_score),
            "score_percent": f"{round(float(s.total_score if s.total_score is not None else s.total_score) * 100)}%",
            "course_name": s.course.name if s.course else None,
            "course_code": s.course.code if s.course else None,
            "title": (s.config or {}).get("assignment_title")
            or (s.config or {}).get("assessment_title")
            or "Practice Viva",
        }
        for s in sorted_scored
    ]

    # Topic Breakdown
    topic_map: dict[str, dict[str, Any]] = {}
    for s in completed_sessions:
        for a in s.answers:
            if a.question and a.question.topic:
                t = a.question.topic
                tid = str(t.id)
                if tid not in topic_map:
                    topic_map[tid] = {
                        "topic_id": tid,
                        "topic_name": t.name,
                        "course_id": str(t.course_id),
                        "course_name": s.course.name if s.course else "",
                        "course_code": s.course.code if s.course else "",
                        "evaluated_count": 0,
                        "_scores": [],
                        "_correctness": [],
                        "_completeness": [],
                        "_clarity": [],
                    }
                ans_score = (
                    a.score_override.override_score
                    if a.score_override and a.score_override.override_score is not None
                    else a.fused_score
                )
                if ans_score is not None:
                    topic_map[tid]["_scores"].append(float(ans_score))
                    topic_map[tid]["evaluated_count"] += 1
                rb = a.rubric_breakdown or {}
                if "correctness" in rb and rb["correctness"] is not None:
                    topic_map[tid]["_correctness"].append(float(rb["correctness"]))
                if "completeness" in rb and rb["completeness"] is not None:
                    topic_map[tid]["_completeness"].append(float(rb["completeness"]))
                if "clarity" in rb and rb["clarity"] is not None:
                    topic_map[tid]["_clarity"].append(float(rb["clarity"]))

    topic_breakdown = []
    strengths = []
    weaknesses = []
    developing = []

    for t_data in topic_map.values():
        t_scores = t_data.pop("_scores")
        t_cor = t_data.pop("_correctness")
        t_cmp = t_data.pop("_completeness")
        t_cla = t_data.pop("_clarity")

        t_avg = round(sum(t_scores) / len(t_scores), 4) if t_scores else None
        t_avg_pct = f"{round(t_avg * 100)}%" if t_avg is not None else "—"

        # Determine primary gap
        primary_gap = "Reinforce core definitions and complete reasoning."
        if t_cmp and t_cor and (sum(t_cmp) / len(t_cmp)) < (sum(t_cor) / len(t_cor)):
            primary_gap = "Completeness: expands key technical points and elaborates with examples."
        elif t_cla and (sum(t_cla) / len(t_cla)) < 0.65:
            primary_gap = "Spoken Clarity: articulate answers with direct, structured phrasing."

        t_entry = {
            **t_data,
            "average_score": t_avg,
            "average_score_percent": t_avg_pct,
            "primary_gap": primary_gap,
            "dimension_averages": {
                "correctness": round(sum(t_cor) / len(t_cor), 4) if t_cor else None,
                "completeness": round(sum(t_cmp) / len(t_cmp), 4) if t_cmp else None,
                "clarity": round(sum(t_cla) / len(t_cla), 4) if t_cla else None,
            },
        }

        if t_avg is not None:
            if t_avg < 0.65:
                t_entry["status"] = "weakness"
                weaknesses.append(t_entry)
            elif t_avg >= 0.80:
                t_entry["status"] = "strength"
                strengths.append(t_entry)
            else:
                t_entry["status"] = "developing"
                developing.append(t_entry)
        else:
            t_entry["status"] = "developing"
            developing.append(t_entry)

        topic_breakdown.append(t_entry)

    topic_breakdown.sort(
        key=lambda t: t["average_score"] if t["average_score"] is not None else 0.0
    )
    weaknesses.sort(key=lambda t: t["average_score"] if t["average_score"] is not None else 0.0)
    strengths.sort(
        key=lambda t: t["average_score"] if t["average_score"] is not None else 1.0, reverse=True
    )

    # Recent attempts
    recent_attempts = []
    for s in sessions[:25]:
        s_score = s.total_score if s.total_score is not None else s.total_score
        cfg = s.config or {}
        if cfg.get("assignment_id"):
            att_type = "assignment"
            att_title = cfg.get("assignment_title") or "Scheduled Assignment"
        elif cfg.get("assessment_id"):
            att_type = "custom_assessment"
            att_title = cfg.get("assessment_title") or "Custom Viva Exam"
        else:
            att_type = "practice"
            att_title = f"{s.course.name} Practice Viva" if s.course else "Oral Exam Practice"

        recent_attempts.append(
            {
                "session_id": str(s.id),
                "title": att_title,
                "type": att_type,
                "course_id": str(s.course_id),
                "course_name": s.course.name if s.course else None,
                "course_code": s.course.code if s.course else None,
                "status": s.status.value,
                "score": float(s_score) if s_score is not None else None,
                "score_percent": f"{round(float(s_score) * 100)}%" if s_score is not None else "—",
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "finished_at": s.finished_at.isoformat() if s.finished_at else None,
                "report_url": f"/report/{s.id}",
            }
        )

    # Coaching summary
    if not scored_sessions:
        coaching = "No completed oral examination attempts recorded yet. Start a viva session to generate diagnostic analytics."
    elif weaknesses:
        w_top = weaknesses[0]
        coaching = (
            f"Prioritize practicing '{w_top['topic_name']}' ({w_top['average_score_percent']}). "
            f"Focus area: {w_top['primary_gap']}"
        )
    elif developing:
        d_top = developing[0]
        coaching = (
            f"Solid foundation! Deepen comprehension in '{d_top['topic_name']}' ({d_top['average_score_percent']}) "
            "to transition your oral responses into the mastery tier."
        )
    else:
        coaching = "Superb oral mastery demonstrated across all evaluated topics. Continue regular review to sustain fluency."

    return {
        "student": {
            "id": str(student.id),
            "full_name": student.full_name,
            "email": student.email,
        },
        "course_scope": {
            "course_id": str(course.id) if course else None,
            "course_name": course.name if course else "All Enrolled Courses",
            "course_code": course.code if course else None,
        },
        "overall": {
            "total_sessions": total_sessions,
            "completed_sessions": len(completed_sessions),
            "in_progress_sessions": len(in_progress_sessions),
            "total_evaluated_answers": len(all_answers),
            "average_score": avg_score,
            "average_score_percent": avg_score_pct,
            "dimension_averages": dim_averages,
        },
        "score_history": score_history,
        "topic_breakdown": topic_breakdown,
        "strengths": strengths,
        "weaknesses": weaknesses,
        "developing": developing,
        "recent_attempts": recent_attempts,
        "coaching_summary": coaching,
    }


@router.get("/teacher/sessions")
async def teacher_sessions(
    course_id: uuid.UUID | None = Query(default=None),
    student_id: uuid.UUID | None = Query(default=None),
    user: User = Depends(require_role(UserRole.TEACHER, UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """List sessions accessible to this teacher with optional course and student filtering."""
    query = (
        select(VivaSession)
        .options(
            selectinload(VivaSession.answers).selectinload(Answer.question),
            selectinload(VivaSession.answers).selectinload(Answer.score_override),
            selectinload(VivaSession.student),
            selectinload(VivaSession.course),
        )
        .order_by(VivaSession.created_at.desc())
    )
    if user.role == UserRole.TEACHER:
        query = query.join(Course, VivaSession.course_id == Course.id).where(
            Course.teacher_id == user.id
        )

    if course_id:
        course_result = await db.execute(select(Course).where(Course.id == course_id))
        course = course_result.scalar_one_or_none()
        if course is None:
            raise HTTPException(status_code=404, detail="Course not found")
        if user.role == UserRole.TEACHER and course.teacher_id != user.id:
            raise HTTPException(
                status_code=403, detail="You do not have access to this course sessions"
            )
        query = query.where(VivaSession.course_id == course_id)

    if student_id:
        query = query.where(VivaSession.student_id == student_id)

    sessions = (await db.execute(query)).scalars().unique().all()
    return [{k: v for k, v in _serialize(s).items() if k != "answers"} for s in sessions]


@router.get("/teacher/analytics")
async def teacher_analytics(
    course_id: uuid.UUID | None = Query(default=None),
    from_date: datetime | None = Query(default=None),
    to_date: datetime | None = Query(default=None),
    user: User = Depends(require_role(UserRole.TEACHER, UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Class and student performance analytics for authorized courses."""
    if course_id:
        course_result = await db.execute(select(Course).where(Course.id == course_id))
        course = course_result.scalar_one_or_none()
        if course is None:
            raise HTTPException(status_code=404, detail="Course not found")
        if user.role == UserRole.TEACHER and course.teacher_id != user.id:
            raise HTTPException(
                status_code=403, detail="You do not have access to this course analytics"
            )

    courses_query = select(Course).order_by(Course.created_at.desc())
    if user.role == UserRole.TEACHER:
        courses_query = courses_query.where(Course.teacher_id == user.id)
    if course_id:
        courses_query = courses_query.where(Course.id == course_id)

    authorized_courses = (await db.execute(courses_query)).scalars().all()
    authorized_course_ids = [c.id for c in authorized_courses]

    if not authorized_course_ids:
        return {
            "summary": {
                "total_students": 0,
                "total_sessions": 0,
                "completed_sessions": 0,
                "in_progress_sessions": 0,
                "average_score": None,
                "average_score_percent": "—",
            },
            "students": [],
            "courses": [],
            "topics": [],
            "class_weaknesses": [],
            "recent_activity": [],
        }

    sessions_query = (
        select(VivaSession)
        .options(
            selectinload(VivaSession.answers)
            .selectinload(Answer.question)
            .selectinload(Question.topic),
            selectinload(VivaSession.answers).selectinload(Answer.score_override),
            selectinload(VivaSession.student),
            selectinload(VivaSession.course),
        )
        .where(VivaSession.course_id.in_(authorized_course_ids))
        .order_by(VivaSession.created_at.desc())
    )
    if from_date:
        sessions_query = sessions_query.where(VivaSession.created_at >= from_date)
    if to_date:
        sessions_query = sessions_query.where(VivaSession.created_at <= to_date)

    sessions = (await db.execute(sessions_query)).scalars().unique().all()

    total_sessions = len(sessions)
    completed_sessions = [s for s in sessions if s.status == VivaStatus.COMPLETED]
    in_progress_sessions = [s for s in sessions if s.status != VivaStatus.COMPLETED]
    scored_sessions = [s for s in completed_sessions if s.total_score is not None]

    if scored_sessions:
        avg_score = round(sum(s.total_score for s in scored_sessions) / len(scored_sessions), 4)
        avg_score_percent = f"{round(avg_score * 100)}%"
    else:
        avg_score = None
        avg_score_percent = "—"

    student_ids = {s.student_id for s in sessions if s.student_id}
    total_students = len(student_ids)

    # 1. Student Aggregation
    students_data = []
    sessions_by_student: dict[uuid.UUID, list[VivaSession]] = {}
    for s in sessions:
        if s.student_id:
            sessions_by_student.setdefault(s.student_id, []).append(s)

    for sid, s_list in sessions_by_student.items():
        s_completed = [s for s in s_list if s.status == VivaStatus.COMPLETED]
        s_scored = [s for s in s_completed if s.total_score is not None]
        s_avg = round(sum(s.total_score for s in s_scored) / len(s_scored), 4) if s_scored else None

        dates = [d for s in s_list for d in (s.finished_at, s.started_at, s.created_at) if d]
        last_active = (
            max(
                dates,
                key=lambda d: d.timestamp() if d.tzinfo else d.replace(tzinfo=UTC).timestamp(),
            )
            if dates
            else None
        )
        student_user = s_list[0].student

        students_data.append(
            {
                "student_id": str(sid),
                "student_name": student_user.full_name if student_user else "Student",
                "student_email": student_user.email if student_user else "",
                "total_sessions": len(s_list),
                "completed_sessions": len(s_completed),
                "average_score": s_avg,
                "average_score_percent": f"{round(s_avg * 100)}%" if s_avg is not None else "—",
                "last_active_at": last_active.isoformat() if last_active else None,
                "sessions": [
                    {
                        "id": str(s.id),
                        "course_id": str(s.course_id),
                        "course_name": s.course.name if s.course else None,
                        "course_code": s.course.code if s.course else None,
                        "status": s.status.value,
                        "total_score": s.total_score,
                        "total_score_percent": f"{round(s.total_score * 100)}%"
                        if s.total_score is not None
                        else "—",
                        "created_at": s.created_at.isoformat() if s.created_at else None,
                        "finished_at": s.finished_at.isoformat() if s.finished_at else None,
                    }
                    for s in s_list
                ],
            }
        )

    students_data.sort(key=lambda s: s["last_active_at"] or "", reverse=True)

    # 2. Course Aggregation
    courses_data = []
    sessions_by_course: dict[uuid.UUID, list[VivaSession]] = {}
    for s in sessions:
        sessions_by_course.setdefault(s.course_id, []).append(s)

    for c in authorized_courses:
        c_list = sessions_by_course.get(c.id, [])
        c_completed = [s for s in c_list if s.status == VivaStatus.COMPLETED]
        c_scored = [s for s in c_completed if s.total_score is not None]
        c_avg = round(sum(s.total_score for s in c_scored) / len(c_scored), 4) if c_scored else None
        c_students = len({s.student_id for s in c_list if s.student_id})

        courses_data.append(
            {
                "course_id": str(c.id),
                "course_name": c.name,
                "course_code": c.code,
                "total_sessions": len(c_list),
                "completed_sessions": len(c_completed),
                "student_count": c_students,
                "average_score": c_avg,
                "average_score_percent": f"{round(c_avg * 100)}%" if c_avg is not None else "—",
            }
        )

    courses_data.sort(key=lambda c: c["total_sessions"], reverse=True)

    # 3. Topics Aggregation (from answered question records)
    topic_tally: dict[uuid.UUID, dict] = {}
    for s in sessions:
        for a in s.answers:
            if a.question and a.question.topic:
                t = a.question.topic
                if t.id not in topic_tally:
                    topic_tally[t.id] = {
                        "topic_id": str(t.id),
                        "topic_name": t.name,
                        "course_id": str(t.course_id),
                        "course_name": s.course.name if s.course else "",
                        "attempt_count": 0,
                        "_scores": [],
                        "_students": set(),
                    }
                topic_tally[t.id]["attempt_count"] += 1
                if s.student_id:
                    topic_tally[t.id]["_students"].add(s.student_id)
                ans_score = (
                    a.score_override.override_score
                    if a.score_override and a.score_override.override_score is not None
                    else a.fused_score
                )
                if ans_score is not None:
                    topic_tally[t.id]["_scores"].append(float(ans_score))

    topics_data = []
    class_weaknesses = []
    for t in topic_tally.values():
        scores = t.pop("_scores")
        students = t.pop("_students")
        t_avg = round(sum(scores) / len(scores), 4) if scores else None
        t_avg_pct = f"{round(t_avg * 100)}%" if t_avg is not None else "—"
        is_weak = bool(t_avg is not None and t_avg < 0.65 and len(scores) >= 1)

        t["average_score"] = t_avg
        t["average_score_percent"] = t_avg_pct
        t["evaluated_count"] = len(scores)
        t["student_count"] = len(students)
        t["is_class_weakness"] = is_weak
        t["status"] = (
            "weakness" if is_weak else ("strength" if t_avg and t_avg >= 0.80 else "developing")
        )
        t["recommendation"] = (
            f"Class-wide review recommended: average score is {t_avg_pct}." if is_weak else None
        )

        topics_data.append(t)
        if is_weak:
            class_weaknesses.append(t)

    topics_data.sort(key=lambda t: t["attempt_count"], reverse=True)
    class_weaknesses.sort(
        key=lambda t: t["average_score"] if t["average_score"] is not None else 1.0
    )

    # 4. Recent Activity (top 10 sessions)
    recent_activity = [
        {
            "id": str(s.id),
            "session_id": str(s.id),
            "student_id": str(s.student_id),
            "student_name": s.student.full_name if s.student else "Student",
            "student_email": s.student.email if s.student else "",
            "course_id": str(s.course_id),
            "course_name": s.course.name if s.course else "",
            "course_code": s.course.code if s.course else "",
            "status": s.status.value,
            "total_score": s.total_score,
            "total_score_percent": f"{round(s.total_score * 100)}%"
            if s.total_score is not None
            else "—",
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "finished_at": s.finished_at.isoformat() if s.finished_at else None,
        }
        for s in sessions[:10]
    ]

    return {
        "summary": {
            "total_students": total_students,
            "total_sessions": total_sessions,
            "completed_sessions": len(completed_sessions),
            "in_progress_sessions": len(in_progress_sessions),
            "average_score": avg_score,
            "average_score_percent": avg_score_percent,
        },
        "students": students_data,
        "courses": courses_data,
        "topics": topics_data,
        "class_weaknesses": class_weaknesses,
        "recent_activity": recent_activity,
    }


@router.put("/viva/sessions/{session_id}/scores/{answer_id}")
async def override_score(
    session_id: uuid.UUID,
    answer_id: uuid.UUID,
    payload: dict,
    user: User = Depends(require_role(UserRole.TEACHER, UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    session = await _session(db, session_id)
    _check_access(session, user)
    answer = next((item for item in session.answers if item.id == answer_id), None)
    if answer is None:
        raise HTTPException(status_code=404, detail="Answer not found")
    try:
        score = float(payload.get("score")) / 100
        justification = str(payload.get("justification", "")).strip()
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Score must be a number from 0 to 100") from exc
    if not 0 <= score <= 1 or not justification:
        raise HTTPException(status_code=422, detail="Provide a score from 0 to 100 and a reason")
    override = answer.score_override
    if override is None:
        override = ScoreOverride(
            answer_id=answer.id,
            teacher_id=user.id,
            original_score=answer.fused_score or 0,
            override_score=score,
            justification=justification,
        )
        db.add(override)
    else:
        override.teacher_id = user.id
        override.override_score = score
        override.justification = justification
    await db.commit()
    return {"answer_id": str(answer.id), "override_score": score, "justification": justification}


@router.get("/viva/sessions/{session_id}/answers/{answer_id}/audio")
async def get_answer_audio(
    session_id: uuid.UUID,
    answer_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    session = await _session(db, session_id)
    _check_access(session, user)
    answer = next((a for a in session.answers if a.id == answer_id), None)
    if answer is None:
        raise HTTPException(status_code=404, detail="Answer not found")
    if not answer.audio_path:
        raise HTTPException(status_code=404, detail="No audio recording for this answer")
    file_path = Path(answer.audio_path)
    if not file_path.exists():
        for alt in (Path("..") / file_path, Path("backend") / file_path):
            if alt.exists():
                file_path = alt
                break
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Audio recording file not found")
    suffix = file_path.suffix.lower()
    media_types = {
        ".webm": "audio/webm",
        ".wav": "audio/wav",
        ".mp3": "audio/mpeg",
        ".ogg": "audio/ogg",
        ".m4a": "audio/mp4",
    }
    media_type = media_types.get(suffix, "application/octet-stream")
    return FileResponse(path=str(file_path), media_type=media_type, filename=file_path.name)


@router.get("/reports/student/me")
async def get_student_performance_report(
    course_id: uuid.UUID | None = Query(default=None),
    user: User = Depends(require_role(UserRole.STUDENT, UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Detailed oral performance report for the authenticated student."""
    query = (
        select(VivaSession)
        .options(
            selectinload(VivaSession.answers)
            .selectinload(Answer.question)
            .selectinload(Question.topic),
            selectinload(VivaSession.answers).selectinload(Answer.score_override),
            selectinload(VivaSession.course),
        )
        .where(VivaSession.student_id == user.id)
        .order_by(VivaSession.created_at.desc())
    )
    selected_course = None
    if course_id:
        course_res = await db.execute(select(Course).where(Course.id == course_id))
        selected_course = course_res.scalar_one_or_none()
        if selected_course is None:
            raise HTTPException(status_code=404, detail="Course not found")
        query = query.where(VivaSession.course_id == course_id)

    sessions = (await db.execute(query)).scalars().unique().all()
    return _build_student_performance_data(user, sessions, selected_course)


@router.get("/reports/student/me/pdf")
async def get_student_performance_report_pdf(
    course_id: uuid.UUID | None = Query(default=None),
    user: User = Depends(require_role(UserRole.STUDENT, UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Downloadable PDF oral performance report for the authenticated student."""
    data = await get_student_performance_report(course_id=course_id, user=user, db=db)
    pdf_bytes = generate_student_report_pdf(data)
    filename = f"parakh-student-report-{user.id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/reports/teacher/student/{student_id}")
async def get_teacher_student_performance_report(
    student_id: uuid.UUID,
    course_id: uuid.UUID | None = Query(default=None),
    user: User = Depends(require_role(UserRole.TEACHER, UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Instructor view of a student's performance, scoped strictly to courses taught by the instructor."""
    student_res = await db.execute(select(User).where(User.id == student_id))
    student = student_res.scalar_one_or_none()
    if student is None:
        raise HTTPException(status_code=404, detail="Student not found")

    # Courses authorized for this teacher
    courses_query = select(Course)
    if user.role == UserRole.TEACHER:
        courses_query = courses_query.where(Course.teacher_id == user.id)
    authorized_courses = (await db.execute(courses_query)).scalars().all()
    authorized_course_ids = [c.id for c in authorized_courses]

    selected_course = None
    if course_id:
        course_res = await db.execute(select(Course).where(Course.id == course_id))
        selected_course = course_res.scalar_one_or_none()
        if selected_course is None:
            raise HTTPException(status_code=404, detail="Course not found")
        if user.role == UserRole.TEACHER and selected_course.teacher_id != user.id:
            raise HTTPException(
                status_code=403, detail="You do not have access to this course report"
            )
        authorized_course_ids = [selected_course.id]

    # Query sessions
    query = (
        select(VivaSession)
        .options(
            selectinload(VivaSession.answers)
            .selectinload(Answer.question)
            .selectinload(Question.topic),
            selectinload(VivaSession.answers).selectinload(Answer.score_override),
            selectinload(VivaSession.course),
        )
        .where(
            VivaSession.student_id == student_id,
            VivaSession.course_id.in_(authorized_course_ids),
        )
        .order_by(VivaSession.created_at.desc())
    )
    sessions = (await db.execute(query)).scalars().unique().all()

    # If teacher has no shared sessions/courses with student, verify student isolation
    if user.role == UserRole.TEACHER and not sessions:
        # Check if student ever took any course by this teacher
        any_shared = await db.scalar(
            select(VivaSession.id)
            .where(
                VivaSession.student_id == student_id,
                VivaSession.course_id.in_(authorized_course_ids),
            )
            .limit(1)
        )
        if any_shared is None and not course_id:
            raise HTTPException(
                status_code=403, detail="You do not have access to this student's reports"
            )

    return _build_student_performance_data(student, sessions, selected_course)


@router.get("/reports/teacher/student/{student_id}/pdf")
async def get_teacher_student_performance_report_pdf(
    student_id: uuid.UUID,
    course_id: uuid.UUID | None = Query(default=None),
    user: User = Depends(require_role(UserRole.TEACHER, UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Downloadable PDF performance report of a student for instructor records."""
    data = await get_teacher_student_performance_report(
        student_id=student_id, course_id=course_id, user=user, db=db
    )
    pdf_bytes = generate_student_report_pdf(data)
    filename = f"parakh-student-report-{student_id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/reports/teacher/class")
async def get_teacher_class_report(
    course_id: uuid.UUID | None = Query(default=None),
    topic_id: uuid.UUID | None = Query(default=None),
    from_date: datetime | None = Query(default=None),
    to_date: datetime | None = Query(default=None),
    user: User = Depends(require_role(UserRole.TEACHER, UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Class-level detailed performance report and score distributions with date and topic filters."""
    from_date = _normalize_utc_dt(from_date)
    to_date = _normalize_utc_dt(to_date)
    if from_date and to_date and from_date > to_date:
        raise HTTPException(status_code=422, detail="From date must be earlier than to date")

    # Authorize courses
    courses_query = select(Course).order_by(Course.created_at.desc())
    if user.role == UserRole.TEACHER:
        courses_query = courses_query.where(Course.teacher_id == user.id)
    if course_id:
        course_res = await db.execute(select(Course).where(Course.id == course_id))
        target_course = course_res.scalar_one_or_none()
        if target_course is None:
            raise HTTPException(status_code=404, detail="Course not found")
        if user.role == UserRole.TEACHER and target_course.teacher_id != user.id:
            raise HTTPException(
                status_code=403, detail="You do not have access to this course report"
            )
        courses_query = courses_query.where(Course.id == course_id)

    authorized_courses = (await db.execute(courses_query)).scalars().all()
    authorized_course_ids = [c.id for c in authorized_courses]

    if topic_id:
        topic_res = await db.execute(select(Topic).where(Topic.id == topic_id))
        target_topic = topic_res.scalar_one_or_none()
        if target_topic is None:
            raise HTTPException(status_code=404, detail="Topic not found")
        if target_topic.course_id not in authorized_course_ids:
            raise HTTPException(
                status_code=403, detail="You do not have access to this topic report"
            )

    if not authorized_course_ids:
        return {
            "course_name": None,
            "course_code": None,
            "teacher_name": user.full_name,
            "summary": {
                "total_students": 0,
                "total_sessions": 0,
                "completed_sessions": 0,
                "average_score": None,
                "average_score_percent": "—",
            },
            "score_distribution": _calculate_score_distribution([]),
            "class_weaknesses": [],
            "topics": [],
            "students": [],
            "recent_sessions": [],
        }

    # Query sessions
    sessions_query = (
        select(VivaSession)
        .options(
            selectinload(VivaSession.answers)
            .selectinload(Answer.question)
            .selectinload(Question.topic),
            selectinload(VivaSession.answers).selectinload(Answer.score_override),
            selectinload(VivaSession.student),
            selectinload(VivaSession.course),
        )
        .where(VivaSession.course_id.in_(authorized_course_ids))
        .order_by(VivaSession.created_at.desc())
    )
    if from_date:
        sessions_query = sessions_query.where(VivaSession.created_at >= from_date)
    if to_date:
        sessions_query = sessions_query.where(VivaSession.created_at <= to_date)

    raw_sessions = (await db.execute(sessions_query)).scalars().unique().all()

    # Filter by topic_id if provided
    sessions: list[VivaSession] = []
    for s in raw_sessions:
        if topic_id:
            has_topic = any(a.question and a.question.topic_id == topic_id for a in s.answers)
            if not has_topic:
                continue
        sessions.append(s)

    total_sessions = len(sessions)
    completed_sessions = [s for s in sessions if s.status == VivaStatus.COMPLETED]
    scored_sessions = [
        s for s in completed_sessions if (s.total_score is not None or s.total_score is not None)
    ]
    scores = [
        float(s.total_score if s.total_score is not None else s.total_score)
        for s in scored_sessions
    ]
    avg_score = round(sum(scores) / len(scores), 4) if scores else None
    avg_score_pct = f"{round(avg_score * 100)}%" if avg_score is not None else "—"

    # Score Distribution
    distribution = _calculate_score_distribution(scores)

    # Students breakdown
    students_map: dict[uuid.UUID, list[VivaSession]] = {}
    for s in sessions:
        if s.student_id:
            students_map.setdefault(s.student_id, []).append(s)

    students_list = []
    for sid, s_list in students_map.items():
        stu_completed = [s for s in s_list if s.status == VivaStatus.COMPLETED]
        stu_scores = [
            float(s.total_score if s.total_score is not None else s.total_score)
            for s in stu_completed
            if (s.total_score is not None or s.total_score is not None)
        ]
        s_avg = round(sum(stu_scores) / len(stu_scores), 4) if stu_scores else None
        dates = [d for s in s_list for d in (s.finished_at, s.started_at, s.created_at) if d]
        last_dt = (
            max(
                dates,
                key=lambda d: d.timestamp() if d.tzinfo else d.replace(tzinfo=UTC).timestamp(),
            ).isoformat()
            if dates
            else None
        )
        stu_user = s_list[0].student

        students_list.append(
            {
                "student_id": str(sid),
                "student_name": stu_user.full_name if stu_user else "Student",
                "student_email": stu_user.email if stu_user else "",
                "total_sessions": len(s_list),
                "completed_sessions": len(stu_completed),
                "average_score": s_avg,
                "average_score_percent": f"{round(s_avg * 100)}%" if s_avg is not None else "—",
                "last_active_at": last_dt,
            }
        )
    students_list.sort(key=lambda s: s["student_name"].lower())

    # Topic breakdown
    topic_tally: dict[str, dict[str, Any]] = {}
    for s in sessions:
        for a in s.answers:
            if a.question and a.question.topic:
                t = a.question.topic
                tid = str(t.id)
                if tid not in topic_tally:
                    topic_tally[tid] = {
                        "topic_id": tid,
                        "topic_name": t.name,
                        "course_id": str(t.course_id),
                        "course_name": s.course.name if s.course else "",
                        "attempt_count": 0,
                        "_scores": [],
                    }
                topic_tally[tid]["attempt_count"] += 1
                ans_score = (
                    a.score_override.override_score
                    if a.score_override and a.score_override.override_score is not None
                    else a.fused_score
                )
                if ans_score is not None:
                    topic_tally[tid]["_scores"].append(float(ans_score))

    topics_data = []
    class_weaknesses = []
    for t_data in topic_tally.values():
        t_sc = t_data.pop("_scores")
        t_avg = round(sum(t_sc) / len(t_sc), 4) if t_sc else None
        t_avg_pct = f"{round(t_avg * 100)}%" if t_avg is not None else "—"
        is_weak = bool(t_avg is not None and t_avg < 0.65)

        entry = {
            **t_data,
            "average_score": t_avg,
            "average_score_percent": t_avg_pct,
            "evaluated_count": len(t_sc),
            "is_weakness": is_weak,
            "status": "weakness"
            if is_weak
            else ("strength" if t_avg and t_avg >= 0.80 else "developing"),
            "recommendation": f"Class average is {t_avg_pct}. Consider dedicated review of core principles."
            if is_weak
            else None,
        }
        topics_data.append(entry)
        if is_weak:
            class_weaknesses.append(entry)

    topics_data.sort(key=lambda t: t["average_score"] if t["average_score"] is not None else 1.0)
    class_weaknesses.sort(
        key=lambda t: t["average_score"] if t["average_score"] is not None else 1.0
    )

    # Distinct assessment vs adaptive practice activity breakdown
    assessment_sessions = [
        s
        for s in completed_sessions
        if (s.config or {}).get("assessment_id") or (s.config or {}).get("assignment_id")
    ]
    adaptive_sessions = [s for s in completed_sessions if s not in assessment_sessions]

    asst_avg = (
        round(
            sum(s.total_score for s in assessment_sessions if s.total_score is not None)
            / len(assessment_sessions),
            4,
        )
        if assessment_sessions
        else None
    )
    adapt_avg = (
        round(
            sum(s.total_score for s in adaptive_sessions if s.total_score is not None)
            / len(adaptive_sessions),
            4,
        )
        if adaptive_sessions
        else None
    )

    easy_count = 0
    med_count = 0
    hard_count = 0
    stepped_up = 0
    for s in adaptive_sessions:
        prog = (s.config or {}).get("difficulty_progression", [])
        for d in prog:
            if d == "easy":
                easy_count += 1
            elif d == "medium":
                med_count += 1
            elif d == "hard":
                hard_count += 1
        if len(prog) >= 2 and prog[-1] == "hard" and prog[0] != "hard":
            stepped_up += 1

    activity_breakdown = {
        "assigned_assessments": {
            "count": len(assessment_sessions),
            "average_score": asst_avg,
            "average_score_percent": f"{round(asst_avg * 100)}%" if asst_avg is not None else "—",
        },
        "adaptive_practice": {
            "count": len(adaptive_sessions),
            "average_score": adapt_avg,
            "average_score_percent": f"{round(adapt_avg * 100)}%" if adapt_avg is not None else "—",
            "stepped_up_to_hard_count": stepped_up,
            "difficulty_breakdown": {
                "easy": easy_count,
                "medium": med_count,
                "hard": hard_count,
            },
        },
    }

    # Active course info
    active_course_name = (
        authorized_courses[0].name if len(authorized_courses) == 1 else "All Courses"
    )
    active_course_code = authorized_courses[0].code if len(authorized_courses) == 1 else ""

    return {
        "activity_breakdown": activity_breakdown,
        "course_name": active_course_name,
        "course_code": active_course_code,
        "teacher_name": user.full_name,
        "summary": {
            "total_students": len(students_map),
            "total_sessions": total_sessions,
            "completed_sessions": len(completed_sessions),
            "average_score": avg_score,
            "average_score_percent": avg_score_pct,
        },
        "score_distribution": distribution,
        "class_weaknesses": class_weaknesses,
        "topics": topics_data,
        "students": students_list,
        "recent_sessions": [
            {
                "id": str(s.id),
                "student_name": s.student.full_name if s.student else "Student",
                "student_email": s.student.email if s.student else "",
                "course_name": s.course.name if s.course else "",
                "status": s.status.value,
                "score": float(s.total_score if s.total_score is not None else s.total_score)
                if (s.total_score is not None or s.total_score is not None)
                else None,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in sessions[:15]
        ],
    }


@router.get("/reports/teacher/class/pdf")
async def get_teacher_class_report_pdf(
    course_id: uuid.UUID | None = Query(default=None),
    topic_id: uuid.UUID | None = Query(default=None),
    from_date: datetime | None = Query(default=None),
    to_date: datetime | None = Query(default=None),
    user: User = Depends(require_role(UserRole.TEACHER, UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Downloadable PDF class examination summary report with active filters applied."""
    data = await get_teacher_class_report(
        course_id=course_id,
        topic_id=topic_id,
        from_date=from_date,
        to_date=to_date,
        user=user,
        db=db,
    )
    pdf_bytes = generate_class_report_pdf(data)
    filename = f"parakh-class-report-{course_id or 'all'}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/reports/export")
async def export_reports(
    course_id: uuid.UUID | None = Query(default=None),
    student_id: uuid.UUID | None = Query(default=None),
    topic_id: uuid.UUID | None = Query(default=None),
    from_date: datetime | None = Query(default=None),
    to_date: datetime | None = Query(default=None),
    user: User = Depends(require_role(UserRole.TEACHER, UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Export filtered viva examination records as standard CSV, respecting instructor ownership and date boundaries."""
    from_date = _normalize_utc_dt(from_date)
    to_date = _normalize_utc_dt(to_date)
    if from_date and to_date and from_date > to_date:
        raise HTTPException(status_code=422, detail="From date must be earlier than to date")

    query = (
        select(VivaSession)
        .options(
            selectinload(VivaSession.answers)
            .selectinload(Answer.question)
            .selectinload(Question.topic),
            selectinload(VivaSession.answers).selectinload(Answer.score_override),
            selectinload(VivaSession.student),
            selectinload(VivaSession.course),
        )
        .order_by(VivaSession.created_at.desc())
    )
    if user.role == UserRole.TEACHER:
        query = query.join(Course, VivaSession.course_id == Course.id).where(
            Course.teacher_id == user.id
        )

    if course_id:
        course_result = await db.execute(select(Course).where(Course.id == course_id))
        course = course_result.scalar_one_or_none()
        if course is None:
            raise HTTPException(status_code=404, detail="Course not found")
        if user.role == UserRole.TEACHER and course.teacher_id != user.id:
            raise HTTPException(
                status_code=403, detail="You do not have access to this course report"
            )
        query = query.where(VivaSession.course_id == course_id)

    if student_id:
        student_res = await db.execute(select(User).where(User.id == student_id))
        if student_res.scalar_one_or_none() is None:
            raise HTTPException(status_code=404, detail="Student not found")
        query = query.where(VivaSession.student_id == student_id)

    if from_date:
        query = query.where(VivaSession.created_at >= from_date)
    if to_date:
        query = query.where(VivaSession.created_at <= to_date)

    raw_sessions = (await db.execute(query)).scalars().unique().all()

    # Filter topic_id if provided
    sessions: list[VivaSession] = []
    for s in raw_sessions:
        if topic_id:
            has_topic = any(a.question and a.question.topic_id == topic_id for a in s.answers)
            if not has_topic:
                continue
        sessions.append(s)

    # If teacher specifically queried a student they have no access to
    if user.role == UserRole.TEACHER and student_id and not sessions:
        # Check if student ever took any course by this teacher
        any_access = await db.scalar(
            select(VivaSession.id)
            .join(Course, VivaSession.course_id == Course.id)
            .where(
                VivaSession.student_id == student_id,
                Course.teacher_id == user.id,
            )
            .limit(1)
        )
        if any_access is None:
            raise HTTPException(
                status_code=403, detail="You do not have access to this student's reports"
            )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "session_id",
            "student_name",
            "student_email",
            "course_name",
            "course_code",
            "session_type",
            "assessment_or_assignment_title",
            "status",
            "session_date",
            "overall_score",
            "topic_name",
            "question_text",
            "transcript",
            "answer_score",
            "teacher_override",
            "override_reason",
        ]
    )

    for session in sessions:
        cfg = session.config or {}
        if cfg.get("assignment_id"):
            session_type = "Assignment"
            title = cfg.get("assignment_title") or "Scheduled Assignment"
        elif cfg.get("assessment_id"):
            session_type = "Assessment"
            title = cfg.get("assessment_title") or "Custom Viva"
        else:
            session_type = "Practice"
            title = "Practice Viva"

        session_overall = session.total_score
        overall_str = (
            f"{round(float(session_overall) * 100)}%" if session_overall is not None else ""
        )
        date_str = session.created_at.isoformat() if session.created_at else ""

        if not session.answers:
            # Output session row even if 0 answers yet
            writer.writerow(
                [
                    str(session.id),
                    session.student.full_name if session.student else "Student",
                    session.student.email if session.student else "",
                    session.course.name if session.course else "",
                    session.course.code if session.course else "",
                    session_type,
                    title,
                    session.status.value,
                    date_str,
                    overall_str,
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                ]
            )
            continue

        for answer in session.answers:
            q_topic = (
                answer.question.topic.name if (answer.question and answer.question.topic) else ""
            )
            q_text = answer.question.question_text if answer.question else ""
            ans_score = (
                answer.score_override.override_score
                if answer.score_override and answer.score_override.override_score is not None
                else answer.fused_score
            )
            score_str = f"{round(float(ans_score) * 100)}%" if ans_score is not None else ""
            override_val = answer.score_override.override_score if answer.score_override else ""
            override_reason = answer.score_override.justification if answer.score_override else ""

            writer.writerow(
                [
                    str(session.id),
                    session.student.full_name if session.student else "Student",
                    session.student.email if session.student else "",
                    session.course.name if session.course else "",
                    session.course.code if session.course else "",
                    session_type,
                    title,
                    session.status.value,
                    date_str,
                    overall_str,
                    q_topic,
                    q_text,
                    answer.transcript or "",
                    score_str,
                    override_val,
                    override_reason,
                ]
            )

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=parakh-teacher-report.csv"},
    )
