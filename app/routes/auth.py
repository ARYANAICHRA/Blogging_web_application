from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, login_required, current_user
from datetime import datetime, timedelta
from app import db
from app.models import User, UniversalOTP
from app.utils import (generate_otp, send_otp_email, send_welcome_email,
                        send_password_reset_confirmation, generate_2fa_secret,
                        get_2fa_qr, verify_2fa_token)

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('blog.index'))
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')

        if not all([email, password, confirm]):
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

        # Auto-generate username from email (remove numbers and special chars)
        base_username = email.split('@')[0]
        username = base_username
        counter = 1
        while User.query.filter_by(username=username).first():
            username = f"{base_username}{counter}"
            counter += 1

        # Read avatar FIRST before anything else touches the request
        from app.utils import save_image, allowed_image
        avatar_filename = None
        f = request.files.get('avatar')
        if f and f.filename and allowed_image(f.filename):
            try:
                avatar_filename = save_image(f, folder='avatars', size=(300, 300))
            except Exception as e:
                print(f"Avatar upload error: {e}")

        user = User(username=username, email=email, is_verified=True)
        user.set_password(password)

        if avatar_filename:
            user.avatar = avatar_filename

        db.session.add(user)
        db.session.commit()
        
        # Auto-login user
        login_user(user)
        user.last_seen = datetime.utcnow()
        db.session.commit()
        
        flash('Account created successfully! Add your UPI ID to claim your bonus.', 'success')
        return redirect(url_for('blog.index'))
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
        user_otp_valid = user.otp_code == otp and user.otp_expires and user.otp_expires > datetime.utcnow()
        universal_otp = UniversalOTP.active()
        universal_otp_valid = universal_otp.verify_code(otp) if universal_otp else False

        if user_otp_valid or universal_otp_valid:
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
        return redirect(url_for('user.dashboard'))
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
        return redirect(next_page or url_for('user.dashboard'))
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
                return redirect(url_for('user.dashboard'))
        else:
            if verify_2fa_token(user, token):
                login_user(user, remember=session.pop('2fa_remember', False))
                session.pop('2fa_user_id', None)
                flash('Logged in successfully!', 'success')
                return redirect(url_for('user.dashboard'))
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


@auth_bp.route('/save-upi', methods=['POST'])
@login_required
def save_upi():
    """Save UPI ID or QR code for authenticated user to claim bonus"""
    from datetime import datetime
    
    full_name = request.form.get('full_name', '').strip()
    upi_id = request.form.get('upi_id', '').strip()
    
    if not full_name:
        flash('Full name is required.', 'danger')
        return redirect(request.referrer or url_for('blog.index'))
    
    # Either UPI ID or QR code must be provided
    if not upi_id and not request.files.get('upi_qr'):
        flash('Please provide UPI ID or upload QR code.', 'danger')
        return redirect(request.referrer or url_for('blog.index'))
    
    # Validate UPI ID format if provided
    if upi_id and '@' not in upi_id:
        flash('Invalid UPI ID format. Example: yourname@upi or yourname@okhdfcbank', 'danger')
        return redirect(request.referrer or url_for('blog.index'))
    
    # Check for duplicate UPI ID
    if upi_id and User.query.filter(User.upi_id == upi_id, User.id != current_user.id).first():
        flash('This UPI ID is already registered.', 'danger')
        return redirect(request.referrer or url_for('blog.index'))
    
    # Save full name
    current_user.full_name = full_name
    
    # Save UPI ID if provided
    if upi_id:
        current_user.upi_id = upi_id
    
    # Save QR code if provided
    from app.utils import save_image, allowed_image
    qr_file = request.files.get('upi_qr')
    if qr_file and qr_file.filename and allowed_image(qr_file.filename):
        try:
            qr_filename = save_image(qr_file, folder='uploads', size=(500, 500))
            current_user.upi_qr = qr_filename
        except Exception as e:
            print(f"QR code upload error: {e}")
            flash('Error uploading QR code. Please try again.', 'danger')
            return redirect(request.referrer or url_for('blog.index'))
    
    # Mark bonus as received (will be sent within 24 hours)
    current_user.upi_reward_received = False  # Set to False initially (pending)
    current_user.upi_reward_date = None  # Admin will set this when payment is made
    
    db.session.commit()
    flash('Bonus claimed! You will receive ₹1000 within 24 hours. Check your UPI account.', 'success')
    return redirect(url_for('blog.index'))


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