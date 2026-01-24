"""
Script to delete all rows from all tables in the database, preserving the schema.
Usage: python nuke_db.py
"""

from sqlalchemy import text
from sqlalchemy.engine import reflection
from backend.config import DATABASE_URL
from sqlalchemy import create_engine

engine = create_engine(DATABASE_URL)

def nuke_all_tables():
	with engine.connect() as conn:
		trans = conn.begin()
		try:
			inspector = reflection.Inspector.from_engine(conn)
			tables = inspector.get_table_names()
			# Disable referential integrity
			conn.execute(text('SET session_replication_role = replica;'))
			for table in tables:
				if table == 'alembic_version':
					continue  # Preserve Alembic migration history
				conn.execute(text(f'TRUNCATE TABLE "{table}" RESTART IDENTITY CASCADE;'))
			# Re-enable referential integrity
			conn.execute(text('SET session_replication_role = DEFAULT;'))
			trans.commit()
			print("All tables truncated. Database nuked.")
		except Exception as e:
			trans.rollback()
			print(f"Error: {e}")

if __name__ == "__main__":
	nuke_all_tables()
