from src.database import create_db_and_tables
from src.models import *

try:
    create_db_and_tables()
    print("Tables Created")
except BaseException as e:  # noqa: BLE001
    print("Failed to Create tables. They may all ready exist.", e)
