"""Image search by description over phone images, made on this server (05 section 17.6).

- ``phone_image_vectors``: one image-text embedding per distinct image content in a case (SHA-256 of the bytes),
  per model weights, so a duplicate on several phones or in several files is embedded once. The vector is stored
  as bytes (little-endian float32, ``dim`` values, unit length); it records the model id with its pinned revision
  and the SHA-256 of the weights that made it. Case-scoped, so deleting a case deletes its vectors.
- ``phone_image_index_jobs``: a person's "Index this case's images for search", with the true counts it was
  started with and what it left out, by reason.
- ``phone_image_index_items``: one row per file the job indexes: its state, the content hash read, the weights
  that embedded it, and, when it could not be indexed, the reason in a code and in words. A finished row is the
  link from (case, file) to its content hash and vector.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261103_phone_image_search"
down_revision = "20261103_phone_translations"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "phone_image_vectors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content_sha256", sa.CHAR(64), nullable=False),
        sa.Column("model_id", sa.Text(), nullable=False),
        sa.Column("weights_sha256", sa.CHAR(64), nullable=False),
        sa.Column("dim", sa.Integer(), nullable=False),
        sa.Column("vector", sa.LargeBinary(), nullable=False),
        sa.Column("parameters", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("octet_length(vector) = 4 * dim", name="ck_phone_image_vectors_length"),
        sa.UniqueConstraint("case_id", "content_sha256", "weights_sha256", name="uq_phone_image_vectors_content"),
    )
    op.create_table(
        "phone_image_index_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("left_out", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("model_id", sa.Text(), nullable=False),
        sa.Column("weights_sha256", sa.CHAR(64), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_phone_image_index_jobs_case", "phone_image_index_jobs", ["case_id", "created_at"])
    op.create_table(
        "phone_image_index_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("phone_image_index_jobs.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("extraction_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("file_uid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("state", sa.Text(), nullable=False, server_default="queued"),
        sa.Column("outcome", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("content_sha256", sa.CHAR(64), nullable=True),
        sa.Column("weights_sha256", sa.CHAR(64), nullable=True),
        sa.Column("sniffed_container", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("solo", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("state IN ('queued', 'running', 'done', 'failed')", name="ck_phone_image_index_items_state"),
        sa.CheckConstraint("outcome IS NULL OR outcome IN ('embedded', 'reused')",
                           name="ck_phone_image_index_items_outcome"),
        sa.CheckConstraint("state <> 'done' OR (outcome IS NOT NULL AND content_sha256 IS NOT NULL AND "
                           "weights_sha256 IS NOT NULL)", name="ck_phone_image_index_items_done"),
        sa.CheckConstraint("state <> 'failed' OR (reason IS NOT NULL AND error IS NOT NULL)",
                           name="ck_phone_image_index_items_failed"),
    )
    op.create_index("ix_phone_image_index_items_job", "phone_image_index_items", ["job_id", "state"])
    op.create_index("ix_phone_image_index_items_file", "phone_image_index_items", ["case_id", "file_uid"])
    op.create_index("ix_phone_image_index_items_content", "phone_image_index_items",
                    ["case_id", "content_sha256", "weights_sha256"], postgresql_where=sa.text("state = 'done'"))
    op.create_index("ix_phone_image_index_items_queued", "phone_image_index_items", ["created_at"],
                    postgresql_where=sa.text("state IN ('queued', 'running')"))
    # one open indexing per file: a second job at the same moment inserts nothing for a file already waiting
    op.execute("CREATE UNIQUE INDEX uq_phone_image_index_items_open ON phone_image_index_items (case_id, file_uid) "
               "WHERE state IN ('queued', 'running')")


def downgrade():
    op.execute("DROP INDEX IF EXISTS uq_phone_image_index_items_open")
    op.drop_table("phone_image_index_items")
    op.drop_table("phone_image_index_jobs")
    op.drop_table("phone_image_vectors")
