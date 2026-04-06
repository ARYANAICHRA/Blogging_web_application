import os
from datetime import timedelta
from urllib.parse import urlencode
from flask import Flask, session, request
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_mail import Mail
from flask_migrate import Migrate
from werkzeug.middleware.proxy_fix import ProxyFix
from dotenv import load_dotenv

load_dotenv()

db = SQLAlchemy()
login_manager = LoginManager()
mail = Mail()


def create_app():
    app = Flask(__name__)

    app_env = os.environ.get('APP_ENV', os.environ.get('FLASK_ENV', 'development')).lower()
    is_production = app_env == 'production'
    force_https = os.environ.get('FORCE_HTTPS', 'false').lower() == 'true'
    secure_cookies = is_production or force_https

    database_url = os.environ.get('DATABASE_URL', 'sqlite:///blog.db')
    # Normalize legacy postgres URL for SQLAlchemy 2+ compatibility.
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)

    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'change-me-in-production')
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
    }
    app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static', 'uploads')
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
    app.config['PREFERRED_URL_SCHEME'] = 'https' if secure_cookies else 'http'

    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['SESSION_COOKIE_SECURE'] = secure_cookies
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)
    app.config['REMEMBER_COOKIE_DURATION'] = timedelta(days=14)
    app.config['REMEMBER_COOKIE_HTTPONLY'] = True
    app.config['REMEMBER_COOKIE_SAMESITE'] = 'Lax'
    app.config['REMEMBER_COOKIE_SECURE'] = secure_cookies

    _mail_user = os.environ.get('MAIL_USERNAME', '')
    _mail_sender = os.environ.get('MAIL_DEFAULT_SENDER', _mail_user)
    app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
    app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'true').lower() == 'true'
    app.config['MAIL_USE_SSL'] = False
    app.config['MAIL_USERNAME'] = _mail_user
    app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD', '')
    app.config['MAIL_DEFAULT_SENDER'] = ('BlogSphere', _mail_sender)
    app.config['MAIL_MAX_EMAILS'] = None
    app.config['MAIL_ASCII_ATTACHMENTS'] = False
    app.config['ANALYTICS_MEASUREMENT_ID'] = os.environ.get('ANALYTICS_MEASUREMENT_ID', '').strip()

    db.init_app(app)
    migrate = Migrate(app, db)
    login_manager.init_app(app)
    mail.init_app(app)

    if is_production or force_https:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = 'info'
    login_manager.session_protection = 'strong'

    @app.before_request
    def make_session_permanent():
        session.permanent = True

    @app.context_processor
    def inject_site_metadata():
        tracking_keys = {'gclid', 'fbclid', 'msclkid', 'igshid', 'ref', 'ref_src'}
        tracking_prefixes = ('utm_', 'mc_', 'ga_')
        keep_params_by_endpoint = {
            'blog.index': {'page', 'q'},
        }

        endpoint = request.endpoint or ''
        allowed_params = keep_params_by_endpoint.get(endpoint, set())
        cleaned_params = []

        for key in request.args.keys():
            key_l = key.lower()
            if key_l in tracking_keys or any(key_l.startswith(prefix) for prefix in tracking_prefixes):
                continue
            if allowed_params and key not in allowed_params:
                continue
            if not allowed_params:
                continue
            for value in request.args.getlist(key):
                val = (value or '').strip()
                if not val:
                    continue
                if key == 'page' and val == '1':
                    continue
                cleaned_params.append((key, val))

        canonical_href = request.base_url
        if cleaned_params:
            canonical_href = f"{request.base_url}?{urlencode(cleaned_params, doseq=True)}"

        return {
            'site_name': 'BlogSphere',
            'analytics_measurement_id': app.config.get('ANALYTICS_MEASUREMENT_ID', ''),
            'canonical_href': canonical_href,
        }

    from app.routes.auth import auth_bp
    from app.routes.user import user_bp
    from app.routes.admin import admin_bp
    from app.routes.blog import blog_bp
    from app.routes.api import api_bp

    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(user_bp, url_prefix='/user')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(blog_bp, url_prefix='/')
    app.register_blueprint(api_bp, url_prefix='/api')

    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'avatars'), exist_ok=True)
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'posts'), exist_ok=True)

    auto_db_create = os.environ.get('AUTO_DB_CREATE', 'true').lower() == 'true'
    with app.app_context():
        if auto_db_create:
            db.create_all()
        _create_admin()

    return app


def _create_admin():
    from app.models import User
    from werkzeug.security import generate_password_hash

    admin_email = os.environ.get('ADMIN_EMAIL', 'admin@blogsphere.com')
    admin_username = os.environ.get('ADMIN_USERNAME', 'admin')
    admin_password = os.environ.get('ADMIN_PASSWORD', 'Admin@123')

    admin = User.query.filter_by(role='admin').first()
    if not admin:
        admin = User(
            username=admin_username,
            email=admin_email,
            password_hash=generate_password_hash(admin_password),
            role='admin',
            is_verified=True,
            is_active=True,
        )
        db.session.add(admin)
        db.session.commit()
    else:
        admin.email = admin_email
        admin.username = admin_username
        db.session.commit()
