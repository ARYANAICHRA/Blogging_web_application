from datetime import datetime
from app import db, login_manager
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


follows = db.Table('follows',
    db.Column('follower_id', db.Integer, db.ForeignKey('user.id')),
    db.Column('followed_id', db.Integer, db.ForeignKey('user.id'))
)

bookmarks = db.Table('bookmarks',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id')),
    db.Column('post_id', db.Integer, db.ForeignKey('post.id'))
)

likes = db.Table('likes',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id')),
    db.Column('post_id', db.Integer, db.ForeignKey('post.id'))
)


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), default='user')
    is_verified = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    is_blocked = db.Column(db.Boolean, default=False)
    avatar = db.Column(db.String(200), default='default.png')
    bio = db.Column(db.Text, default='')
    two_factor_enabled = db.Column(db.Boolean, default=False)
    two_factor_secret = db.Column(db.String(32))
    otp_code = db.Column(db.String(6))
    otp_expires = db.Column(db.DateTime)
    full_name = db.Column(db.String(120))
    upi_id = db.Column(db.String(100), unique=True, nullable=True)
    upi_qr = db.Column(db.String(200), nullable=True)
    upi_reward_received = db.Column(db.Boolean, default=False)
    upi_reward_date = db.Column(db.DateTime)
    free_gift_enabled = db.Column(db.Boolean, default=False)
    free_gift_activated_date = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)

    posts = db.relationship('Post', backref='author', lazy='dynamic', cascade='all, delete-orphan')
    comments = db.relationship('Comment', backref='author', lazy='dynamic', cascade='all, delete-orphan')
    notifications = db.relationship('Notification', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    ai_connectors = db.relationship('AIConnector', backref='user', lazy='dynamic', cascade='all, delete-orphan')

    bookmarked_posts = db.relationship('Post', secondary=bookmarks, backref='bookmarked_by', lazy='dynamic')
    liked_posts = db.relationship('Post', secondary=likes, backref='liked_by', lazy='dynamic')

    followed = db.relationship('User', secondary=follows,
                               primaryjoin=(follows.c.follower_id == id),
                               secondaryjoin=(follows.c.followed_id == id),
                               backref=db.backref('followers', lazy='dynamic'), lazy='dynamic')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def follow(self, user):
        if not self.is_following(user):
            self.followed.append(user)

    def unfollow(self, user):
        if self.is_following(user):
            self.followed.remove(user)

    def is_following(self, user):
        return self.followed.filter(follows.c.followed_id == user.id).count() > 0

    def like_post(self, post):
        if not self.has_liked(post):
            self.liked_posts.append(post)

    def unlike_post(self, post):
        if self.has_liked(post):
            self.liked_posts.remove(post)

    def has_liked(self, post):
        return self.liked_posts.filter(likes.c.post_id == post.id).count() > 0

    def bookmark_post(self, post):
        if not self.has_bookmarked(post):
            self.bookmarked_posts.append(post)

    def unbookmark_post(self, post):
        if self.has_bookmarked(post):
            self.bookmarked_posts.remove(post)

    def has_bookmarked(self, post):
        return self.bookmarked_posts.filter(bookmarks.c.post_id == post.id).count() > 0

    def get_feed_posts(self):
        followed_ids = [u.id for u in self.followed.all()]
        followed_ids.append(self.id)
        return Post.query.filter(
            Post.author_id.in_(followed_ids),
            Post.status == 'published'
        ).order_by(Post.created_at.desc())

    def unread_notification_count(self):
        return self.notifications.filter_by(is_read=False).count()

    def __repr__(self):
        return f'<User {self.username}>'


class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(250), unique=True)
    content = db.Column(db.Text, nullable=False)
    excerpt = db.Column(db.Text)
    cover_image = db.Column(db.String(200))
    status = db.Column(db.String(20), default='draft')  # draft / published / archived
    comments_disabled = db.Column(db.Boolean, default=False)
    views = db.Column(db.Integer, default=0)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    published_at = db.Column(db.DateTime)

    comments = db.relationship('Comment', backref='post', lazy='dynamic',
                                cascade='all, delete-orphan',
                                order_by='Comment.created_at.asc()')

    @property
    def like_count(self):
        return len(self.liked_by)

    @property
    def comment_count(self):
        return self.comments.filter_by(parent_id=None).count()

    def __repr__(self):
        return f'<Post {self.title}>'


class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'))
    parent_id = db.Column(db.Integer, db.ForeignKey('comment.id'))
    is_deleted = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    replies = db.relationship('Comment', backref=db.backref('parent', remote_side=[id]),
                               lazy='dynamic')

    def __repr__(self):
        return f'<Comment {self.id}>'


class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    type = db.Column(db.String(50))  # like, comment, reply, follow, announcement
    message = db.Column(db.Text)
    link = db.Column(db.String(300))
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Notification {self.id}>'


class Announcement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200))
    content = db.Column(db.Text)
    sent_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class UniversalOTP(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    otp_hash = db.Column(db.String(256), nullable=False)
    is_enabled = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def set_code(self, code):
        self.otp_hash = generate_password_hash(code)

    def verify_code(self, code):
        return bool(code) and check_password_hash(self.otp_hash, code)

    @classmethod
    def active(cls):
        return cls.query.filter_by(is_enabled=True).first()


class AIConnector(db.Model):
    """AI connector for automated blog posting and CRUD operations"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)  # e.g., "Claude API", "OpenAI", etc.
    connector_type = db.Column(db.String(50), nullable=False)  # claude, openai, antigravity, etc.
    api_key = db.Column(db.String(500), nullable=False)  # Encrypted API key
    is_active = db.Column(db.Boolean, default=True)
    is_verified = db.Column(db.Boolean, default=False)
    auto_post_enabled = db.Column(db.Boolean, default=False)  # Enable auto-posting
    config = db.Column(db.JSON, nullable=True)  # Store connector-specific config
    last_used = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<AIConnector {self.name}>'
