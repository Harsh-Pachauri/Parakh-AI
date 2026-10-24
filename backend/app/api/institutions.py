"""Institution and administration endpoints."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_role
from app.models.institution import Institution
from app.models.user import User, UserRole
from app.schemas.institution import (
    InstitutionAdminCreate,
    InstitutionAdminResponse,
    InstitutionCreate,
    InstitutionResponse,
    TeacherCreate,
    TeacherResponse,
)
from app.services.auth_service import hash_password

router = APIRouter(tags=["Institutions"])


# ============================================================================
# Platform Admin Endpoints
# ============================================================================


@router.post(
    "/admin/institutions", response_model=InstitutionResponse, status_code=status.HTTP_201_CREATED
)
async def create_institution(
    payload: InstitutionCreate,
    current_user: User = Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> InstitutionResponse:
    """Create a new institution (Platform Admin only)."""
    name_clean = payload.name.strip()
    code_clean = payload.code.strip().upper()

    existing_query = await db.execute(
        select(Institution).where(
            or_(
                Institution.name.ilike(name_clean),
                Institution.code.ilike(code_clean),
            )
        )
    )
    if existing_query.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An institution with this name or code already exists",
        )

    institution = Institution(
        name=name_clean,
        code=code_clean,
        is_active=True,
    )
    db.add(institution)
    await db.commit()
    await db.refresh(institution)
    return InstitutionResponse.model_validate(institution)


@router.get("/admin/institutions", response_model=list[InstitutionResponse])
async def list_institutions(
    current_user: User = Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> list[InstitutionResponse]:
    """List all institutions (Platform Admin only)."""
    result = await db.execute(select(Institution).order_by(Institution.created_at.desc()))
    institutions = result.scalars().all()
    return [InstitutionResponse.model_validate(inst) for inst in institutions]


@router.post(
    "/admin/institutions/{institution_id}/admins",
    response_model=InstitutionAdminResponse,
    status_code=status.HTTP_201_CREATED,
)
async def appoint_institution_admin(
    institution_id: uuid.UUID,
    payload: InstitutionAdminCreate,
    current_user: User = Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> InstitutionAdminResponse:
    """Appoint an administrator to a specific institution (Platform Admin only)."""
    inst_result = await db.execute(select(Institution).where(Institution.id == institution_id))
    institution = inst_result.scalar_one_or_none()
    if institution is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Institution not found",
        )

    existing_user_query = await db.execute(select(User).where(User.email == payload.email))
    if existing_user_query.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email is already registered",
        )

    admin_user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name.strip(),
        role=UserRole.INSTITUTION_ADMIN,
        institution_id=institution.id,
    )
    db.add(admin_user)
    await db.commit()
    await db.refresh(admin_user)

    return InstitutionAdminResponse(
        id=admin_user.id,
        email=admin_user.email,
        full_name=admin_user.full_name,
        role=admin_user.role.value,
        institution_id=institution.id,
        created_at=admin_user.created_at,
    )


# ============================================================================
# Institution Admin Endpoints (Scoped strictly to caller's institution)
# ============================================================================


def _require_institution_admin(user: User) -> None:
    """Ensure the user is an Institution Admin with an assigned institution."""
    if user.role != UserRole.INSTITUTION_ADMIN or not user.institution_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operation permitted only for institution administrators with an assigned institution",
        )


@router.get(
    "/institution/profile",
    response_model=InstitutionResponse,
)
async def get_institution_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> InstitutionResponse:
    """Return the institution profile metadata for the authenticated institution admin."""
    _require_institution_admin(current_user)

    inst_result = await db.execute(
        select(Institution).where(Institution.id == current_user.institution_id)
    )
    institution = inst_result.scalar_one_or_none()
    if institution is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Institution not found",
        )

    return InstitutionResponse.model_validate(institution)


@router.post(
    "/institution/teachers",
    response_model=TeacherResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_institution_teacher(
    payload: TeacherCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TeacherResponse:
    """Register a teacher account bound strictly to the caller's institution."""
    _require_institution_admin(current_user)

    inst_result = await db.execute(
        select(Institution).where(Institution.id == current_user.institution_id)
    )
    institution = inst_result.scalar_one_or_none()
    if institution is None or not institution.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Institution is inactive or not found",
        )

    existing_user_query = await db.execute(select(User).where(User.email == payload.email))
    if existing_user_query.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email is already registered",
        )

    teacher_user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name.strip(),
        role=UserRole.TEACHER,
        institution_id=current_user.institution_id,
    )
    db.add(teacher_user)
    await db.commit()
    await db.refresh(teacher_user)

    return TeacherResponse(
        id=teacher_user.id,
        email=teacher_user.email,
        full_name=teacher_user.full_name,
        role=teacher_user.role.value,
        institution_id=current_user.institution_id,
        created_at=teacher_user.created_at,
    )


@router.get(
    "/institution/teachers",
    response_model=list[TeacherResponse],
)
async def list_institution_teachers(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[TeacherResponse]:
    """List all teachers belonging strictly to the caller's institution."""
    _require_institution_admin(current_user)

    result = await db.execute(
        select(User)
        .where(
            User.institution_id == current_user.institution_id,
            User.role == UserRole.TEACHER,
        )
        .order_by(User.created_at.desc())
    )
    teachers = result.scalars().all()

    return [
        TeacherResponse(
            id=t.id,
            email=t.email,
            full_name=t.full_name,
            role=t.role.value,
            institution_id=current_user.institution_id,
            created_at=t.created_at,
        )
        for t in teachers
    ]
