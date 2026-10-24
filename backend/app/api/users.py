"""User-level maintenance endpoints for privacy and media cleanup."""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.answer import Answer
from app.models.user import User
from app.models.viva_session import VivaSession

router = APIRouter(prefix="/users", tags=["Users"])


@router.delete("/{user_id}/audio", response_model=dict)
async def delete_user_audio(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, int | str]:
    """Delete all stored audio for a user and clear the answer audio paths."""
    if current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="You can only delete your own audio files"
        )

    result = await db.execute(
        select(Answer)
        .join(VivaSession, Answer.session_id == VivaSession.id)
        .where(VivaSession.student_id == user_id)
    )
    answers = result.scalars().all()

    deleted_count = 0
    for answer in answers:
        if answer.audio_path:
            file_path = Path(answer.audio_path)
            if file_path.exists():
                file_path.unlink()
            wav_path = file_path.with_suffix(".wav")
            if wav_path != file_path and wav_path.exists():
                wav_path.unlink()
            deleted_count += 1
            answer.audio_path = None

    await db.commit()
    return {"deleted_count": deleted_count, "user_id": str(user_id)}
