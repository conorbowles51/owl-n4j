"""Deleted items: kept copies for deleted evidence folders, entry links, pins, deadlines and chats (lx-deletebin B).

Revision ID: 20261108_deleted_items_kinds
Revises: 20261108_case_selections
"""
from alembic import op

revision = "20261108_deleted_items_kinds"
down_revision = "20261108_case_selections"
branch_labels = None
depends_on = None

OLD = ('dossier_assessment', 'dossier_interview', 'dossier_media', 'dossier_link', 'dossier_evidence_link',
       'snapshot')
NEW = OLD + ('evidence_folder', 'entry_link', 'evidence_pin', 'case_deadline', 'chat')


def _check(kinds):
    return "kind IN ('" + "', '".join(kinds) + "')"


def upgrade():
    op.drop_constraint("ck_removed_records_kind", "removed_records", type_="check")
    op.create_check_constraint("ck_removed_records_kind", "removed_records", _check(NEW))


def downgrade():
    op.drop_constraint("ck_removed_records_kind", "removed_records", type_="check")
    op.create_check_constraint("ck_removed_records_kind", "removed_records", _check(OLD))
