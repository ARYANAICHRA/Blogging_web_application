"""initial migration

Revision ID: f332526ae0b2
Revises: 
Create Date: 2026-04-06 14:29:15.764083

"""
from alembic import op
import sqlalchemy as sa

revision = 'f332526ae0b2'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('user',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('username', sa.String(80), nullable=False),
        sa.Column('email', sa.String(120), nullable=False),
        sa.Column('password_hash', sa.String(256), nullable=False),
        sa.Column('role', sa.String(20), nullable=True),
        sa.Column('is_verified', sa.Boolean(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('is_blocked', sa.Boolean(), nullable=True),
        sa.Column('avatar', sa.String(200), nullable=True),
        sa.Column('bio', sa.Text(), nullable=True),
        sa.Column('two_factor_enabled', sa.Boolean(), nullable=True),
        sa.Column('two_factor_secret', sa.String(32), nullable=True),
        sa.Column('otp_code', sa.String(6), nullable=True),
        sa.Column('otp_expires', sa.DateTime(), nullable=True),
        sa.Column('full_name', sa.String(120), nullable=True),
        sa.Column('upi_id', sa.String(100), nullable=True),
        sa.Column('upi_qr', sa.String(200), nullable=True),
        sa.Column('upi_reward_received', sa.Boolean(), nullable=True),
        sa.Column('upi_reward_date', sa.DateTime(), nullable=True),
        sa.Column('free_gift_enabled', sa.Boolean(), nullable=True),
        sa.Column('free_gift_activated_date', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('last_seen', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('username'),
        sa.UniqueConstraint('email'),
        sa.UniqueConstraint('upi_id')
    )

    op.create_table('post',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('slug', sa.String(250), nullable=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('excerpt', sa.Text(), nullable=True),
        sa.Column('cover_image', sa.String(200), nullable=True),
        sa.Column('status', sa.String(20), nullable=True),
        sa.Column('comments_disabled', sa.Boolean(), nullable=True),
        sa.Column('views', sa.Integer(), nullable=True),
        sa.Column('author_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('published_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['author_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('slug')
    )

    op.create_table('comment',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('author_id', sa.Integer(), nullable=True),
        sa.Column('post_id', sa.Integer(), nullable=True),
        sa.Column('parent_id', sa.Integer(), nullable=True),
        sa.Column('is_deleted', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['author_id'], ['user.id']),
        sa.ForeignKeyConstraint(['post_id'], ['post.id']),
        sa.ForeignKeyConstraint(['parent_id'], ['comment.id']),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('notification',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('type', sa.String(50), nullable=True),
        sa.Column('message', sa.Text(), nullable=True),
        sa.Column('link', sa.String(300), nullable=True),
        sa.Column('is_read', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('announcement',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(200), nullable=True),
        sa.Column('content', sa.Text(), nullable=True),
        sa.Column('sent_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['sent_by'], ['user.id']),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('universal_otp',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('otp_hash', sa.String(256), nullable=False),
        sa.Column('is_enabled', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('ai_connector',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('connector_type', sa.String(50), nullable=False),
        sa.Column('api_key', sa.String(500), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('is_verified', sa.Boolean(), nullable=True),
        sa.Column('auto_post_enabled', sa.Boolean(), nullable=True),
        sa.Column('config', sa.JSON(), nullable=True),
        sa.Column('last_used', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('follows',
        sa.Column('follower_id', sa.Integer(), nullable=True),
        sa.Column('followed_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['follower_id'], ['user.id']),
        sa.ForeignKeyConstraint(['followed_id'], ['user.id'])
    )

    op.create_table('bookmarks',
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('post_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.ForeignKeyConstraint(['post_id'], ['post.id'])
    )

    op.create_table('likes',
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('post_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.ForeignKeyConstraint(['post_id'], ['post.id'])
    )


def downgrade():
    op.drop_table('likes')
    op.drop_table('bookmarks')
    op.drop_table('follows')
    op.drop_table('ai_connector')
    op.drop_table('universal_otp')
    op.drop_table('announcement')
    op.drop_table('notification')
    op.drop_table('comment')
    op.drop_table('post')
    op.drop_table('user')