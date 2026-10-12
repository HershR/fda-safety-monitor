from typing import Annotated

from fastapi import Depends
from sqlmodel import Session, create_engine

from src.config import *
from src.models import *

engine = create_engine(DATABASE_URI, echo=True)


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]
