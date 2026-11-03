"""Where each file sits inside an uploaded archive (cb-media item F; 01 D6, containers are read in place).

A phone file kept inside an uploaded ZIP or UFDR has no path of its own on disk. Each container entry now records
the archive it was listed from (``container_id``) and, for an archive, the member's local header offset,
compressed size, compression method and CRC-32, so the file is served by seeking straight to it instead of reading
the archive's whole directory (measured on live C9.zip: 58,215 entries, 310-480 ms per directory read). Rows of a
folder upload keep NULL offsets. Rows written before this revision are filled by the capture's own function
(``app.phone.files.record_member_offsets``), run once for each existing archive.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261103_phone_entry_offsets"
down_revision = "20261103_phone_derived_identity"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("phone_container_entries", sa.Column("container_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("phone_container_entries", sa.Column("header_offset", sa.BigInteger(), nullable=True))
    op.add_column("phone_container_entries", sa.Column("compressed_size", sa.BigInteger(), nullable=True))
    op.add_column("phone_container_entries", sa.Column("compress_type", sa.SmallInteger(), nullable=True))
    op.add_column("phone_container_entries", sa.Column("crc32", sa.BigInteger(), nullable=True))


def downgrade():
    for name in ("crc32", "compress_type", "compressed_size", "header_offset", "container_id"):
        op.drop_column("phone_container_entries", name)
