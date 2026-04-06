from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, abort, Response
from flask_login import login_required, current_user
from datetime import datetime
import markdown
import bleach
from app import db
from app.models import Post, Comment, User, Notification

from app.utils import (unique_slug, save_image, allowed_image,
                        create_notification, send_publication_email)

blog_bp = Blueprint('blog', __name__)

ALLOWED_TAGS = ['p', 'br', 'strong', 'em', 'ul', 'ol', 'li', 'h1', 'h2', 'h3',
                'h4', 'blockquote', 'code', 'pre', 'a', 'img', 'hr', 'table',
                'thead', 'tbody', 'tr', 'th', 'td']
ALLOWED_ATTRS = {'a': ['href', 'title'], 'img': ['src', 'alt', 'title']}


@blog_bp.route('/')
def index():
    page = request.args.get('page', 1, type=int)
    q = request.args.get('q', '')
    query = Post.query.filter_by(status='published')
    if q:
        query = query.filter(Post.title.ilike(f'%{q}%') | Post.content.ilike(f'%{q}%'))
    posts = query.order_by(Post.created_at.desc()).paginate(page=page, per_page=10)
    popular = Post.query.filter_by(status='published').order_by(Post.views.desc()).limit(5).all()
    return render_template('blog/index.html', posts=posts, popular=popular, q=q)


@blog_bp.route('/robots.txt')
def robots_txt():
    body = (
        'User-agent: *\n'
        'Allow: /\n'
        'Disallow: /admin/\n'
        'Disallow: /auth/\n'
        f'Sitemap: {url_for("blog.sitemap_xml", _external=True)}\n'
    )
    return Response(body, mimetype='text/plain')


@blog_bp.route('/sitemap.xml')
def sitemap_xml():
    posts = Post.query.filter_by(status='published').order_by(Post.updated_at.desc()).all()
    urls = [
        {
            'loc': url_for('blog.index', _external=True),
            'lastmod': datetime.utcnow().date().isoformat(),
            'changefreq': 'daily',
            'priority': '1.0',
        }
    ]
    for post in posts:
        lastmod = (post.updated_at or post.published_at or post.created_at or datetime.utcnow()).date().isoformat()
        urls.append({
            'loc': url_for('blog.view_post', slug=post.slug, _external=True),
            'lastmod': lastmod,
            'changefreq': 'weekly',
            'priority': '0.8',
        })

    xml = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for entry in urls:
        xml.append('<url>')
        xml.append(f"<loc>{entry['loc']}</loc>")
        xml.append(f"<lastmod>{entry['lastmod']}</lastmod>")
        xml.append(f"<changefreq>{entry['changefreq']}</changefreq>")
        xml.append(f"<priority>{entry['priority']}</priority>")
        xml.append('</url>')
    xml.append('</urlset>')
    return Response('\n'.join(xml), mimetype='application/xml')


@blog_bp.route('/post/<slug>')
def view_post(slug):
    from flask import session as flask_session
    post = Post.query.filter_by(slug=slug).first_or_404()
    if post.status != 'published':
        if not current_user.is_authenticated:
            abort(404)
        if current_user.id != post.author_id and current_user.role != 'admin':
            abort(404)
    # Only count one view per session per post
    viewed_key = f'viewed_post_{post.id}'
    if not flask_session.get(viewed_key):
        post.views += 1
        db.session.commit()
        flask_session[viewed_key] = True

    # Render markdown
    rendered = bleach.clean(
        markdown.markdown(post.content, extensions=['extra', 'codehilite', 'nl2br']),
        tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS
    )
    comments = Comment.query.filter_by(post_id=post.id, parent_id=None, is_deleted=False).order_by(Comment.created_at.asc()).all()
    is_bookmarked = current_user.is_authenticated and current_user.has_bookmarked(post)
    is_liked = current_user.is_authenticated and current_user.has_liked(post)
    is_following_author = current_user.is_authenticated and current_user.is_following(post.author)
    return render_template('blog/view_post.html', post=post, rendered=rendered,
                           comments=comments, is_bookmarked=is_bookmarked,
                           is_liked=is_liked, is_following_author=is_following_author)


@blog_bp.route('/post/new', methods=['GET', 'POST'])
@login_required
def new_post():
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        content = request.form.get('content', '').strip()
        action = request.form.get('action', 'draft')

        if not title or not content:
            flash('Title and content are required.', 'danger')
            return render_template('blog/editor.html', post=None)

        post = Post(title=title, content=content, author_id=current_user.id)
        post.slug = unique_slug(title, Post)
        post.excerpt = content[:200].strip()

        if 'cover_image' in request.files:
            f = request.files['cover_image']
            if f and f.filename and allowed_image(f.filename):
                post.cover_image = save_image(f, 'posts')

        if action == 'publish':
            post.status = 'published'
            post.published_at = datetime.utcnow()
            db.session.add(post)
            db.session.commit()
            send_publication_email(current_user, post)
            flash('Post published!', 'success')
        else:
            post.status = 'draft'
            db.session.add(post)
            db.session.commit()
            flash('Saved as draft.', 'info')

        return redirect(url_for('blog.view_post', slug=post.slug))
    return render_template('blog/editor.html', post=None)


@blog_bp.route('/post/<int:post_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_post(post_id):
    post = Post.query.get_or_404(post_id)
    if post.author_id != current_user.id and current_user.role != 'admin':
        abort(403)

    if request.method == 'POST':
        post.title = request.form.get('title', '').strip()
        post.content = request.form.get('content', '').strip()
        action = request.form.get('action', 'draft')

        if not post.title or not post.content:
            flash('Title and content are required.', 'danger')
            return render_template('blog/editor.html', post=post)

        post.slug = unique_slug(post.title, Post, existing_id=post.id)
        post.excerpt = post.content[:200].strip()

        if 'cover_image' in request.files:
            f = request.files['cover_image']
            if f and f.filename and allowed_image(f.filename):
                post.cover_image = save_image(f, 'posts')

        if action == 'publish':
            was_draft = post.status != 'published'
            post.status = 'published'
            if not post.published_at:
                post.published_at = datetime.utcnow()
            db.session.commit()
            if was_draft:
                send_publication_email(current_user, post)
            flash('Post updated and published!', 'success')
        elif action == 'archive':
            post.status = 'archived'
            db.session.commit()
            flash('Post archived.', 'info')
        else:
            post.status = 'draft'
            db.session.commit()
            flash('Draft saved.', 'info')

        return redirect(url_for('blog.view_post', slug=post.slug))
    return render_template('blog/editor.html', post=post)


@blog_bp.route('/post/<int:post_id>/delete', methods=['POST'])
@login_required
def delete_post(post_id):
    post = Post.query.get_or_404(post_id)
    if post.author_id != current_user.id and current_user.role != 'admin':
        abort(403)
    db.session.delete(post)
    db.session.commit()
    flash('Post deleted.', 'info')
    return redirect(url_for('user.dashboard'))


@blog_bp.route('/post/<int:post_id>/archive', methods=['POST'])
@login_required
def archive_post(post_id):
    post = Post.query.get_or_404(post_id)
    if post.author_id != current_user.id and current_user.role != 'admin':
        abort(403)
    post.status = 'archived'
    db.session.commit()
    flash('Post archived.', 'info')
    return redirect(url_for('user.dashboard'))


@blog_bp.route('/post/<int:post_id>/publish', methods=['POST'])
@login_required
def publish_post(post_id):
    post = Post.query.get_or_404(post_id)
    if post.author_id != current_user.id and current_user.role != 'admin':
        abort(403)
    post.status = 'published'
    if not post.published_at:
        post.published_at = datetime.utcnow()
    db.session.commit()
    send_publication_email(current_user, post)
    flash('Post published!', 'success')
    return redirect(url_for('blog.view_post', slug=post.slug))


@blog_bp.route('/post/<int:post_id>/like', methods=['POST'])
@login_required
def like_post(post_id):
    post = Post.query.get_or_404(post_id)
    if current_user.has_liked(post):
        current_user.unlike_post(post)
        db.session.commit()
        return jsonify({'liked': False, 'count': post.like_count})
    else:
        current_user.like_post(post)
        db.session.commit()
        if post.author_id != current_user.id:
            actor = User.query.get(current_user.id)
            uname = actor.username
            create_notification(post.author_id, 'like',
                                f'<a href="/user/{uname}" class="notif-link">@{uname}</a> liked your post "<a href="/post/{post.slug}" class="notif-link">{post.title}</a>".',
                                url_for('blog.view_post', slug=post.slug))
        return jsonify({'liked': True, 'count': post.like_count})


@blog_bp.route('/post/<int:post_id>/bookmark', methods=['POST'])
@login_required
def bookmark_post(post_id):
    post = Post.query.get_or_404(post_id)
    if current_user.has_bookmarked(post):
        current_user.unbookmark_post(post)
        db.session.commit()
        return jsonify({'bookmarked': False})
    else:
        current_user.bookmark_post(post)
        db.session.commit()
        return jsonify({'bookmarked': True})


@blog_bp.route('/post/<int:post_id>/toggle-comments', methods=['POST'])
@login_required
def toggle_comments(post_id):
    post = Post.query.get_or_404(post_id)
    if post.author_id != current_user.id and current_user.role != 'admin':
        abort(403)
    post.comments_disabled = not post.comments_disabled
    db.session.commit()
    # AJAX request → JSON
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'disabled': post.comments_disabled})
    # Normal form POST → redirect back to post
    status = 'disabled' if post.comments_disabled else 'enabled'
    flash(f'Comments {status} on this post.', 'info')
    return redirect(url_for('blog.view_post', slug=post.slug))


@blog_bp.route('/post/<int:post_id>/comment', methods=['POST'])
@login_required
def add_comment(post_id):
    post = Post.query.get_or_404(post_id)
    if post.comments_disabled:
        flash('Comments are disabled on this post.', 'warning')
        return redirect(url_for('blog.view_post', slug=post.slug))

    content = request.form.get('content', '').strip()
    parent_id = request.form.get('parent_id', type=int)
    if not content:
        flash('Comment cannot be empty.', 'danger')
        return redirect(url_for('blog.view_post', slug=post.slug))

    comment = Comment(content=content, author_id=current_user.id,
                      post_id=post_id, parent_id=parent_id)
    db.session.add(comment)
    db.session.commit()

    if parent_id:
        parent = Comment.query.get(parent_id)
        if parent and parent.author_id != current_user.id:
            actor = User.query.get(current_user.id)
            uname = actor.username
            create_notification(parent.author_id, 'reply',
                                f'<a href="/user/{uname}" class="notif-link">@{uname}</a> replied to your comment.',
                                url_for('blog.view_post', slug=post.slug))
    elif post.author_id != current_user.id:
        actor = User.query.get(current_user.id)
        uname = actor.username
        create_notification(post.author_id, 'comment',
                            f'<a href="/user/{uname}" class="notif-link">@{uname}</a> commented on "<a href="/post/{post.slug}" class="notif-link">{post.title}</a>".',
                            url_for('blog.view_post', slug=post.slug))

    flash('Comment added!', 'success')
    return redirect(url_for('blog.view_post', slug=post.slug) + f'#comment-{comment.id}')


@blog_bp.route('/comment/<int:comment_id>/edit', methods=['POST'])
@login_required
def edit_comment(comment_id):
    comment = Comment.query.get_or_404(comment_id)
    if comment.author_id != current_user.id:
        abort(403)
    content = request.form.get('content', '').strip()
    if content:
        comment.content = content
        db.session.commit()
    return redirect(url_for('blog.view_post', slug=comment.post.slug) + f'#comment-{comment.id}')


@blog_bp.route('/comment/<int:comment_id>/delete', methods=['POST'])
@login_required
def delete_comment(comment_id):
    comment = Comment.query.get_or_404(comment_id)
    if comment.author_id != current_user.id and current_user.role != 'admin':
        abort(403)
    comment.is_deleted = True
    comment.content = '[deleted]'
    db.session.commit()
    return redirect(url_for('blog.view_post', slug=comment.post.slug))


@blog_bp.route('/post/preview', methods=['POST'])
@login_required
def preview_post():
    title = request.form.get('title', '')
    content = request.form.get('content', '')
    rendered = bleach.clean(
        markdown.markdown(content, extensions=['extra', 'codehilite', 'nl2br']),
        tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS
    )
    return render_template('blog/preview.html', title=title, rendered=rendered)


@blog_bp.route('/upload-image', methods=['POST'])
@login_required
def upload_image():
    if 'image' not in request.files:
        return jsonify({'error': 'No file'}), 400
    f = request.files['image']
    if not f or not allowed_image(f.filename):
        return jsonify({'error': 'Invalid file'}), 400
    filename = save_image(f, 'posts')
    from flask import current_app
    url = f'/static/uploads/posts/{filename}'
    return jsonify({'url': url})
