"""API package router aggregator."""

from fastapi import APIRouter

from app.api.assessments import router as assessments_router
from app.api.assignments import router as assignments_router
from app.api.auth import router as auth_router
from app.api.consent import router as consent_router
from app.api.courses import router as courses_router
from app.api.documents import router as documents_router
from app.api.institutions import router as institutions_router
from app.api.questions import router as questions_router
from app.api.reports import router as reports_router
from app.api.topics import router as topics_router
from app.api.users import router as users_router
from app.api.viva import router as viva_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(courses_router)
api_router.include_router(topics_router)
api_router.include_router(documents_router)
api_router.include_router(questions_router)
api_router.include_router(consent_router)
api_router.include_router(users_router)
api_router.include_router(viva_router)
api_router.include_router(reports_router)
api_router.include_router(institutions_router)
api_router.include_router(assessments_router)
api_router.include_router(assignments_router)

__all__ = ["api_router"]
