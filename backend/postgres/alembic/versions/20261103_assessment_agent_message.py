"""A dossier assessment accepted from an agent answer names that answer (07 section 6.3, CO-18 agent).

``dossier_assessments.agent_message_id`` points at the agent message whose text a person accepted. With it the
assessment shows "Read by <model>, accepted by <name>"; the answer keeps its own mark as a model reading. Existing
rows are unchanged (the column is nullable and starts empty).
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261103_assessment_agent_message"
down_revision = "20261103_phone_image_search"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("dossier_assessments", sa.Column("agent_message_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_dossier_assessments_agent_message", "dossier_assessments", "agent_messages",
                          ["agent_message_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_dossier_assessments_agent_message_id", "dossier_assessments", ["agent_message_id"])


def downgrade():
    op.drop_index("ix_dossier_assessments_agent_message_id", table_name="dossier_assessments")
    op.drop_constraint("fk_dossier_assessments_agent_message", "dossier_assessments", type_="foreignkey")
    op.drop_column("dossier_assessments", "agent_message_id")
