from fastapi import APIRouter
from app.api.v1.endpoints import auth, products, scan, history
from app.services.gemini_service import gemini_service

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(products.router, prefix="/products", tags=["Products"])
api_router.include_router(scan.router, prefix="/scan", tags=["Scan"])
api_router.include_router(history.router, prefix="/history", tags=["History"])