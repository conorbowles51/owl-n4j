"""Machine text names exactly what made it (05 section 17.4 points 2 and 4, unit 05-S12).

Every transcript and every text read from an image records the model id, the weights hash (or, for Tesseract, the
hash of its language data), the parameters it ran with, the SHA-256 of the input bytes, the provider (``local``:
made on this server), the file's kind as sniffed from its bytes, and the audio duration where there is one.
Rows written before this revision keep NULL in the new columns: what made them was not recorded, and nothing here
invents it.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261103_phone_derived_identity"
down_revision = "20261103_phone_analysis"
branch_labels = None
depends_on = None

COLUMNS = (
    ("model_id", sa.Text()),
    ("weights_sha256", sa.Text()),
    ("input_sha256", sa.Text()),
    ("provider", sa.Text()),
    ("sniffed_container", sa.Text()),
    ("language", sa.Text()),
    ("duration_seconds", sa.Float()),
)


def upgrade():
    for name, type_ in COLUMNS:
        op.add_column("phone_derived_texts", sa.Column(name, type_, nullable=True))
    op.add_column("phone_derived_texts", sa.Column("parameters", postgresql.JSONB(), nullable=True))


def downgrade():
    op.drop_column("phone_derived_texts", "parameters")
    for name, _ in reversed(COLUMNS):
        op.drop_column("phone_derived_texts", name)
