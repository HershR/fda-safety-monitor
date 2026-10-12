import json
from datetime import date
from pathlib import Path

from sqlalchemy.dialects.postgresql import insert
from sqlmodel import Session

from src.database import engine
from src.models import FiscalYear, State

DATA_DIR = f"{Path(__file__).parent}/data"


def load_json(name):
    return json.loads(f"{DATA_DIR}/{name}")


def seed_db():
    with open(f"{DATA_DIR}/state_codes.json", "r") as file:
        states = json.load(file)
    with open(f"{DATA_DIR}/fiscal_years.json", "r") as file:
        fiscal_year = json.load(file)
        years = [
            {
                "fiscal_year": fy["fiscal_year"],
                "fy_start": date.fromisoformat(fy["fy_start"]),
                "fy_end": date.fromisoformat(fy["fy_end"]),
            }
            for fy in fiscal_year
        ]
    with Session(engine) as session:
        session.exec(
            insert(State)
            .values(states)
            .on_conflict_do_nothing(index_elements=["state_code"])
        )
        session.exec(
            insert(FiscalYear)
            .values(years)
            .on_conflict_do_nothing(index_elements=["fiscal_year"])
        )
        session.commit()
