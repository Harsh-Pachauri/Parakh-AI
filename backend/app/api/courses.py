"""Course management endpoints."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_db, require_role
from app.models.course import Course
from app.models.topic import Topic
from app.models.user import User, UserRole
from app.schemas.course import CourseCreate, CourseResponse, CourseUpdate, TopicUpdate
from app.services.llm_service import get_provider

router = APIRouter(prefix="/courses", tags=["Courses"])

_SYLLABUS_SCHEMA = {
    "type": "object",
    "properties": {
        "modules": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "topics": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "subtopics": {"type": "array", "items": {"type": "string"}},
                                "key_concepts": {"type": "array", "items": {"type": "string"}},
                                "learning_objectives": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "prerequisites": {"type": "array", "items": {"type": "string"}},
                                "question_types": {
                                    "type": "array",
                                    "items": {
                                        "type": "string",
                                        "enum": [
                                            "conceptual",
                                            "practical",
                                            "analytical",
                                            "application",
                                        ],
                                    },
                                },
                            },
                            "required": ["name", "subtopics", "key_concepts"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["name", "topics"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["modules"],
    "additionalProperties": False,
}


def _strings(value: object, label: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"Invalid syllabus analysis field: {label}")
    return [item.strip() for item in value if item.strip()]


def _syllabus_chunks(text: str, chunk_size: int = 6000) -> list[tuple[int, int, str]]:
    chunks: list[tuple[int, int, str]] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        if end < len(text):
            boundary = text.rfind("\n", start + chunk_size // 2, end)
            if boundary > start:
                end = boundary + 1
        chunks.append((start, end, text[start:end]))
        start = end
    return chunks


def _merge_syllabus_sections(results: list[dict]) -> dict:
    modules_by_name: dict[str, dict] = {}
    for result in results:
        if not isinstance(result, dict):
            raise ValueError("Groq returned an invalid syllabus analysis object.")
        source_reference = result.get("_source_reference")
        modules = result.get("modules")
        if not isinstance(modules, list):
            raise ValueError("Groq returned invalid syllabus modules.")
        for module in modules:
            if not isinstance(module, dict) or not isinstance(module.get("name"), str):
                raise ValueError("Groq returned an invalid syllabus module.")
            name = module["name"].strip()
            if not name or not isinstance(module.get("topics"), list):
                raise ValueError("Groq returned an invalid syllabus module.")
            key = name.casefold()
            merged_module = modules_by_name.setdefault(key, {"name": name, "topics": []})
            topics_by_name = {item["name"].casefold(): item for item in merged_module["topics"]}
            for topic in module["topics"]:
                if not isinstance(topic, dict) or not isinstance(topic.get("name"), str):
                    raise ValueError("Groq returned an invalid syllabus topic.")
                topic_name = topic["name"].strip()
                if not topic_name:
                    raise ValueError("Groq returned an empty syllabus topic.")
                normalized = {
                    "name": topic_name,
                    "subtopics": _strings(topic.get("subtopics", []), "subtopics"),
                    "key_concepts": _strings(topic.get("key_concepts", []), "key_concepts"),
                    "learning_objectives": _strings(
                        topic.get("learning_objectives", []), "learning_objectives"
                    ),
                    "prerequisites": _strings(topic.get("prerequisites", []), "prerequisites"),
                    "question_types": _strings(topic.get("question_types", []), "question_types"),
                    "source_references": [source_reference] if source_reference else [],
                }
                topic_key = topic_name.casefold()
                if topic_key not in topics_by_name:
                    merged_module["topics"].append(normalized)
                    topics_by_name[topic_key] = normalized
                else:
                    existing = topics_by_name[topic_key]
                    for field in normalized:
                        if field != "name":
                            combined = existing[field] + normalized[field]
                            existing[field] = [
                                item
                                for index, item in enumerate(combined)
                                if item not in combined[:index]
                            ]
                    if source_reference and source_reference not in existing["source_references"]:
                        existing["source_references"].append(source_reference)
    return {"modules": list(modules_by_name.values())}


@router.post("", response_model=CourseResponse, status_code=status.HTTP_201_CREATED)
async def create_course(
    payload: CourseCreate,
    current_user: User = Depends(require_role(UserRole.TEACHER, UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> CourseResponse:
    """Create a new course. Restricted to teachers and admins."""
    if payload.interview_config.topic_ids:
        raise HTTPException(
            status_code=422,
            detail="Interview topic IDs can only be selected after course topics exist.",
        )
    code_check = await db.execute(select(Course).where(Course.code == payload.code))
    if code_check.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Course with code '{payload.code}' already exists",
        )

    course = Course(
        teacher_id=current_user.id,
        name=payload.name,
        code=payload.code,
        subject=payload.subject,
        description=payload.description,
        academic_level=payload.academic_level,
        syllabus_text=payload.syllabus_text,
        interview_config=payload.interview_config.model_dump(mode="json"),
    )
    db.add(course)
    await db.commit()

    result = await db.execute(
        select(Course).options(selectinload(Course.topics)).where(Course.id == course.id)
    )
    course_loaded = result.scalar_one()
    return CourseResponse.model_validate(course_loaded)


@router.get("", response_model=list[CourseResponse])
async def list_courses(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[CourseResponse]:
    """List courses. Teachers see their own courses; students see all available courses."""
    query = select(Course).options(selectinload(Course.topics))
    if current_user.role == UserRole.TEACHER:
        query = query.where(Course.teacher_id == current_user.id)

    result = await db.execute(query.order_by(Course.created_at.desc()))
    courses = result.scalars().all()
    return [CourseResponse.model_validate(c) for c in courses]


@router.get("/{course_id}", response_model=CourseResponse)
async def get_course(
    course_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CourseResponse:
    """Get details of a single course including its topics."""
    result = await db.execute(
        select(Course).options(selectinload(Course.topics)).where(Course.id == course_id)
    )
    course = result.scalar_one_or_none()
    if course is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course not found",
        )
    if current_user.role == UserRole.TEACHER and course.teacher_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Course not found")

    return CourseResponse.model_validate(course)


@router.put("/{course_id}", response_model=CourseResponse)
async def update_course(
    course_id: uuid.UUID,
    payload: CourseUpdate,
    current_user: User = Depends(require_role(UserRole.TEACHER, UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> CourseResponse:
    """Update a course. Only the creator teacher or admin can modify."""
    result = await db.execute(
        select(Course).options(selectinload(Course.topics)).where(Course.id == course_id)
    )
    course = result.scalar_one_or_none()
    if course is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course not found",
        )

    if current_user.role == UserRole.TEACHER and course.teacher_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to edit this course",
        )

    if payload.code is not None and payload.code != course.code:
        code_check = await db.execute(select(Course).where(Course.code == payload.code))
        if code_check.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Course with code '{payload.code}' already exists",
            )
        course.code = payload.code

    if payload.name is not None:
        course.name = payload.name
    if "subject" in payload.model_fields_set:
        course.subject = payload.subject
    if payload.description is not None:
        course.description = payload.description
    if "academic_level" in payload.model_fields_set:
        course.academic_level = payload.academic_level
    if "syllabus_text" in payload.model_fields_set:
        course.syllabus_text = payload.syllabus_text
    if (
        "syllabus_text" in payload.model_fields_set
        and course.syllabus_text != payload.syllabus_text
    ):
        course.syllabus_analysis = None
        course.syllabus_text = payload.syllabus_text
    if payload.interview_config is not None:
        selected_topics = set(payload.interview_config.topic_ids)
        if selected_topics:
            course_topics = set(
                (
                    await db.execute(
                        select(Topic.id).where(
                            Topic.course_id == course.id,
                            Topic.id.in_(selected_topics),
                        )
                    )
                ).scalars()
            )
            if course_topics != selected_topics:
                raise HTTPException(
                    status_code=422,
                    detail="Interview topics must belong to this course.",
                )
        course.interview_config = payload.interview_config.model_dump(mode="json")

    await db.commit()
    await db.refresh(course)
    return CourseResponse.model_validate(course)


@router.put(
    "/{course_id}/syllabus/topics/{topic_id}",
    response_model=CourseResponse,
)
async def update_syllabus_topic(
    course_id: uuid.UUID,
    topic_id: uuid.UUID,
    payload: TopicUpdate,
    current_user: User = Depends(require_role(UserRole.TEACHER, UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> CourseResponse:
    """Edit an extracted syllabus topic and keep the saved analysis synchronized."""
    course = await db.get(Course, course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    if current_user.role == UserRole.TEACHER and course.teacher_id != current_user.id:
        raise HTTPException(status_code=403, detail="You cannot manage this course")
    topic = await db.scalar(select(Topic).where(Topic.id == topic_id, Topic.course_id == course_id))
    if topic is None:
        raise HTTPException(status_code=404, detail="Syllabus topic not found")
    if not payload.name:
        raise HTTPException(status_code=422, detail="A topic name is required")

    previous_name = topic.name
    topic.name = payload.name.strip()
    analysis = dict(course.syllabus_analysis or {})
    for module in analysis.get("modules", []):
        for item in module.get("topics", []):
            if item.get("name", "").casefold() == previous_name.casefold():
                item["name"] = topic.name
    if course.syllabus_analysis is not None:
        course.syllabus_analysis = analysis
    if payload.sort_order is not None:
        topic.sort_order = payload.sort_order
    await db.commit()
    refreshed = await db.execute(
        select(Course).options(selectinload(Course.topics)).where(Course.id == course_id)
    )
    return CourseResponse.model_validate(refreshed.scalar_one())


@router.delete("/{course_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_course(
    course_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.TEACHER, UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a course. Only the creator teacher or admin can delete."""
    result = await db.execute(select(Course).where(Course.id == course_id))
    course = result.scalar_one_or_none()
    if course is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course not found",
        )

    if current_user.role == UserRole.TEACHER and course.teacher_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to delete this course",
        )

    await db.delete(course)
    await db.commit()


@router.post("/{course_id}/syllabus/analyze", response_model=CourseResponse)
async def analyze_syllabus(
    course_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.TEACHER, UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> CourseResponse:
    """Extract reviewable topics from the saved syllabus without replacing its source text."""
    result = await db.execute(select(Course).where(Course.id == course_id))
    course = result.scalar_one_or_none()
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    if current_user.role == UserRole.TEACHER and course.teacher_id != current_user.id:
        raise HTTPException(status_code=403, detail="You cannot manage this course")
    if not course.syllabus_text or not course.syllabus_text.strip():
        raise HTTPException(status_code=422, detail="Save syllabus text before analyzing it")

    provider = get_provider()
    analyses = []
    try:
        for index, (start, end, section) in enumerate(_syllabus_chunks(course.syllabus_text), 1):
            prompt = (
                "Analyze only the syllabus content below. Do not add topics not present in it. "
                "Extract modules and detailed topics, subtopics, key concepts, learning objectives "
                "when stated, prerequisites when identifiable, and suitable question types. "
                "Return the required JSON object. Keep the topic/module names grounded in the "
                "source wording.\n"
                f"Course: {course.name}\nSubject: {course.code}\n"
                f"Academic level: {course.academic_level or 'unspecified'}\n"
                f"Source section {index}; character range [{start}, {end}):\n{section}"
            )
            section_analysis = await provider.generate(prompt, schema=_SYLLABUS_SCHEMA)
            if isinstance(section_analysis, dict):
                section_analysis["_source_reference"] = {
                    "section": index,
                    "start": start,
                    "end": end,
                }
            analyses.append(section_analysis)
        analysis = _merge_syllabus_sections(analyses)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=f"Syllabus analysis failed: {exc}") from exc

    analysis["source_length"] = len(course.syllabus_text)
    analysis["analyzed_at"] = datetime.now(UTC).isoformat()
    course.syllabus_analysis = analysis
    existing_topics_result = await db.execute(select(Topic).where(Topic.course_id == course_id))
    existing_topics = existing_topics_result.scalars().all()
    known_names = {item.name.casefold() for item in existing_topics}
    next_order = max((item.sort_order for item in existing_topics), default=-1) + 1
    for module in analysis["modules"]:
        for syllabus_topic in module["topics"]:
            if syllabus_topic["name"].casefold() not in known_names:
                db.add(
                    Topic(
                        course_id=course_id,
                        name=syllabus_topic["name"],
                        sort_order=next_order,
                    )
                )
                next_order += 1
                known_names.add(syllabus_topic["name"].casefold())
    await db.commit()
    refreshed = await db.execute(
        select(Course).options(selectinload(Course.topics)).where(Course.id == course_id)
    )
    return CourseResponse.model_validate(refreshed.scalar_one())
