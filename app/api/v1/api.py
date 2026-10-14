from fastapi import APIRouter
from app.api.v1.endpoints import auth, products, scan, history, admin_review, ai_analysis

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(products.router, prefix="/products", tags=["Products"])
api_router.include_router(scan.router, prefix="/scan", tags=["Scan"])
api_router.include_router(history.router, prefix="/history", tags=["History"])
api_router.include_router(admin_review.router, prefix="/admin", tags=["Admin Review"])
api_router.include_router(ai_analysis.router, prefix="/ai", tags=["AI Analysis"])
