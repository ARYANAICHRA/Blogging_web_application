from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, session
from flask_login import login_required, current_user
from datetime import datetime
from app import db
from app.models import User, Post, Notification
from app.utils import (save_image, allowed_image, generate_2fa_secret,
                        get_2fa_qr, verify_2fa_token, create_notification)

user_bp = Blueprint('user', __name__)


@user_bp.route('/dashboard')
@login_required
def dashboard():
    posts = Post.query.filter_by(author_id=current_user.id).order_by(Post.created_at.desc()).all()
    published = [p for p in posts if p.status == 'published']
    drafts = [p for p in posts if p.status == 'draft']
    archived = [p for p in posts if p.status == 'archived']
    total_likes = sum(p.like_count for p in published)
    total_views = sum(p.views for p in published)
    notifications = current_user.notifications.order_by(Notification.created_at.desc()).limit(10).all()
    return render_template('user/dashboard.html',
                           posts=posts, published=published, drafts=drafts,
                           archived=archived, total_likes=total_likes,
                           total_views=total_views, notifications=notifications)


@user_bp.route('/profile/edit', methods=['GET', 'POST'])
@login_required
def edit_profile():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        bio = request.form.get('bio', '').strip()

        if username and username != current_user.username:
            if User.query.filter_by(username=username).first():
                flash('Username already taken.', 'danger')
                return render_template('user/edit_profile.html')
            current_user.username = username

        current_user.bio = bio

        if 'avatar' in request.files:
            f = request.files['avatar']
            if f and f.filename and allowed_image(f.filename):
                filename = save_image(f, folder='avatars', size=(300, 300))
                current_user.avatar = filename

        db.session.commit()
        flash('Profile updated!', 'success')
        return redirect(url_for('user.profile', username=current_user.username))
    return render_template('user/edit_profile.html')


@user_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        current_pw = request.form.get('current_password', '')
        new_pw = request.form.get('new_password', '')
        confirm = request.form.get('confirm_password', '')
        if not current_user.check_password(current_pw):
            flash('Current password is incorrect.', 'danger')
        elif new_pw != confirm:
            flash('New passwords do not match.', 'danger')
        elif len(new_pw) < 8:
            flash('Password must be at least 8 characters.', 'danger')
        else:
            current_user.set_password(new_pw)
            db.session.commit()
            flash('Password changed successfully!', 'success')
            return redirect(url_for('user.dashboard'))
    return render_template('user/change_password.html')


@user_bp.route('/setup-2fa', methods=['GET', 'POST'])
@login_required
def setup_2fa():
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'enable':
            token = request.form.get('token', '').strip()
            if not current_user.two_factor_secret:
                flash('Please generate a secret first.', 'danger')
                return redirect(url_for('user.setup_2fa'))
            if verify_2fa_token(current_user, token):
                current_user.two_factor_enabled = True
                db.session.commit()
                flash('Two-Factor Authentication enabled!', 'success')
                return redirect(url_for('user.dashboard'))
            flash('Invalid token. Please try again.', 'danger')
        elif action == 'disable':
            current_user.two_factor_enabled = False
            current_user.two_factor_secret = None
            db.session.commit()
            flash('Two-Factor Authentication disabled.', 'info')
            return redirect(url_for('user.dashboard'))
        elif action == 'generate':
            current_user.two_factor_secret = generate_2fa_secret()
            db.session.commit()

    qr_code = None
    if current_user.two_factor_secret:
        qr_code = get_2fa_qr(current_user)
    return render_template('user/setup_2fa.html', qr_code=qr_code)


@user_bp.route('/<username>')
def profile(username):
    user = User.query.filter_by(username=username).first_or_404()
    posts = Post.query.filter_by(author_id=user.id, status='published').order_by(Post.created_at.desc()).all()
    is_following = current_user.is_authenticated and current_user.is_following(user)
    return render_template('user/profile.html', user=user, posts=posts, is_following=is_following)


@user_bp.route('/follow/<int:user_id>', methods=['POST'])
@login_required
def follow(user_id):
    user = User.query.get_or_404(user_id)
    if user == current_user:
        return jsonify({'error': 'Cannot follow yourself'}), 400
    if current_user.is_following(user):
        current_user.unfollow(user)
        db.session.commit()
        return jsonify({'following': False, 'count': user.followers.count()})
    else:
        current_user.follow(user)
        db.session.commit()
        actor = User.query.get(current_user.id)
        uname = actor.username
        # If username looks like an email, use the part before @
        if '@' in uname:
            uname = uname.split('@')[0]
        create_notification(user.id, 'follow',
                            f'<a href="/user/{actor.username}" class="notif-link">@{uname}</a> started following you.',
                            '#')
        return jsonify({'following': True, 'count': user.followers.count()})


@user_bp.route('/notifications')
@login_required
def notifications():
    page = request.args.get('page', 1, type=int)
    notifs = current_user.notifications.order_by(Notification.created_at.desc()).paginate(page=page, per_page=10)
    return render_template('user/notifications.html', notifications=notifs)


@user_bp.route('/notifications/<int:notif_id>/read', methods=['POST'])
@login_required
def mark_one_read(notif_id):
    n = Notification.query.filter_by(id=notif_id, user_id=current_user.id).first_or_404()
    n.is_read = True
    db.session.commit()
    return jsonify({'success': True})


@user_bp.route('/notifications/mark-read', methods=['POST'])
@login_required
def mark_notifications_read():
    current_user.notifications.filter_by(is_read=False).update({'is_read': True})
    db.session.commit()
    # If AJAX request, return JSON; otherwise redirect back
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True})
    flash('All notifications marked as read.', 'success')
    return redirect(url_for('user.notifications'))


@user_bp.route('/bookmarks')
@login_required
def bookmarks():
    posts = current_user.bookmarked_posts.filter_by(status='published').order_by(Post.created_at.desc()).all()
    return render_template('user/bookmarks.html', posts=posts)


@user_bp.route('/following-feed')
@login_required
def following_feed():
    posts = current_user.get_feed_posts().all()
    return render_template('user/following_feed.html', posts=posts)


@user_bp.route('/enable-free-gift', methods=['POST'])
@login_required
def enable_free_gift():
    """Enable free premium access for user"""
    if current_user.free_gift_enabled:
        flash('You already have premium access enabled!', 'info')
        return redirect(url_for('user.dashboard'))
    
    current_user.free_gift_enabled = True
    current_user.free_gift_activated_date = datetime.utcnow()
    db.session.commit()
    
    flash('🎉 Premium access unlocked! You can now add AI connectors and enable automated blog posting.', 'success')
    return redirect(url_for('user.dashboard'))


@user_bp.route('/connectors')
@login_required
def manage_connectors():
    """Manage AI connectors"""
    if not current_user.free_gift_enabled:
        flash('You need to unlock premium access first!', 'warning')
        return redirect(url_for('user.dashboard'))
    
    connectors = current_user.ai_connectors.all()
    return render_template('user/connectors.html', connectors=connectors)


@user_bp.route('/connector/add', methods=['GET', 'POST'])
@login_required
def add_connector():
    """Add a new AI connector"""
    if not current_user.free_gift_enabled:
        flash('You need to unlock premium access first!', 'warning')
        return redirect(url_for('user.dashboard'))
    
    if request.method == 'POST':
        from app.models import AIConnector
        
        name = request.form.get('name', '').strip()
        connector_type = request.form.get('connector_type', '').strip()
        api_key = request.form.get('api_key', '').strip()
        auto_post = request.form.get('auto_post_enabled') == 'on'
        
        if not all([name, connector_type, api_key]):
            flash('All fields are required.', 'danger')
            return render_template('user/add_connector.html')
        
        # Check for duplicate connector name
        if AIConnector.query.filter_by(user_id=current_user.id, name=name).first():
            flash('You already have a connector with this name.', 'danger')
            return render_template('user/add_connector.html')
        
        connector = AIConnector(
            user_id=current_user.id,
            name=name,
            connector_type=connector_type,
            api_key=api_key,  # In production, encrypt this
            auto_post_enabled=auto_post,
            is_active=True
        )
        db.session.add(connector)
        db.session.commit()
        
        flash(f'Connector "{name}" added successfully!', 'success')
        return redirect(url_for('user.manage_connectors'))
    
    return render_template('user/add_connector.html')


@user_bp.route('/connector/<int:connector_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_connector(connector_id):
    """Edit an AI connector"""
    from app.models import AIConnector
    
    connector = AIConnector.query.get_or_404(connector_id)
    
    if connector.user_id != current_user.id:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('user.manage_connectors'))
    
    if request.method == 'POST':
        connector.name = request.form.get('name', '').strip() or connector.name
        api_key = request.form.get('api_key', '').strip()
        if api_key:
            connector.api_key = api_key
        connector.auto_post_enabled = request.form.get('auto_post_enabled') == 'on'
        connector.is_active = request.form.get('is_active') == 'on'
        
        db.session.commit()
        flash('Connector updated!', 'success')
        return redirect(url_for('user.manage_connectors'))
    
    return render_template('user/edit_connector.html', connector=connector)


@user_bp.route('/connector/<int:connector_id>/delete', methods=['POST'])
@login_required
def delete_connector(connector_id):
    """Delete an AI connector"""
    from app.models import AIConnector
    
    connector = AIConnector.query.get_or_404(connector_id)
    
    if connector.user_id != current_user.id:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('user.manage_connectors'))
    
    name = connector.name
    db.session.delete(connector)
    db.session.commit()
    
    flash(f'Connector "{name}" deleted.', 'success')
    return redirect(url_for('user.manage_connectors'))
