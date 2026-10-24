"""Document upload and indexing endpoints."""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_role
from app.models.course import Course
from app.models.document import Document, DocumentStatus
from app.models.topic import Topic
from app.models.user import User, UserRole
from app.schemas.document import DocumentResponse
from app.services.document_service import DocumentService
from app.services.rag_service import build_index, chunk_text

router = APIRouter(tags=["Documents"])


@router.post(
    "/topics/{topic_id}/documents",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    topic_id: uuid.UUID,
    file: UploadFile = File(...),
    current_user: User = Depends(require_role(UserRole.TEACHER, UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> DocumentResponse:
    """Upload a file to a course topic and record its metadata."""
    topic_result = await db.execute(select(Topic).where(Topic.id == topic_id))
    topic = topic_result.scalar_one_or_none()
    if topic is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")

    if current_user.role == UserRole.TEACHER:
        owner_id = await db.scalar(select(Course.teacher_id).where(Course.id == topic.course_id))
        if owner_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not authorized to upload documents to this topic",
            )

    try:
        saved = await DocumentService.save_upload(file, topic_id)
        content = DocumentService.extract_text(
            file.filename or "document.txt", saved["raw_content"]
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    chunks = chunk_text(content, chunk_size=512, overlap=64)
    document = Document(
        topic_id=topic_id,
        filename=saved["filename"],
        file_path=saved["file_path"],
        content_hash=saved["content_hash"],
        status=DocumentStatus.UPLOADED,
        chunk_count=len(chunks),
    )
    db.add(document)
    await db.commit()
    await db.refresh(document)
    return DocumentResponse.model_validate(document)


@router.get("/topics/{topic_id}/documents", response_model=list[DocumentResponse])
async def list_documents(
    topic_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[DocumentResponse]:
    """List every uploaded document for a topic."""
    topic_result = await db.execute(select(Topic).where(Topic.id == topic_id))
    topic = topic_result.scalar_one_or_none()
    if topic is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")

    if current_user.role == UserRole.TEACHER:
        owner_id = await db.scalar(select(Course.teacher_id).where(Course.id == topic.course_id))
        if owner_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not authorized to access documents for this topic",
            )

    result = await db.execute(
        select(Document).where(Document.topic_id == topic_id).order_by(Document.created_at.desc())
    )
    documents = result.scalars().all()
    return [DocumentResponse.model_validate(item) for item in documents]


@router.post("/documents/{document_id}/embed", response_model=DocumentResponse)
async def embed_document(
    document_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.TEACHER, UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> DocumentResponse:
    """Chunk and embed the content of a saved document into the topic embedding index."""
    result = await db.execute(select(Document).where(Document.id == document_id))
    document = result.scalar_one_or_none()
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    if current_user.role == UserRole.TEACHER:
        owner_id = await db.scalar(
            select(Course.teacher_id)
            .join(Topic, Topic.course_id == Course.id)
            .where(Topic.id == document.topic_id)
        )
        if owner_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not authorized to embed this document",
            )

    file_path = Path(document.file_path)
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Stored file no longer exists"
        )

    try:
        text = DocumentService.extract_text(document.filename, file_path.read_bytes())
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    chunks = chunk_text(text, chunk_size=512, overlap=64)
    build_index(document.topic_id, chunks)
    document.chunk_count = len(chunks)
    document.status = DocumentStatus.EMBEDDED
    await db.commit()
    await db.refresh(document)
    return DocumentResponse.model_validate(document)


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.TEACHER, UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Remove a document record and delete its stored file from disk."""
    result = await db.execute(select(Document).where(Document.id == document_id))
    document = result.scalar_one_or_none()
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    if current_user.role == UserRole.TEACHER:
        owner_id = await db.scalar(
            select(Course.teacher_id)
            .join(Topic, Topic.course_id == Course.id)
            .where(Topic.id == document.topic_id)
        )
        if owner_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not authorized to delete this document",
            )

    file_path = Path(document.file_path)
    if file_path.exists():
        file_path.unlink()

    await db.delete(document)
    await db.commit()
