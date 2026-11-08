"""What each evidence file claims to be, what its bytes show, its hold from model reading and its malware scan.

Nullable columns with no default, so the table is not rewritten and a running upload is not held. A row stays null
until its file is read (``services/evidence_signature.py``).
"""
import sqlalchemy as sa
from alembic import op

revision = "20261106_evidence_file_check"
down_revision = "20261105_job_cancel"
branch_labels = None
depends_on = None

COLUMNS = (("file_type_stated", sa.String(32)), ("file_type_detected", sa.String(32)), ("file_type_match", sa.String(16)),
           ("reading_hold", sa.String(16)), ("reading_hold_reason", sa.String(32)), ("reading_hold_detail", sa.Text()),
           ("reading_released_by", sa.String(255)), ("reading_released_at", sa.DateTime(timezone=True)),
           ("malware_scan", sa.String(16)), ("malware_scan_at", sa.DateTime(timezone=True)))


def upgrade():
    for name, kind in COLUMNS:
        op.add_column("evidence_files", sa.Column(name, kind, nullable=True))
    op.create_index("ix_evidence_files_malware_waiting", "evidence_files", ["id"],
                    postgresql_where=sa.text("malware_scan = 'waiting'"))


def downgrade():
    op.drop_index("ix_evidence_files_malware_waiting", table_name="evidence_files")
    for name, _kind in reversed(COLUMNS):
        op.drop_column("evidence_files", name)
