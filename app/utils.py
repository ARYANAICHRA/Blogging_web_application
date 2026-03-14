import os
import re
import random
import string
import pyotp
import qrcode
import io
import base64
import traceback
from flask import current_app, render_template
from flask_mail import Message
from app import mail, db
from app.models import Notification


def generate_otp():
    return ''.join(random.choices(string.digits, k=6))


def send_email(subject, recipients, html_body, text_body=''):
    try:
        sender = current_app.config.get('MAIL_DEFAULT_SENDER')
        msg = Message(subject=subject, sender=sender, recipients=recipients)
        msg.html = html_body
        msg.body = text_body or 'Please view this email in an HTML-capable client.'
        mail.send(msg)
        return True
    except Exception as exc:
        print(f"[EMAIL ERROR] {exc}")
        traceback.print_exc()
        return False


def send_otp_email(user, otp, purpose='verification'):
    subjects = {
        'verification': 'Verify Your Email - BlogSphere',
        'reset': 'Password Reset OTP - BlogSphere',
        'login_2fa': 'Two-Factor Authentication Code - BlogSphere',
    }
    subject = subjects.get(purpose, 'Your OTP - BlogSphere')
    html = render_template('email/otp.html', user=user, otp=otp, purpose=purpose)
    return send_email(subject, [user.email], html)


def send_publication_email(user, post):
    subject = f'Your post "{post.title}" is now live!'
    html = render_template('email/post_published.html', user=user, post=post)
    return send_email(subject, [user.email], html)


def send_announcement_email(users, title, content):
    for user in users:
        html = render_template('email/announcement.html', user=user, title=title, content=content)
        send_email(f'Announcement: {title}', [user.email], html)


def send_welcome_email(user):
    html = render_template('email/welcome.html', user=user)
    return send_email('Welcome to BlogSphere!', [user.email], html)


def send_password_reset_confirmation(user):
    html = render_template('email/password_changed.html', user=user)
    return send_email('Password Changed - BlogSphere', [user.email], html)


def slugify(text):
    text = text.lower()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_-]+', '-', text)
    return text.strip('-')


def unique_slug(title, model, existing_id=None):
    base = slugify(title)
    slug = base
    counter = 1
    while True:
        q = model.query.filter_by(slug=slug)
        if existing_id:
            q = q.filter(model.id != existing_id)
        if not q.first():
            break
        slug = f"{base}-{counter}"
        counter += 1
    return slug


def save_image(file, folder='posts', size=(800, 600)):
    from PIL import Image
    import uuid
    ext = file.filename.rsplit('.', 1)[-1].lower()
    filename = f"{uuid.uuid4().hex}.{ext}"
    upload_path = os.path.join(current_app.config['UPLOAD_FOLDER'], folder)
    os.makedirs(upload_path, exist_ok=True)
    filepath = os.path.join(upload_path, filename)
    img = Image.open(file)
    img.thumbnail(size, Image.LANCZOS)
    img.save(filepath)
    return filename


def create_notification(user_id, ntype, message, link=''):
    n = Notification(user_id=user_id, type=ntype, message=message, link=link)
    db.session.add(n)
    db.session.commit()


def generate_2fa_secret():
    return pyotp.random_base32()


def get_2fa_qr(user):
    totp = pyotp.TOTP(user.two_factor_secret)
    uri = totp.provisioning_uri(user.email, issuer_name='BlogSphere')
    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return base64.b64encode(buf.getvalue()).decode()


def verify_2fa_token(user, token):
    totp = pyotp.TOTP(user.two_factor_secret)
    return totp.verify(token)


def allowed_image(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg', 'gif', 'webp'}
