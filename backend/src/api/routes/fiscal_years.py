from fastapi import APIRouter, HTTPException, Response, status
from sqlmodel import select
from src.database import SessionDep
from src.models import FiscalYear

router = APIRouter()


@router.get("/", response_model=list[FiscalYear])
async def get_fiscal_years(session: SessionDep):
    """Get all USA Government fiscal years"""
    years = session.exec(select(FiscalYear)).all()
    return years


@router.get("/{year}", response_model=FiscalYear)
async def get_fiscal_year(session: SessionDep, year: int):
    """Fetch a fiscal year's details"""
    statement = select(FiscalYear).where(FiscalYear.fiscal_year == year)
    result = session.exec(statement).first()
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Fiscal year with year {year} was not found",
        )
    return result


@router.post(
    "/find_or_create",
    status_code=status.HTTP_201_CREATED,
    response_model=FiscalYear,
)
async def find_or_create_fiscal_year(
    session: SessionDep, fiscal_year: FiscalYear, response: Response
):
    """Create a new Fiscal year, if it exists return it"""
    existing_state = session.exec(
        select(FiscalYear).where(
            FiscalYear.fiscal_year == fiscal_year.fiscal_year
        )
    ).first()
    if existing_state:
        response.status_code = status.HTTP_200_OK
        return existing_state
    session.add(fiscal_year)
    session.commit()
    session.refresh(fiscal_year)
    return fiscal_year
