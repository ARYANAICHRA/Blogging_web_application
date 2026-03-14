from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, login_required, current_user
from datetime import datetime, timedelta
from app import db
from app.models import User
from app.utils import (generate_otp, send_otp_email, send_welcome_email,
                        send_password_reset_confirmation, generate_2fa_secret,
                        get_2fa_qr, verify_2fa_token)

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('blog.index'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')

        if not all([username, email, password, confirm]):
            flash('All fields are required.', 'danger')
            return render_template('auth/register.html')
        if password != confirm:
            flash('Passwords do not match.', 'danger')
            return render_template('auth/register.html')
        if len(password) < 8:
            flash('Password must be at least 8 characters.', 'danger')
            return render_template('auth/register.html')
        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'danger')
            return render_template('auth/register.html')
        if User.query.filter_by(username=username).first():
            flash('Username already taken.', 'danger')
            return render_template('auth/register.html')

        # Read avatar FIRST before anything else touches the request
        from app.utils import save_image, allowed_image
        avatar_filename = None
        f = request.files.get('avatar')
        if f and f.filename and allowed_image(f.filename):
            try:
                avatar_filename = save_image(f, folder='avatars', size=(300, 300))
            except Exception as e:
                print(f"Avatar upload error: {e}")

        otp = generate_otp()
        user = User(username=username, email=email, otp_code=otp,
                    otp_expires=datetime.utcnow() + timedelta(minutes=10))
        user.set_password(password)

        if avatar_filename:
            user.avatar = avatar_filename

        db.session.add(user)
        db.session.commit()
        send_otp_email(user, otp, 'verification')
        session['pending_verify_id'] = user.id
        flash('OTP sent to your email. Please verify.', 'success')
        return redirect(url_for('auth.verify_email'))
    return render_template('auth/register.html')


@auth_bp.route('/verify-email', methods=['GET', 'POST'])
def verify_email():
    user_id = session.get('pending_verify_id')
    if not user_id:
        return redirect(url_for('auth.register'))
    user = User.query.get(user_id)
    if not user:
        return redirect(url_for('auth.register'))

    if request.method == 'POST':
        otp = request.form.get('otp', '').strip()
        if user.otp_code == otp and user.otp_expires > datetime.utcnow():
            user.is_verified = True
            user.otp_code = None
            user.otp_expires = None
            db.session.commit()
            send_welcome_email(user)
            session.pop('pending_verify_id', None)
            login_user(user)
            flash('Email verified! Welcome to BlogSphere!', 'success')
            return redirect(url_for('blog.index'))
        else:
            flash('Invalid or expired OTP.', 'danger')
    return render_template('auth/verify_email.html', email=user.email)


@auth_bp.route('/resend-otp')
def resend_otp():
    user_id = session.get('pending_verify_id') or session.get('reset_user_id') or session.get('2fa_user_id')
    if not user_id:
        flash('Session expired.', 'danger')
        return redirect(url_for('auth.login'))
    user = User.query.get(user_id)
    otp = generate_otp()
    user.otp_code = otp
    user.otp_expires = datetime.utcnow() + timedelta(minutes=10)
    db.session.commit()
    send_otp_email(user, otp, 'verification')
    flash('OTP resent!', 'success')
    return redirect(request.referrer or url_for('auth.verify_email'))


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('blog.index'))
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        remember = request.form.get('remember', False)

        user = User.query.filter_by(email=email).first()
        if not user or not user.check_password(password):
            flash('Invalid email or password.', 'danger')
            return render_template('auth/login.html')
        if user.is_blocked:
            flash('Your account has been blocked. Contact support.', 'danger')
            return render_template('auth/login.html')
        if not user.is_verified:
            session['pending_verify_id'] = user.id
            otp = generate_otp()
            user.otp_code = otp
            user.otp_expires = datetime.utcnow() + timedelta(minutes=10)
            db.session.commit()
            send_otp_email(user, otp, 'verification')
            flash('Please verify your email first.', 'warning')
            return redirect(url_for('auth.verify_email'))
        if user.two_factor_enabled:
            session['2fa_user_id'] = user.id
            session['2fa_remember'] = bool(remember)
            return redirect(url_for('auth.two_factor'))

        login_user(user, remember=bool(remember))
        user.last_seen = datetime.utcnow()
        db.session.commit()
        next_page = request.args.get('next')
        flash(f'Welcome back, {user.username}!', 'success')
        return redirect(next_page or url_for('blog.index'))
    return render_template('auth/login.html')


@auth_bp.route('/two-factor', methods=['GET', 'POST'])
def two_factor():
    user_id = session.get('2fa_user_id')
    if not user_id:
        return redirect(url_for('auth.login'))
    user = User.query.get(user_id)

    if request.method == 'POST':
        token = request.form.get('token', '').strip()
        method = request.form.get('method', 'app')

        if method == 'email':
            if user.otp_code == token and user.otp_expires > datetime.utcnow():
                user.otp_code = None
                user.otp_expires = None
                db.session.commit()
                login_user(user, remember=session.pop('2fa_remember', False))
                session.pop('2fa_user_id', None)
                flash('Logged in successfully!', 'success')
                return redirect(url_for('blog.index'))
        else:
            if verify_2fa_token(user, token):
                login_user(user, remember=session.pop('2fa_remember', False))
                session.pop('2fa_user_id', None)
                flash('Logged in successfully!', 'success')
                return redirect(url_for('blog.index'))
        flash('Invalid authentication code.', 'danger')

    return render_template('auth/two_factor.html')


@auth_bp.route('/send-2fa-email')
def send_2fa_email():
    user_id = session.get('2fa_user_id')
    if not user_id:
        return redirect(url_for('auth.login'))
    user = User.query.get(user_id)
    otp = generate_otp()
    user.otp_code = otp
    user.otp_expires = datetime.utcnow() + timedelta(minutes=10)
    db.session.commit()
    send_otp_email(user, otp, 'login_2fa')
    flash('OTP sent to your email.', 'success')
    return redirect(url_for('auth.two_factor'))


@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        user = User.query.filter_by(email=email).first()
        if user:
            otp = generate_otp()
            user.otp_code = otp
            user.otp_expires = datetime.utcnow() + timedelta(minutes=10)
            db.session.commit()
            send_otp_email(user, otp, 'reset')
            session['reset_user_id'] = user.id
        flash('If that email is registered, an OTP has been sent.', 'info')
        return redirect(url_for('auth.reset_password'))
    return render_template('auth/forgot_password.html')


@auth_bp.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    user_id = session.get('reset_user_id')
    if not user_id:
        return redirect(url_for('auth.forgot_password'))
    user = User.query.get(user_id)

    if request.method == 'POST':
        otp = request.form.get('otp', '').strip()
        new_password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')

        if not new_password or new_password != confirm:
            flash('Passwords do not match.', 'danger')
            return render_template('auth/reset_password.html')
        if len(new_password) < 8:
            flash('Password must be at least 8 characters.', 'danger')
            return render_template('auth/reset_password.html')
        if user.otp_code == otp and user.otp_expires > datetime.utcnow():
            user.set_password(new_password)
            user.otp_code = None
            user.otp_expires = None
            db.session.commit()
            send_password_reset_confirmation(user)
            session.pop('reset_user_id', None)
            flash('Password reset successful. Please login.', 'success')
            return redirect(url_for('auth.login'))
        flash('Invalid or expired OTP.', 'danger')
    return render_template('auth/reset_password.html')


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out successfully.', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/test-email')
def test_email():
    """Visit /auth/test-email to verify SMTP is working. Remove in production."""
    import os, traceback
    from flask import current_app, jsonify
    from flask_mail import Message
    from app import mail

    to = os.environ.get('MAIL_USERNAME', '')
    if not to:
        return jsonify({'error': 'MAIL_USERNAME not set in .env'}), 500

    cfg = {k: ('***' if 'PASSWORD' in k else str(v))
           for k, v in current_app.config.items() if k.startswith('MAIL_')}
    try:
        sender = current_app.config.get('MAIL_DEFAULT_SENDER', ('BlogSphere', to))
        msg = Message(subject='BlogSphere — SMTP Test ✅', sender=sender, recipients=[to])
        msg.body = 'SMTP is working!'
        msg.html = '<h2 style="color:#c8502a">✦ BlogSphere</h2><p>SMTP is working correctly! 🎉</p>'
        mail.send(msg)
        return jsonify({'success': True, 'sent_to': to, 'config': cfg})
    except Exception as exc:
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(exc), 'config': cfg}), 500