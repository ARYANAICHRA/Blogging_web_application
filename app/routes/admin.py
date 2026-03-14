from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from functools import wraps
from datetime import datetime
from app import db
from app.models import User, Post, Comment, Notification, Announcement
from app.utils import send_announcement_email, create_notification

admin_bp = Blueprint('admin', __name__)


def admin_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if current_user.role != 'admin':
            flash('Admin access required.', 'danger')
            return redirect(url_for('blog.index'))
        return f(*args, **kwargs)
    return decorated


@admin_bp.route('/dashboard')
@admin_required
def dashboard():
    total_users = User.query.filter_by(role='user').count()
    total_posts = Post.query.count()
    published_posts = Post.query.filter_by(status='published').count()
    draft_posts = Post.query.filter_by(status='draft').count()
    archived_posts = Post.query.filter_by(status='archived').count()
    total_comments = Comment.query.filter_by(is_deleted=False).count()
    recent_users = User.query.filter_by(role='user').order_by(User.created_at.desc()).limit(5).all()
    recent_posts = Post.query.order_by(Post.created_at.desc()).limit(5).all()
    popular_posts = Post.query.filter_by(status='published').order_by(Post.views.desc()).limit(5).all()
    active_users = db.session.query(User, db.func.count(Post.id).label('pcount')).join(Post).group_by(User.id).order_by(db.text('pcount DESC')).limit(5).all()
    most_liked = Post.query.filter_by(status='published').all()
    most_liked.sort(key=lambda p: p.like_count, reverse=True)
    most_liked = most_liked[:5]
    return render_template('admin/dashboard.html',
                           total_users=total_users, total_posts=total_posts,
                           published_posts=published_posts, draft_posts=draft_posts,
                           archived_posts=archived_posts, total_comments=total_comments,
                           recent_users=recent_users, recent_posts=recent_posts,
                           popular_posts=popular_posts, active_users=active_users,
                           most_liked=most_liked)


@admin_bp.route('/users')
@admin_required
def users():
    q = request.args.get('q', '')
    page = request.args.get('page', 1, type=int)
    query = User.query.filter_by(role='user')
    if q:
        query = query.filter(User.username.ilike(f'%{q}%') | User.email.ilike(f'%{q}%'))
    users = query.order_by(User.created_at.desc()).paginate(page=page, per_page=20)
    return render_template('admin/users.html', users=users, q=q)


@admin_bp.route('/users/<int:user_id>')
@admin_required
def view_user(user_id):
    user = User.query.get_or_404(user_id)
    posts = Post.query.filter_by(author_id=user_id).order_by(Post.created_at.desc()).all()
    return render_template('admin/view_user.html', user=user, posts=posts)


@admin_bp.route('/users/<int:user_id>/block', methods=['POST'])
@admin_required
def block_user(user_id):
    user = User.query.get_or_404(user_id)
    user.is_blocked = not user.is_blocked
    db.session.commit()
    status = 'blocked' if user.is_blocked else 'unblocked'
    flash(f'User {user.username} has been {status}.', 'success')
    return redirect(request.referrer or url_for('admin.users'))


@admin_bp.route('/users/<int:user_id>/delete', methods=['POST'])
@admin_required
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    db.session.delete(user)
    db.session.commit()
    flash('User deleted.', 'info')
    return redirect(url_for('admin.users'))


@admin_bp.route('/users/<int:user_id>/reset-password', methods=['POST'])
@admin_required
def reset_user_password(user_id):
    user = User.query.get_or_404(user_id)
    new_password = request.form.get('password', '')
    if len(new_password) < 8:
        flash('Password must be at least 8 characters.', 'danger')
        return redirect(url_for('admin.view_user', user_id=user_id))
    user.set_password(new_password)
    db.session.commit()
    flash(f'Password reset for {user.username}.', 'success')
    return redirect(url_for('admin.view_user', user_id=user_id))


@admin_bp.route('/posts')
@admin_required
def posts():
    q = request.args.get('q', '')
    status_filter = request.args.get('status', '')
    page = request.args.get('page', 1, type=int)
    query = Post.query
    if q:
        query = query.filter(Post.title.ilike(f'%{q}%'))
    if status_filter:
        query = query.filter_by(status=status_filter)
    posts = query.order_by(Post.created_at.desc()).paginate(page=page, per_page=20)
    return render_template('admin/posts.html', posts=posts, q=q, status_filter=status_filter)


@admin_bp.route('/posts/<int:post_id>/delete', methods=['POST'])
@admin_required
def delete_post(post_id):
    post = Post.query.get_or_404(post_id)
    db.session.delete(post)
    db.session.commit()
    flash('Post deleted.', 'info')
    return redirect(url_for('admin.posts'))


@admin_bp.route('/posts/<int:post_id>/archive', methods=['POST'])
@admin_required
def archive_post(post_id):
    post = Post.query.get_or_404(post_id)
    post.status = 'archived'
    db.session.commit()
    flash('Post archived.', 'info')
    return redirect(url_for('admin.posts'))


@admin_bp.route('/posts/<int:post_id>/toggle-comments', methods=['POST'])
@admin_required
def toggle_comments(post_id):
    post = Post.query.get_or_404(post_id)
    post.comments_disabled = not post.comments_disabled
    db.session.commit()
    flash('Comments setting updated.', 'info')
    return redirect(url_for('admin.posts'))


@admin_bp.route('/comments')
@admin_required
def comments():
    page = request.args.get('page', 1, type=int)
    comments = Comment.query.filter_by(is_deleted=False).order_by(Comment.created_at.desc()).paginate(page=page, per_page=30)
    return render_template('admin/comments.html', comments=comments)


@admin_bp.route('/comments/<int:comment_id>/delete', methods=['POST'])
@admin_required
def delete_comment(comment_id):
    comment = Comment.query.get_or_404(comment_id)
    comment.is_deleted = True
    comment.content = '[Removed by admin]'
    db.session.commit()
    flash('Comment removed.', 'info')
    return redirect(request.referrer or url_for('admin.comments'))


@admin_bp.route('/announcement', methods=['GET', 'POST'])
@admin_required
def announcement():
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        content = request.form.get('content', '').strip()
        send_email = request.form.get('send_email') == 'on'

        if not title or not content:
            flash('Title and content are required.', 'danger')
            return render_template('admin/announcement.html')

        ann = Announcement(title=title, content=content, sent_by=current_user.id)
        db.session.add(ann)

        users = User.query.filter_by(role='user', is_active=True, is_blocked=False).all()
        for user in users:
            create_notification(user.id, 'announcement',
                                f'{title}||{content}', '#')

        if send_email:
            send_announcement_email(users, title, content)

        db.session.commit()
        flash(f'Announcement sent to {len(users)} users!', 'success')
        return redirect(url_for('admin.dashboard'))
    return render_template('admin/announcement.html')
