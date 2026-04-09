"""Add scope, categories, planning and comments tables

Revision ID: 003_scope_categories_planning
Revises: 002_analytics_fields
Create Date: 2026-04-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '003_scope_categories_planning'
down_revision: Union[str, None] = '002_analytics_fields'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Comments table
    op.create_table(
        'comments',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('jira_comment_id', sa.String(64), unique=True, nullable=False, index=True),
        sa.Column('body', sa.Text(), nullable=True),
        sa.Column('jira_created_at', sa.DateTime(), nullable=True),
        sa.Column('issue_id', sa.String(36), sa.ForeignKey('issues.id'), nullable=False, index=True),
        sa.Column('author_id', sa.String(36), sa.ForeignKey('employees.id'), nullable=True, index=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('synced_at', sa.DateTime(), nullable=True),
    )

    # Scope: allowed Jira projects
    op.create_table(
        'scope_projects',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('jira_project_key', sa.String(16), unique=True, nullable=False, index=True),
        sa.Column('jira_project_id', sa.String(64), nullable=True),
        sa.Column('is_enabled', sa.Boolean(), default=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )

    # Scope: root epics/tasks for category auto-assignment
    op.create_table(
        'scope_roots',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('category_code', sa.String(100), nullable=False, index=True),
        sa.Column('jira_issue_key', sa.String(32), nullable=False, index=True),
        sa.Column('jira_issue_id', sa.String(64), nullable=True),
        sa.Column('project_key', sa.String(16), nullable=True),
        sa.Column('is_enabled', sa.Boolean(), default=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )

    # Category mappings
    op.create_table(
        'category_mappings',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('entity_type', sa.String(50), nullable=False, index=True),
        sa.Column('entity_id', sa.String(36), nullable=False, index=True),
        sa.Column('category', sa.String(100), nullable=False, index=True),
        sa.Column('subcategory', sa.String(100), nullable=True),
        sa.Column('source_rule', sa.String(100), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )

    # Category overrides
    op.create_table(
        'category_overrides',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('jira_issue_key', sa.String(32), unique=True, nullable=False, index=True),
        sa.Column('category_code', sa.String(100), nullable=False),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )

    # Worklog quality rules
    op.create_table(
        'worklog_quality_rules',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('rule_code', sa.String(100), unique=True, nullable=False, index=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('threshold_value', sa.Float(), nullable=True),
        sa.Column('is_enabled', sa.Boolean(), default=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )

    # Vacations
    op.create_table(
        'vacations',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('employee_id', sa.String(36), sa.ForeignKey('employees.id'), nullable=False, index=True),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=False),
        sa.Column('hours_total', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )

    # Monthly capacity rules
    op.create_table(
        'monthly_capacity_rules',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('month', sa.Integer(), nullable=False),
        sa.Column('year', sa.Integer(), nullable=False),
        sa.Column('percent_of_norm', sa.Float(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )

    # Backlog items
    op.create_table(
        'backlog_items',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('project_id', sa.String(36), sa.ForeignKey('projects.id'), nullable=True, index=True),
        sa.Column('quarter', sa.String(10), nullable=True),
        sa.Column('estimate_hours', sa.Float(), nullable=True),
        sa.Column('priority', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )

    # Planning scenarios
    op.create_table(
        'planning_scenarios',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('quarter', sa.String(10), nullable=True),
        sa.Column('year', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )

    # Scenario allocations
    op.create_table(
        'scenario_allocations',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('scenario_id', sa.String(36), sa.ForeignKey('planning_scenarios.id'), nullable=False, index=True),
        sa.Column('backlog_item_id', sa.String(36), sa.ForeignKey('backlog_items.id'), nullable=False, index=True),
        sa.Column('planned_hours', sa.Float(), nullable=True),
        sa.Column('included_flag', sa.Boolean(), default=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('scenario_allocations')
    op.drop_table('planning_scenarios')
    op.drop_table('backlog_items')
    op.drop_table('monthly_capacity_rules')
    op.drop_table('vacations')
    op.drop_table('worklog_quality_rules')
    op.drop_table('category_overrides')
    op.drop_table('category_mappings')
    op.drop_table('scope_roots')
    op.drop_table('scope_projects')
    op.drop_table('comments')
