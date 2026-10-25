"""students, courses, attempts

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "students",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "courses",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    # One row per question answered; mastery (week 2) is computed from these.
    op.create_table(
        "attempts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("student_id", sa.Integer, sa.ForeignKey("students.id"), nullable=False),
        sa.Column("course_id", sa.String(64), sa.ForeignKey("courses.id"), nullable=False),
        sa.Column("topic", sa.String(255), nullable=False),
        sa.Column("correct", sa.Boolean, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_attempts_student_topic", "attempts", ["student_id", "course_id", "topic"])


def downgrade() -> None:
    op.drop_table("attempts")
    op.drop_table("courses")
    op.drop_table("students")
