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


@router.post("/", status_code=201, response_model=FiscalYear)
async def create_fiscal_year(session: SessionDep, fiscal_year: FiscalYear):
    session.add(fiscal_year)
    try:
        session.commit()
    except BaseException as e:
        print(e)
        raise HTTPException(status_code=500, detail="Internal Server Error")
    session.refresh(fiscal_year)
    return fiscal_year
