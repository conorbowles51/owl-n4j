"""Work a model did for a person keeps its own origin on decisions (adjudications.actor_origin): additive.

NULL for a person's or a rule's decision. Set to the model origin (services.financial.model_work) when a model
decided for the person whose account the work ran under, so the decision shows as the model's until confirmed.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261029_model_work_origin"
down_revision = "20261028_request_speed"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('adjudications', sa.Column('actor_origin', postgresql.JSONB(), nullable=True))


def downgrade():
    op.drop_column('adjudications', 'actor_origin')
