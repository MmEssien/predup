
import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

database_url = os.getenv("DATABASE_URL")
if not database_url:
    print("DATABASE_URL not set")
    exit(1)

engine = create_engine(database_url)
Session = sessionmaker(bind=engine)
session = Session()

tables = ["fixtures", "predictions", "odds_data", "competitions", "teams", "prediction_history", "pipeline_state"]

print("--- DATABASE FORENSICS ---")
for table in tables:
    try:
        count = session.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
        last_updated = session.execute(text(f"SELECT MAX(created_at) FROM {table}")).scalar()
        print(f"Table: {table:20} | Count: {count:6} | Last Updated: {last_updated}")
    except Exception as e:
        print(f"Table: {table:20} | Error: {str(e).splitlines()[0]}")

session.close()
