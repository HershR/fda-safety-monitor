# Paritally inspired by this discussion: https://github.com/fastapi/sqlmodel/issues/59
from itertools import batched

from sqlalchemy.dialects.postgresql import insert
from sqlmodel import Session, SQLModel

BATCH_SIZE = 1000


def save_row(session: Session, row: SQLModel, update: bool = True):
    """
    Insert row. If row exists then it is updated, or skipped when update=False.
    Method DOES not commit changes, trigger commit when method returns.
    """
    if not row:
        return
    table = type(row)
    pks = table.__table__.primary_key.columns.keys()
    new_values = row.model_dump()
    stmt = insert(table).values(new_values)
    if update:
        new_values = {c: stmt.excluded[c] for c in new_values if c not in pks}
        stmt = stmt.on_conflict_do_update(index_elements=pks, set_=new_values)
    else:
        stmt = stmt.on_conflict_do_nothing(index_elements=pks)
    session.exec(stmt)


def save_rows(session: Session, rows: list[SQLModel], update: bool = True):
    """
    Insert rows. Existing rows are updated, or skipped when update=False.
    Method DOES not commit changes, trigger commit when method returns.
    """
    if not rows:
        return 0

    table = type(rows[0])
    pks = table.__table__.primary_key.columns.keys()

    # remove duplicate rows if any
    unique = {}
    for r in rows:
        key = tuple(getattr(r, k) for k in pks)
        unique[key] = r.model_dump()

    for batch in batched(unique.values(), BATCH_SIZE):
        stmt = insert(table).values(batch)
        if update:
            new_values = {
                c: stmt.excluded[c] for c in batch[0] if c not in pks
            }
            stmt = stmt.on_conflict_do_update(
                index_elements=pks, set_=new_values
            )
        else:
            stmt = stmt.on_conflict_do_nothing(index_elements=pks)
        session.exec(stmt)

    return len(unique)
