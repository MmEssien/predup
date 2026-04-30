
import os
from sqlalchemy import create_engine, inspect

database_url = os.getenv("DATABASE_URL")
if not database_url:
    print("DATABASE_URL not set")
    exit(1)

engine = create_engine(database_url)
inspector = inspect(engine)
tables = inspector.get_table_names()
print(f"Tables found: {tables}")
