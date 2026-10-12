from fastapi import APIRouter, HTTPException
from sqlmodel import select
from src.database import SessionDep
from src.models import FiscalYear

router = APIRouter()


@router.get("/", response_model=list[FiscalYear])
async def get_fiscal_years(session: SessionDep):
    years = session.exec(select(FiscalYear)).all()
    return years


@router.get("/{year}", response_model=FiscalYear)
async def get_fiscal_year(session: SessionDep, year: int):
    statement = select(FiscalYear).where(FiscalYear.fiscal_year == year)
    result = session.exec(statement).first()
    if not result:
        raise HTTPException(
            status_code=404,
            detail=f"Fiscal year with year {year} was not found",
        )
    return result


@router.post("/find_or_create", status_code=201, response_model=FiscalYear)
async def find_or_create_fiscal_year(
    session: SessionDep, fiscal_year: FiscalYear
):
    existing_state = session.exec(
        select(FiscalYear).where(
            FiscalYear.fiscal_year == fiscal_year.fiscal_year
        )
    ).first()
    if existing_state:
        return existing_state
    session.add(fiscal_year)
    session.commit()
    session.refresh(fiscal_year)
    return fiscal_year
