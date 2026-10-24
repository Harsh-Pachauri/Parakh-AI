"""Question-bank CRUD, question generation, and bulk CSV import endpoints."""

from __future__ import annotations

import csv
import io
import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_db, require_role
from app.models.course import Course
from app.models.document import Document
from app.models.question import Question, QuestionDifficulty
from app.models.topic import Topic
from app.models.user import User, UserRole
from app.schemas.question import (
    QuestionCreate,
    QuestionGenerateRequest,
    QuestionPageResponse,
    QuestionResponse,
    QuestionUpdate,
)
from app.services.document_service import DocumentService
from app.services.question_service import QuestionService
from app.services.rag_service import chunk_text, retrieve_for_topic

router = APIRouter(tags=["Questions"])


def _enrich_question_response(question: Question) -> QuestionResponse:
    resp = QuestionResponse.model_validate(question)
    topic = question.__dict__.get("topic")
    if topic is not None:
        resp.topic_name = topic.name
        resp.course_id = topic.course_id
        course = topic.__dict__.get("course")
        if course is not None:
            resp.course_name = course.name
    return resp


async def _question_for_teacher(
    question_id: uuid.UUID, current_user: User, db: AsyncSession
) -> Question:
    result = await db.execute(
        select(Question)
        .options(selectinload(Question.topic).selectinload(Topic.course))
        .join(Topic, Question.topic_id == Topic.id)
        .join(Course, Topic.course_id == Course.id)
        .where(Question.id == question_id)
    )
    question = result.scalar_one_or_none()
    if question is None:
        raise HTTPException(status_code=404, detail="Question not found")
    if current_user.role == UserRole.TEACHER:
        owner_id = await db.scalar(
            select(Course.teacher_id)
            .join(Topic, Topic.course_id == Course.id)
            .where(Topic.id == question.topic_id)
        )
        if owner_id != current_user.id:
            raise HTTPException(status_code=403, detail="You cannot manage this question")
    return question


async def _require_topic_owner(topic_id: uuid.UUID, current_user: User, db: AsyncSession) -> None:
    if current_user.role != UserRole.TEACHER:
        return
    owner_id = await db.scalar(
        select(Course.teacher_id)
        .join(Topic, Topic.course_id == Course.id)
        .where(Topic.id == topic_id)
    )
    if owner_id is None:
        raise HTTPException(status_code=404, detail="Topic not found")
    if owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="You cannot access this course topic")


@router.get("/questions", response_model=QuestionPageResponse)
async def search_questions(
    current_user: User = Depends(require_role(UserRole.TEACHER, UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
    search: str | None = Query(default=None, max_length=200),
    course_id: uuid.UUID | None = None,
    topic_id: uuid.UUID | None = None,
    difficulty: QuestionDifficulty | None = None,
    question_type: str | None = Query(default=None, max_length=50),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
) -> QuestionPageResponse:
    """Search the current teacher's question bank with bounded pagination."""
    statement = (
        select(Question)
        .options(selectinload(Question.topic).selectinload(Topic.course))
        .join(Topic, Question.topic_id == Topic.id)
        .join(Course, Topic.course_id == Course.id)
    )
    if current_user.role == UserRole.TEACHER:
        statement = statement.where(Course.teacher_id == current_user.id)
    if course_id is not None:
        statement = statement.where(Course.id == course_id)
    if topic_id is not None:
        statement = statement.where(Question.topic_id == topic_id)
    if difficulty is not None:
        statement = statement.where(Question.difficulty == difficulty)
    if question_type:
        statement = statement.where(Question.question_type == question_type)
    if search:
        statement = statement.where(Question.question_text.ilike(f"%{search.strip()}%"))

    count_result = await db.execute(select(func.count()).select_from(statement.subquery()))
    result = await db.execute(
        statement.order_by(Question.created_at.desc()).offset(offset).limit(limit)
    )
    return QuestionPageResponse(
        items=[_enrich_question_response(item) for item in result.scalars().all()],
        total=count_result.scalar_one(),
        offset=offset,
        limit=limit,
    )


@router.get("/questions/csv-template")
async def get_csv_template(
    current_user: User = Depends(require_role(UserRole.TEACHER, UserRole.ADMIN)),
) -> PlainTextResponse:
    """Download a CSV import template with sample questions."""
    template = (
        "question_text,expected_key_points,difficulty,question_type,explanation,topic_name\n"
        '"Explain the difference between TCP and UDP.","Connection-oriented vs connectionless;Reliability and flow control;Header overhead and speed",medium,conceptual,"TCP guarantees delivery via 3-way handshake while UDP is lightweight.","Transport Layer"\n'
        '"What is a dead-lock in operating systems and how is it detected?","Mutual exclusion;Hold and wait;Resource allocation graph cycle detection",hard,analytical,"A deadlock occurs when a set of processes are blocked waiting for each other.","Process Synchronization"\n'
    )
    return PlainTextResponse(
        content=template,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=questions_template.csv"},
    )


@router.post("/questions/import-csv")
async def import_questions_csv(
    file: UploadFile | None = File(default=None),
    csv_text: str | None = Form(default=None),
    course_id: uuid.UUID | None = Form(default=None),
    topic_id: uuid.UUID | None = Form(default=None),
    current_user: User = Depends(require_role(UserRole.TEACHER, UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Bulk import questions from CSV with row validation and course ownership enforcement."""
    raw_content = ""
    if file is not None:
        raw_bytes = await file.read()
        raw_content = raw_bytes.decode("utf-8-sig", errors="replace")
    elif csv_text:
        raw_content = csv_text.strip()
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please provide a CSV file or csv_text.",
        )

    if not raw_content.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="CSV content is empty.")

    reader = csv.DictReader(io.StringIO(raw_content))
    if not reader.fieldnames:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="CSV must contain a header row."
        )

    teacher_courses_query = select(Course).options(selectinload(Course.topics))
    if current_user.role == UserRole.TEACHER:
        teacher_courses_query = teacher_courses_query.where(Course.teacher_id == current_user.id)
    if course_id:
        teacher_courses_query = teacher_courses_query.where(Course.id == course_id)

    courses_res = await db.execute(teacher_courses_query)
    teacher_courses = courses_res.scalars().all()
    if not teacher_courses:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No matching courses found for this teacher.",
        )

    topic_by_id: dict[str, Topic] = {}
    topic_by_name_lower: dict[str, Topic] = {}
    for c in teacher_courses:
        for t in c.topics or []:
            topic_by_id[str(t.id)] = t
            topic_by_name_lower[t.name.strip().lower()] = t

    default_topic: Topic | None = None
    if topic_id:
        default_topic = topic_by_id.get(str(topic_id))
        if not default_topic:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Specified default topic was not found in your courses.",
            )

    imported_count = 0
    errors: list[str] = []

    for row_idx, row in enumerate(reader, start=2):
        row_norm = {k.strip().lower().replace(" ", "_"): v for k, v in row.items() if k}
        q_text = (
            row_norm.get("question_text") or row_norm.get("question") or row_norm.get("text") or ""
        ).strip()
        if not q_text:
            errors.append(f"Row {row_idx}: Question text is required.")
            continue

        row_topic_id = (row_norm.get("topic_id") or "").strip()
        row_topic_name = (row_norm.get("topic_name") or row_norm.get("topic") or "").strip().lower()

        target_topic: Topic | None = None
        if row_topic_id and row_topic_id in topic_by_id:
            target_topic = topic_by_id[row_topic_id]
        elif row_topic_name and row_topic_name in topic_by_id:
            target_topic = topic_by_id[row_topic_name]
        elif row_topic_name and row_topic_name in topic_by_name_lower:
            target_topic = topic_by_name_lower[row_topic_name]
        elif default_topic:
            target_topic = default_topic
        elif len(topic_by_id) == 1:
            target_topic = next(iter(topic_by_id.values()))
        else:
            errors.append(
                f"Row {row_idx}: Could not match a topic. Specify topic_name or topic_id matching your courses."
            )
            continue

        raw_points = (
            row_norm.get("expected_key_points")
            or row_norm.get("key_points")
            or row_norm.get("rubric")
            or row_norm.get("expected_answer")
            or ""
        )
        points = [
            p.strip()
            for p in raw_points.replace("|", ";").replace("\n", ";").split(";")
            if p.strip()
        ]

        explanation = (
            row_norm.get("explanation")
            or row_norm.get("model_answer")
            or row_norm.get("notes")
            or ""
        ).strip() or None
        if not points:
            if explanation:
                points = [explanation]
            else:
                errors.append(
                    f"Row {row_idx}: At least one expected key point or explanation is required."
                )
                continue

        diff_str = (row_norm.get("difficulty") or "medium").strip().lower()
        if "easy" in diff_str:
            diff = QuestionDifficulty.EASY
        elif "hard" in diff_str:
            diff = QuestionDifficulty.HARD
        else:
            diff = QuestionDifficulty.MEDIUM

        q_type = (row_norm.get("question_type") or row_norm.get("type") or "conceptual").strip()
        raw_tags = (row_norm.get("tags") or "").strip()
        tags = [t.strip() for t in raw_tags.replace(";", ",").split(",") if t.strip()]

        question = Question(
            topic_id=target_topic.id,
            question_text=q_text,
            expected_key_points=points,
            difficulty=diff,
            question_type=q_type if q_type else None,
            explanation=explanation,
            tags=tags,
            is_approved=True,
            generated_by=current_user.id,
        )
        db.add(question)
        imported_count += 1

    if imported_count > 0:
        await db.commit()

    return {
        "imported_count": imported_count,
        "failed_count": len(errors),
        "errors": errors[:30],
        "message": f"Successfully imported {imported_count} questions."
        if imported_count > 0
        else "No questions imported.",
    }


@router.post("/questions", response_model=QuestionResponse, status_code=status.HTTP_201_CREATED)
async def create_question(
    payload: QuestionCreate,
    current_user: User = Depends(require_role(UserRole.TEACHER, UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> QuestionResponse:
    """Create a persistent teacher-managed question."""
    result = await db.execute(
        select(Topic)
        .options(selectinload(Topic.course))
        .join(Course, Topic.course_id == Course.id)
        .where(Topic.id == payload.topic_id)
    )
    topic = result.scalar_one_or_none()
    if topic is None:
        raise HTTPException(status_code=404, detail="Topic not found")
    if current_user.role == UserRole.TEACHER:
        owner_id = await db.scalar(select(Course.teacher_id).where(Course.id == topic.course_id))
        if owner_id != current_user.id:
            raise HTTPException(status_code=403, detail="You cannot manage this course")

    question = Question(
        topic_id=topic.id,
        question_text=payload.question_text.strip(),
        expected_key_points=[
            point.strip() for point in payload.expected_key_points if point.strip()
        ],
        difficulty=payload.difficulty,
        tags=[tag.strip() for tag in payload.tags if tag.strip()],
        question_type=payload.question_type,
        explanation=payload.explanation,
        is_approved=True,
        generated_by=current_user.id,
    )
    db.add(question)
    await db.commit()
    await db.refresh(question)
    question.topic = topic
    return _enrich_question_response(question)


@router.post("/topics/{topic_id}/questions/generate", response_model=list[QuestionResponse])
async def generate_questions_for_topic(
    topic_id: uuid.UUID,
    payload: QuestionGenerateRequest,
    current_user: User = Depends(require_role(UserRole.TEACHER, UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> list[QuestionResponse]:
    """Generate oral-exam questions from uploaded topic material and retrieved chunks."""
    topic_result = await db.execute(
        select(Topic).options(selectinload(Topic.course)).where(Topic.id == topic_id)
    )
    topic = topic_result.scalar_one_or_none()
    if topic is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")
    await _require_topic_owner(topic_id, current_user, db)

    context_chunks: list[str] = []
    indexed_chunks = retrieve_for_topic(
        topic_id, query=f"Key concepts, topics, and definitions for {topic.name}", top_k=5
    )
    if indexed_chunks:
        context_chunks.extend(item["text"] for item in indexed_chunks)
    else:
        document_result = await db.execute(select(Document).where(Document.topic_id == topic_id))
        for document in document_result.scalars().all():
            try:
                with open(document.file_path, "rb") as source_file:
                    content_bytes = source_file.read()
                extracted_text = DocumentService.extract_text(document.filename, content_bytes)
                context_chunks.extend(chunk_text(extracted_text, chunk_size=512, overlap=64)[:5])
            except (OSError, ValueError):
                continue

    if not context_chunks:
        context_chunks = [
            f"Course topic: {topic.name}. Oral examination questions testing core concepts."
        ]
    try:
        await QuestionService().generate_questions(
            topic_id=topic_id,
            context_chunks=context_chunks,
            count=payload.count,
            topic_name=topic.name,
            db=db,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    saved_result = await db.execute(
        select(Question)
        .options(selectinload(Question.topic).selectinload(Topic.course))
        .where(Question.topic_id == topic_id)
        .order_by(Question.created_at.desc())
        .limit(payload.count)
    )
    return [_enrich_question_response(item) for item in saved_result.scalars().all()]


@router.get("/topics/{topic_id}/questions", response_model=list[QuestionResponse])
async def list_questions(
    topic_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[QuestionResponse]:
    """Retrieve the questions for a topic."""
    topic_result = await db.execute(select(Topic).where(Topic.id == topic_id))
    if topic_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")
    await _require_topic_owner(topic_id, current_user, db)
    result = await db.execute(
        select(Question)
        .options(selectinload(Question.topic).selectinload(Topic.course))
        .where(Question.topic_id == topic_id)
        .order_by(Question.created_at.desc())
    )
    return [_enrich_question_response(item) for item in result.scalars().all()]


@router.get("/questions/{question_id}", response_model=QuestionResponse)
async def get_question(
    question_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> QuestionResponse:
    """Fetch a specific question by identifier."""
    result = await db.execute(
        select(Question)
        .options(selectinload(Question.topic).selectinload(Topic.course))
        .where(Question.id == question_id)
    )
    question = result.scalar_one_or_none()
    if question is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found")
    if current_user.role == UserRole.TEACHER:
        await _require_topic_owner(question.topic_id, current_user, db)
    return _enrich_question_response(question)


@router.put("/questions/{question_id}", response_model=QuestionResponse)
async def update_question(
    question_id: uuid.UUID,
    payload: QuestionUpdate,
    current_user: User = Depends(require_role(UserRole.TEACHER, UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> QuestionResponse:
    """Update an existing question, enforcing course ownership."""
    question = await _question_for_teacher(question_id, current_user, db)
    if payload.question_text is not None:
        question.question_text = payload.question_text.strip()
    if payload.expected_key_points is not None:
        question.expected_key_points = payload.expected_key_points
    if payload.difficulty is not None:
        question.difficulty = payload.difficulty
    if payload.is_approved is not None:
        question.is_approved = payload.is_approved
    if payload.tags is not None:
        question.tags = [tag.strip() for tag in payload.tags if tag.strip()]
    if payload.question_type is not None:
        question.question_type = payload.question_type
    if payload.explanation is not None:
        question.explanation = payload.explanation
    await db.commit()
    await db.refresh(question)
    return _enrich_question_response(question)


@router.post("/questions/{question_id}/approve", response_model=QuestionResponse)
async def approve_question(
    question_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.TEACHER, UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> QuestionResponse:
    """Approve a generated question after verifying course ownership."""
    question = await _question_for_teacher(question_id, current_user, db)
    question.is_approved = True
    await db.commit()
    await db.refresh(question)
    return _enrich_question_response(question)


@router.delete("/questions/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_question(
    question_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.TEACHER, UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a question after verifying course ownership."""
    question = await _question_for_teacher(question_id, current_user, db)
    await db.delete(question)
    await db.commit()
