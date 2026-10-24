"""Assessment Assignment, Scheduling, and Deadlines APIs (P2.11)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_db, require_role
from app.models.assessment import Assessment
from app.models.assignment import Assignment
from app.models.course import Course
from app.models.user import User, UserRole
from app.models.viva_session import VivaSession, VivaStatus
from app.schemas.assignment import (
    AssignmentCreate,
    AssignmentResponse,
    AssignmentSubmissionItem,
    AssignmentSubmissionsResponse,
    AssignmentUpdate,
    StudentAssignmentResponse,
)

router = APIRouter(tags=["Assignments"])


def _normalize_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def _determine_teacher_status(assignment: Assignment, now: datetime) -> str:
    if not assignment.is_active:
        return "closed"
    dl = _normalize_utc(assignment.deadline)
    if dl and now > dl:
        return "closed"
    st = _normalize_utc(assignment.start_date)
    if st and now < st:
        return "scheduled"
    return "active"


def _build_teacher_assignment_response(
    assignment: Assignment,
    sessions: list[VivaSession],
    now: datetime,
) -> AssignmentResponse:
    as_id_str = str(assignment.id)
    matching = [s for s in sessions if (s.config or {}).get("assignment_id") == as_id_str]
    completed = [s for s in matching if s.status == VivaStatus.COMPLETED]
    scores = [s.total_score for s in completed if s.total_score is not None]
    avg_score = round(sum(scores) / len(scores), 2) if scores else None

    status_str = _determine_teacher_status(assignment, now)

    return AssignmentResponse(
        id=assignment.id,
        teacher_id=assignment.teacher_id,
        course_id=assignment.course_id,
        assessment_id=assignment.assessment_id,
        title=assignment.title,
        instructions=assignment.instructions,
        start_date=assignment.start_date,
        deadline=assignment.deadline,
        attempt_limit=assignment.attempt_limit,
        is_active=assignment.is_active,
        assigned_student_ids=assignment.assigned_student_ids or [],
        config=assignment.config or {},
        created_at=assignment.created_at,
        updated_at=assignment.updated_at,
        course_name=assignment.course.name if assignment.course else None,
        course_code=assignment.course.code if assignment.course else None,
        assessment_title=assignment.assessment.title if assignment.assessment else None,
        duration_minutes=assignment.assessment.duration_minutes if assignment.assessment else None,
        status=status_str,
        total_submissions=len(matching),
        completed_count=len(completed),
        average_score=avg_score,
    )


async def _get_assignment_with_auth(
    assignment_id: uuid.UUID,
    current_user: User,
    db: AsyncSession,
) -> Assignment:
    stmt = (
        select(Assignment)
        .options(
            selectinload(Assignment.course),
            selectinload(Assignment.assessment),
        )
        .where(Assignment.id == assignment_id)
    )
    assignment = await db.scalar(stmt)
    if assignment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assignment not found",
        )
    if current_user.role == UserRole.TEACHER and assignment.teacher_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not own this assignment",
        )
    return assignment


@router.post("/assignments", response_model=AssignmentResponse, status_code=status.HTTP_201_CREATED)
async def create_assignment(
    payload: AssignmentCreate,
    current_user: User = Depends(require_role(UserRole.TEACHER, UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> AssignmentResponse:
    """Create a new scheduled assessment assignment for a course."""
    course = await db.scalar(
        select(Course).options(selectinload(Course.teacher)).where(Course.id == payload.course_id)
    )
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
    if current_user.role == UserRole.TEACHER and course.teacher_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="You do not own this course"
        )

    assessment = await db.scalar(select(Assessment).where(Assessment.id == payload.assessment_id))
    if assessment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")
    if current_user.role == UserRole.TEACHER and assessment.teacher_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="You do not own this assessment"
        )
    if assessment.course_id != payload.course_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Assessment does not belong to the selected course",
        )
    if not assessment.is_published:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Cannot assign an unpublished assessment. Please publish the assessment first.",
        )

    # Validate assigned_student_ids if provided
    clean_student_ids: list[str] = []
    if payload.assigned_student_ids:
        for sid in payload.assigned_student_ids:
            try:
                parsed = str(uuid.UUID(str(sid)))
                clean_student_ids.append(parsed)
            except ValueError as exc:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Invalid student ID: {sid}",
                ) from exc

    assignment = Assignment(
        teacher_id=current_user.id if current_user.role == UserRole.TEACHER else course.teacher_id,
        course_id=payload.course_id,
        assessment_id=payload.assessment_id,
        title=payload.title,
        instructions=payload.instructions,
        start_date=_normalize_utc(payload.start_date),
        deadline=_normalize_utc(payload.deadline),
        attempt_limit=payload.attempt_limit,
        is_active=payload.is_active,
        assigned_student_ids=clean_student_ids,
        config=payload.config or {},
    )
    db.add(assignment)
    await db.commit()
    await db.refresh(assignment)

    # Re-fetch with relationships loaded
    loaded = await _get_assignment_with_auth(assignment.id, current_user, db)
    now = datetime.now(UTC)
    return _build_teacher_assignment_response(loaded, [], now)


@router.get("/assignments", response_model=list[AssignmentResponse])
async def list_teacher_assignments(
    course_id: uuid.UUID | None = None,
    current_user: User = Depends(require_role(UserRole.TEACHER, UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> list[AssignmentResponse]:
    """List assignments created by the authenticated teacher with completion stats."""
    stmt = (
        select(Assignment)
        .options(
            selectinload(Assignment.course),
            selectinload(Assignment.assessment),
        )
        .order_by(Assignment.created_at.desc())
    )
    if current_user.role == UserRole.TEACHER:
        stmt = stmt.where(Assignment.teacher_id == current_user.id)
    if course_id is not None:
        stmt = stmt.where(Assignment.course_id == course_id)

    result = await db.execute(stmt)
    assignments = result.scalars().all()
    if not assignments:
        return []

    # Load sessions belonging to this teacher's courses
    course_ids = [a.course_id for a in assignments]
    sess_stmt = select(VivaSession).where(VivaSession.course_id.in_(course_ids))
    sess_res = await db.execute(sess_stmt)
    sessions = sess_res.scalars().all()

    now = datetime.now(UTC)
    return [_build_teacher_assignment_response(a, sessions, now) for a in assignments]


@router.get("/assignments/{assignment_id}", response_model=AssignmentResponse)
async def get_assignment_details(
    assignment_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.TEACHER, UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> AssignmentResponse:
    """Get single assignment metadata and current progress."""
    assignment = await _get_assignment_with_auth(assignment_id, current_user, db)

    sess_stmt = select(VivaSession).where(VivaSession.course_id == assignment.course_id)
    sess_res = await db.execute(sess_stmt)
    sessions = sess_res.scalars().all()

    now = datetime.now(UTC)
    return _build_teacher_assignment_response(assignment, sessions, now)


@router.put("/assignments/{assignment_id}", response_model=AssignmentResponse)
async def update_assignment(
    assignment_id: uuid.UUID,
    payload: AssignmentUpdate,
    current_user: User = Depends(require_role(UserRole.TEACHER, UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> AssignmentResponse:
    """Update assignment scheduling, instructions, attempt limit, or status."""
    assignment = await _get_assignment_with_auth(assignment_id, current_user, db)

    # Check existing sessions
    sess_stmt = select(VivaSession).where(VivaSession.course_id == assignment.course_id)
    sess_res = await db.execute(sess_stmt)
    all_course_sessions = sess_res.scalars().all()
    as_id_str = str(assignment.id)
    matching = [
        s for s in all_course_sessions if (s.config or {}).get("assignment_id") == as_id_str
    ]

    # If payload updates attempt limit, verify it is not less than attempts already taken
    if payload.attempt_limit is not None and matching:
        # Group by student to check max attempts
        student_attempt_counts: dict[str, int] = {}
        for s in matching:
            sid = str(s.student_id)
            student_attempt_counts[sid] = student_attempt_counts.get(sid, 0) + 1
        max_taken = max(student_attempt_counts.values()) if student_attempt_counts else 0
        if payload.attempt_limit < max_taken:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Cannot reduce attempt limit to {payload.attempt_limit}. A student has already used {max_taken} attempt(s).",
            )

    if payload.title is not None:
        assignment.title = payload.title
    if payload.instructions is not None:
        assignment.instructions = payload.instructions
    if payload.start_date is not None:
        assignment.start_date = _normalize_utc(payload.start_date)
    if payload.deadline is not None:
        assignment.deadline = _normalize_utc(payload.deadline)
    if payload.attempt_limit is not None:
        assignment.attempt_limit = payload.attempt_limit
    if payload.is_active is not None:
        assignment.is_active = payload.is_active
    if payload.assigned_student_ids is not None:
        clean_sids: list[str] = []
        for sid in payload.assigned_student_ids:
            try:
                clean_sids.append(str(uuid.UUID(str(sid))))
            except ValueError as exc:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Invalid student ID: {sid}",
                ) from exc
        assignment.assigned_student_ids = clean_sids
    if payload.config is not None:
        assignment.config = payload.config

    assignment.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(assignment)

    now = datetime.now(UTC)
    return _build_teacher_assignment_response(assignment, all_course_sessions, now)


@router.delete("/assignments/{assignment_id}")
async def delete_or_cancel_assignment(
    assignment_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.TEACHER, UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Delete unstarted assignment, or gracefully deactivate/cancel if students have already started."""
    assignment = await _get_assignment_with_auth(assignment_id, current_user, db)

    sess_stmt = select(VivaSession).where(VivaSession.course_id == assignment.course_id)
    sess_res = await db.execute(sess_stmt)
    matching = [
        s
        for s in sess_res.scalars().all()
        if (s.config or {}).get("assignment_id") == str(assignment.id)
    ]

    if matching:
        # Students have already started or submitted: deactivate instead of hard delete
        assignment.is_active = False
        assignment.updated_at = datetime.now(UTC)
        await db.commit()
        return {
            "detail": "Assignment cancelled and closed to preserve existing submissions",
            "action": "cancelled",
        }

    await db.delete(assignment)
    await db.commit()
    return {"detail": "Assignment successfully deleted", "action": "deleted"}


@router.get(
    "/assignments/{assignment_id}/submissions", response_model=AssignmentSubmissionsResponse
)
async def get_assignment_submissions(
    assignment_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.TEACHER, UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> AssignmentSubmissionsResponse:
    """Teacher view of all student submissions, scores, and completion stats for an assignment."""
    assignment = await _get_assignment_with_auth(assignment_id, current_user, db)

    sess_stmt = (
        select(VivaSession)
        .options(selectinload(VivaSession.student))
        .where(VivaSession.course_id == assignment.course_id)
        .order_by(VivaSession.created_at.desc())
    )
    sess_res = await db.execute(sess_stmt)
    all_sess = sess_res.scalars().all()

    as_id_str = str(assignment.id)
    matching = [s for s in all_sess if (s.config or {}).get("assignment_id") == as_id_str]

    items: list[AssignmentSubmissionItem] = []
    completed_scores: list[float] = []

    for s in matching:
        score_val = s.total_score
        if s.status == VivaStatus.COMPLETED and score_val is not None:
            completed_scores.append(score_val)

        student_name = s.student.full_name if s.student else "Unknown Student"
        student_email = s.student.email if s.student else "unknown"

        items.append(
            AssignmentSubmissionItem(
                session_id=s.id,
                student_id=s.student_id,
                student_name=student_name,
                student_email=student_email,
                status=s.status.value,
                score=score_val,
                created_at=s.created_at,
                completed_at=s.finished_at,
            )
        )

    completed_count = sum(1 for s in matching if s.status == VivaStatus.COMPLETED)
    avg_score = (
        round(sum(completed_scores) / len(completed_scores), 2) if completed_scores else None
    )

    # Calculate eligible students
    if assignment.assigned_student_ids:
        total_eligible = len(assignment.assigned_student_ids)
    else:
        # Open to all students in course or institution
        students_query = select(User).where(User.role == UserRole.STUDENT)
        if current_user.institution_id:
            students_query = students_query.where(
                User.institution_id == current_user.institution_id
            )
        stu_res = await db.execute(students_query)
        total_eligible = len(stu_res.scalars().all())

    return AssignmentSubmissionsResponse(
        assignment_id=assignment.id,
        title=assignment.title,
        course_name=assignment.course.name if assignment.course else None,
        total_eligible_students=total_eligible,
        total_submissions=len(matching),
        completed_count=completed_count,
        average_score=avg_score,
        submissions=items,
    )


@router.get("/student/assignments", response_model=list[StudentAssignmentResponse])
async def list_student_assignments(
    current_user: User = Depends(require_role(UserRole.STUDENT, UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> list[StudentAssignmentResponse]:
    """List assigned oral assessments for the authenticated student, with deadlines, attempts, and launch state."""
    # Fetch all assignments
    stmt = (
        select(Assignment)
        .options(
            selectinload(Assignment.course),
            selectinload(Assignment.assessment),
        )
        .order_by(Assignment.created_at.desc())
    )
    result = await db.execute(stmt)
    assignments = result.scalars().all()

    # Load sessions for this student
    sess_stmt = (
        select(VivaSession)
        .where(VivaSession.student_id == current_user.id)
        .order_by(VivaSession.created_at.desc())
    )
    sess_res = await db.execute(sess_stmt)
    student_sessions = sess_res.scalars().all()

    now = datetime.now(UTC)
    response_items: list[StudentAssignmentResponse] = []

    for a in assignments:
        # Filter: if assignment has specific student IDs, check if student is in the list
        if a.assigned_student_ids and str(current_user.id) not in [
            str(x) for x in a.assigned_student_ids
        ]:
            continue

        # Filter by institution if applicable
        if current_user.institution_id and a.course:
            course_teacher = await db.scalar(select(User).where(User.id == a.course.teacher_id))
            if (
                course_teacher
                and course_teacher.institution_id
                and course_teacher.institution_id != current_user.institution_id
            ):
                continue

        as_id_str = str(a.id)
        user_sess = [
            s for s in student_sessions if (s.config or {}).get("assignment_id") == as_id_str
        ]
        attempts_used = len(user_sess)

        # Find latest completed score
        completed_user_sess = [s for s in user_sess if s.status == VivaStatus.COMPLETED]
        latest_score = None
        latest_session_id = None
        if user_sess:
            latest_session_id = user_sess[0].id
        if completed_user_sess:
            score_val = completed_user_sess[0].total_score
            if score_val is not None:
                latest_score = score_val

        # Status calculation
        st = _normalize_utc(a.start_date)
        dl = _normalize_utc(a.deadline)

        has_active_session = any(s.status == VivaStatus.IN_PROGRESS for s in user_sess)

        if attempts_used >= a.attempt_limit:
            item_status = "submitted"
        elif not a.is_active:
            item_status = "closed"
        elif dl and now > dl:
            item_status = "overdue"
        elif st and now < st:
            item_status = "scheduled"
        else:
            item_status = "available"

        can_launch = (
            item_status == "available"
            and attempts_used < a.attempt_limit
            and a.is_active
            and not has_active_session
        )

        response_items.append(
            StudentAssignmentResponse(
                id=a.id,
                course_id=a.course_id,
                assessment_id=a.assessment_id,
                title=a.title,
                instructions=a.instructions,
                course_name=a.course.name if a.course else None,
                course_code=a.course.code if a.course else None,
                duration_minutes=a.assessment.duration_minutes if a.assessment else None,
                start_date=a.start_date,
                deadline=a.deadline,
                attempt_limit=a.attempt_limit,
                attempts_used=attempts_used,
                status=item_status,
                latest_session_id=latest_session_id,
                latest_score=latest_score,
                can_launch=can_launch,
            )
        )

    return response_items
