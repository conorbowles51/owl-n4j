"""Join preserved audio review with the current application migration chain.

Keep both existing revision histories intact for installations that already
applied the audio tables locally and those upgrading from the shared release.
"""

revision = '20261103_merge_audio_review'
down_revision = ('20261103_phone_result_snapshots', '20261026_audio_integrity')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
