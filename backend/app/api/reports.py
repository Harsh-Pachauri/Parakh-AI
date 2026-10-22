"""Teacher session review and CSV export endpoints."""

import csv
import io
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_db, require_role
from app.models.answer import Answer
from app.models.course import Course
from app.models.score_override import ScoreOverride
from app.models.user import User, UserRole
from app.models.viva_session import VivaSession

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
        "student_name": session.student.full_name,
        "course_id": str(session.course_id),
        "course_name": session.course.name,
        "status": session.status.value,
        "total_score": session.total_score,
        "created_at": session.created_at.isoformat(),
        "started_at": session.started_at.isoformat() if session.started_at else None,
        "behavior_flags": (session.config or {}).get("behavior_flags", []),
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


@router.get("/teacher/sessions")
async def teacher_sessions(
    user: User = Depends(require_role(UserRole.TEACHER, UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
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
    sessions = (await db.execute(query)).scalars().unique().all()
    return [{k: v for k, v in _serialize(s).items() if k != "answers"} for s in sessions]


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


@router.get("/reports/export")
async def export_reports(
    course_id: uuid.UUID | None = Query(default=None),
    user: User = Depends(require_role(UserRole.TEACHER, UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> Response:
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
        query = query.where(VivaSession.course_id == course_id)
    sessions = (await db.execute(query)).scalars().unique().all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "session_id",
            "student",
            "course",
            "status",
            "created_at",
            "question",
            "transcript",
            "system_score",
            "teacher_override",
            "override_reason",
        ]
    )
    for session in sessions:
        for answer in session.answers:
            writer.writerow(
                [
                    session.id,
                    session.student.full_name,
                    session.course.name,
                    session.status.value,
                    session.created_at.isoformat(),
                    answer.question.question_text,
                    answer.transcript or "",
                    answer.fused_score if answer.fused_score is not None else "",
                    answer.score_override.override_score if answer.score_override else "",
                    answer.score_override.justification if answer.score_override else "",
                ]
            )
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=viva-sessions.csv"},
    )
