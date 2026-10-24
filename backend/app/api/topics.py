"""Topic management endpoints."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_role
from app.models.course import Course
from app.models.topic import Topic
from app.models.user import User, UserRole
from app.schemas.course import TopicCreate, TopicResponse, TopicUpdate

router = APIRouter(tags=["Topics"])


@router.post(
    "/courses/{course_id}/topics",
    response_model=TopicResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_topic(
    course_id: uuid.UUID,
    payload: TopicCreate,
    current_user: User = Depends(require_role(UserRole.TEACHER, UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> TopicResponse:
    """Add a topic to a course. Restricted to course teacher or admin."""
    course_query = await db.execute(select(Course).where(Course.id == course_id))
    course = course_query.scalar_one_or_none()
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")

    if current_user.role == UserRole.TEACHER and course.teacher_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to add topics to this course",
        )

    topic = Topic(
        course_id=course_id,
        name=payload.name,
        sort_order=payload.sort_order,
    )
    db.add(topic)
    await db.commit()
    await db.refresh(topic)
    return TopicResponse.model_validate(topic)


@router.get("/courses/{course_id}/topics", response_model=list[TopicResponse])
async def list_topics(
    course_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[TopicResponse]:
    """List all topics for a given course."""
    course_query = await db.execute(select(Course).where(Course.id == course_id))
    course = course_query.scalar_one_or_none()
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")

    if current_user.role == UserRole.TEACHER and course.teacher_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to view topics for this course",
        )

    result = await db.execute(
        select(Topic).where(Topic.course_id == course_id).order_by(Topic.sort_order)
    )
    topics = result.scalars().all()
    return [TopicResponse.model_validate(t) for t in topics]


@router.put("/topics/{topic_id}", response_model=TopicResponse)
async def update_topic(
    topic_id: uuid.UUID,
    payload: TopicUpdate,
    current_user: User = Depends(require_role(UserRole.TEACHER, UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> TopicResponse:
    """Update a topic. Restricted to the course owner or admin."""
    result = await db.execute(select(Topic).join(Course).where(Topic.id == topic_id))
    topic = result.scalar_one_or_none()
    if topic is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")

    course_query = await db.execute(select(Course).where(Course.id == topic.course_id))
    course = course_query.scalar_one()
    if current_user.role == UserRole.TEACHER and course.teacher_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to update this topic",
        )

    if payload.name is not None:
        topic.name = payload.name
    if payload.sort_order is not None:
        topic.sort_order = payload.sort_order

    await db.commit()
    await db.refresh(topic)
    return TopicResponse.model_validate(topic)


@router.delete("/topics/{topic_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_topic(
    topic_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.TEACHER, UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a topic from a course."""
    result = await db.execute(select(Topic).where(Topic.id == topic_id))
    topic = result.scalar_one_or_none()
    if topic is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")

    course_query = await db.execute(select(Course).where(Course.id == topic.course_id))
    course = course_query.scalar_one()
    if current_user.role == UserRole.TEACHER and course.teacher_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to delete this topic",
        )

    await db.delete(topic)
    await db.commit()
