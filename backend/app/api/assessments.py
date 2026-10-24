"""Custom Viva Builder and Assessment APIs (P2.10)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_db, require_role
from app.models.assessment import Assessment
from app.models.course import Course
from app.models.question import Question
from app.models.topic import Topic
from app.models.user import User, UserRole
from app.models.viva_session import VivaSession, VivaStatus
from app.schemas.assessment import (
    AssessmentCreate,
    AssessmentResponse,
    AssessmentUpdate,
    StudentAssessmentResponse,
)
from app.schemas.question import QuestionResponse

router = APIRouter(tags=["Assessments"])


def _to_assessment_response(
    assessment: Assessment, questions: list[Question] | None = None
) -> AssessmentResponse:
    q_ids = [uuid.UUID(str(item)) for item in assessment.question_ids if item]
    t_ids = [uuid.UUID(str(item)) for item in assessment.topic_ids if item]
    q_responses = [QuestionResponse.model_validate(q) for q in (questions or [])]
    return AssessmentResponse(
        id=assessment.id,
        teacher_id=assessment.teacher_id,
        course_id=assessment.course_id,
        course_name=assessment.course.name if assessment.course else None,
        course_code=assessment.course.code if assessment.course else None,
        title=assessment.title,
        description=assessment.description,
        instructions=assessment.instructions,
        duration_minutes=assessment.duration_minutes,
        max_questions=assessment.max_questions,
        difficulty=assessment.difficulty,
        is_published=assessment.is_published,
        topic_ids=t_ids,
        question_ids=q_ids,
        question_count=len(q_ids),
        questions=q_responses,
        config=assessment.config or {},
        created_at=assessment.created_at,
        updated_at=assessment.updated_at,
    )


async def _get_teacher_assessment(
    assessment_id: uuid.UUID,
    current_user: User,
    db: AsyncSession,
) -> Assessment:
    stmt = (
        select(Assessment)
        .options(selectinload(Assessment.course))
        .where(Assessment.id == assessment_id)
    )
    assessment = await db.scalar(stmt)
    if assessment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")
    if current_user.role == UserRole.TEACHER and assessment.teacher_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="You do not own this assessment"
        )
    return assessment


@router.get("/assessments", response_model=list[AssessmentResponse])
async def list_teacher_assessments(
    course_id: uuid.UUID | None = None,
    is_published: bool | None = None,
    current_user: User = Depends(require_role(UserRole.TEACHER, UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> list[AssessmentResponse]:
    """List assessments created by the authenticated teacher, with optional course and published filters."""
    stmt = (
        select(Assessment)
        .options(selectinload(Assessment.course))
        .order_by(Assessment.created_at.desc())
    )
    if current_user.role == UserRole.TEACHER:
        stmt = stmt.where(Assessment.teacher_id == current_user.id)
    if course_id is not None:
        stmt = stmt.where(Assessment.course_id == course_id)
    if is_published is not None:
        stmt = stmt.where(Assessment.is_published == is_published)

    result = await db.execute(stmt)
    assessments = result.scalars().all()
    return [_to_assessment_response(a) for a in assessments]


@router.post("/assessments", response_model=AssessmentResponse, status_code=status.HTTP_201_CREATED)
async def create_assessment(
    payload: AssessmentCreate,
    current_user: User = Depends(require_role(UserRole.TEACHER, UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> AssessmentResponse:
    """Create a new custom oral exam assessment in draft or published state."""
    course = await db.scalar(select(Course).where(Course.id == payload.course_id))
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
    if current_user.role == UserRole.TEACHER and course.teacher_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="You do not own this course"
        )

    # Validate topics belong to course
    if payload.topic_ids:
        valid_topics = set(
            (
                await db.execute(
                    select(Topic.id).where(
                        Topic.course_id == course.id,
                        Topic.id.in_(payload.topic_ids),
                    )
                )
            )
            .scalars()
            .all()
        )
        if valid_topics != set(payload.topic_ids):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Some selected topics do not belong to this course",
            )

    # Validate questions belong to course topics
    if payload.question_ids:
        valid_q_ids = set(
            (
                await db.execute(
                    select(Question.id)
                    .join(Topic, Question.topic_id == Topic.id)
                    .where(
                        Topic.course_id == course.id,
                        Question.id.in_(payload.question_ids),
                    )
                )
            )
            .scalars()
            .all()
        )
        if valid_q_ids != set(payload.question_ids):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Some selected questions do not belong to this course",
            )

    assessment = Assessment(
        teacher_id=current_user.id,
        course_id=course.id,
        title=payload.title.strip(),
        description=payload.description.strip() if payload.description else None,
        instructions=payload.instructions.strip() if payload.instructions else None,
        duration_minutes=payload.duration_minutes,
        max_questions=payload.max_questions,
        difficulty=payload.difficulty,
        is_published=payload.is_published,
        topic_ids=[str(item) for item in payload.topic_ids],
        question_ids=[str(item) for item in payload.question_ids],
        config=payload.config or {},
    )
    db.add(assessment)
    await db.commit()
    await db.refresh(assessment)

    # Reload with course relationship
    assessment = await _get_teacher_assessment(assessment.id, current_user, db)
    return _to_assessment_response(assessment)


@router.get("/assessments/{assessment_id}", response_model=AssessmentResponse)
async def get_assessment(
    assessment_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AssessmentResponse:
    """Retrieve full assessment details and questions for teachers, or published assessment info for students."""
    stmt = (
        select(Assessment)
        .options(selectinload(Assessment.course))
        .where(Assessment.id == assessment_id)
    )
    assessment = await db.scalar(stmt)
    if assessment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")

    if current_user.role == UserRole.STUDENT:
        if not assessment.is_published:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This assessment is not currently published",
            )
        return _to_assessment_response(assessment)

    if current_user.role == UserRole.TEACHER and assessment.teacher_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="You do not own this assessment"
        )

    questions: list[Question] = []
    if assessment.question_ids:
        q_uuids = [uuid.UUID(str(item)) for item in assessment.question_ids if item]
        q_res = await db.execute(
            select(Question).options(selectinload(Question.topic)).where(Question.id.in_(q_uuids))
        )
        questions_by_id = {q.id: q for q in q_res.scalars().all()}
        # Preserve configured question order
        questions = [questions_by_id[qid] for qid in q_uuids if qid in questions_by_id]

    return _to_assessment_response(assessment, questions=questions)


@router.put("/assessments/{assessment_id}", response_model=AssessmentResponse)
async def update_assessment(
    assessment_id: uuid.UUID,
    payload: AssessmentUpdate,
    current_user: User = Depends(require_role(UserRole.TEACHER, UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> AssessmentResponse:
    """Update assessment title, instructions, duration, questions, topics, or published status."""
    assessment = await _get_teacher_assessment(assessment_id, current_user, db)

    if payload.title is not None:
        assessment.title = payload.title.strip()
    if payload.description is not None:
        assessment.description = payload.description.strip() if payload.description else None
    if payload.instructions is not None:
        assessment.instructions = payload.instructions.strip() if payload.instructions else None
    if payload.duration_minutes is not None:
        assessment.duration_minutes = payload.duration_minutes
    if payload.max_questions is not None:
        assessment.max_questions = payload.max_questions
    if payload.difficulty is not None:
        assessment.difficulty = payload.difficulty
    if payload.is_published is not None:
        assessment.is_published = payload.is_published

    if payload.topic_ids is not None:
        if payload.topic_ids:
            valid_topics = set(
                (
                    await db.execute(
                        select(Topic.id).where(
                            Topic.course_id == assessment.course_id,
                            Topic.id.in_(payload.topic_ids),
                        )
                    )
                )
                .scalars()
                .all()
            )
            if valid_topics != set(payload.topic_ids):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Some selected topics do not belong to this course",
                )
        assessment.topic_ids = [str(item) for item in payload.topic_ids]

    if payload.question_ids is not None:
        if payload.question_ids:
            valid_q_ids = set(
                (
                    await db.execute(
                        select(Question.id)
                        .join(Topic, Question.topic_id == Topic.id)
                        .where(
                            Topic.course_id == assessment.course_id,
                            Question.id.in_(payload.question_ids),
                        )
                    )
                )
                .scalars()
                .all()
            )
            if valid_q_ids != set(payload.question_ids):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Some selected questions do not belong to this course",
                )
        assessment.question_ids = [str(item) for item in payload.question_ids]

    if payload.config is not None:
        assessment.config = payload.config

    await db.commit()
    await db.refresh(assessment)
    return _to_assessment_response(assessment)


@router.post("/assessments/{assessment_id}/publish", response_model=AssessmentResponse)
async def toggle_assessment_publish(
    assessment_id: uuid.UUID,
    published: bool | None = Query(default=None),
    current_user: User = Depends(require_role(UserRole.TEACHER, UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> AssessmentResponse:
    """Toggle or set the published status of an assessment."""
    assessment = await _get_teacher_assessment(assessment_id, current_user, db)
    assessment.is_published = not assessment.is_published if published is None else published
    await db.commit()
    await db.refresh(assessment)
    return _to_assessment_response(assessment)


@router.delete("/assessments/{assessment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_assessment(
    assessment_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.TEACHER, UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete an assessment owned by the teacher."""
    assessment = await _get_teacher_assessment(assessment_id, current_user, db)
    await db.delete(assessment)
    await db.commit()


@router.get("/student/assessments", response_model=list[StudentAssessmentResponse])
async def list_student_available_assessments(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[StudentAssessmentResponse]:
    """List published assessments available for the authenticated student, with attempt history."""
    stmt = (
        select(Assessment)
        .options(selectinload(Assessment.course))
        .where(Assessment.is_published == True)  # noqa: E712
        .order_by(Assessment.created_at.desc())
    )
    result = await db.execute(stmt)
    published = result.scalars().all()

    # Query completed viva sessions for this student to calculate attempts and latest score
    sess_res = await db.execute(
        select(VivaSession)
        .where(
            VivaSession.student_id == current_user.id,
            VivaSession.status == VivaStatus.COMPLETED,
        )
        .order_by(VivaSession.created_at.desc())
    )
    sessions = sess_res.scalars().all()

    # Map sessions by assessment_id
    attempts_map: dict[str, list[VivaSession]] = {}
    for s in sessions:
        aid = (s.config or {}).get("assessment_id")
        if aid:
            attempts_map.setdefault(aid, []).append(s)

    items: list[StudentAssessmentResponse] = []
    for a in published:
        aid_str = str(a.id)
        user_sess = attempts_map.get(aid_str, [])
        latest_score = None
        if user_sess and user_sess[0].total_score is not None:
            latest_score = f"{round(user_sess[0].total_score * 100)}%"

        q_count = len(a.question_ids) if a.question_ids else a.max_questions
        items.append(
            StudentAssessmentResponse(
                id=a.id,
                course_id=a.course_id,
                course_name=a.course.name if a.course else "",
                course_code=a.course.code if a.course else "",
                title=a.title,
                description=a.description,
                instructions=a.instructions,
                duration_minutes=a.duration_minutes,
                max_questions=a.max_questions,
                difficulty=a.difficulty,
                question_count=q_count,
                start_url=f"/viva/{a.course_id}?assessment={a.id}",
                user_attempts_count=len(user_sess),
                latest_score_percent=latest_score,
            )
        )
    return items
