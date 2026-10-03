from fastapi import APIRouter
from src.api.routes import fiscal_years, recall_scraper, states

api_router = APIRouter()

api_router.include_router(
    fiscal_years.router, prefix="/fiscal_years", tags=["FiscalYears"]
)
api_router.include_router(states.router, prefix="/states", tags=["States"])
api_router.include_router(
    recall_scraper.router, prefix="/fda-recalls", tags=["FDARecalls"]
)
