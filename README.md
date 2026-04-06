![Build Status](https://github.com/ARYANAICHRA/Blogging_web_application/actions/workflows/python-app.yml/badge.svg)
![Python](https://img.shields.io/badge/Python-3.10-blue)
![Flask](https://img.shields.io/badge/Flask-WebApp-black)
![Database](https://img.shields.io/badge/Database-SQLite-blue)

# BlogSphere

A full-stack blogging platform built with Flask. Supports user registration, markdown posts, comments, follows, bookmarks, likes, two-factor authentication, and a full admin panel.

---

## What's inside

**Auth** — register with email OTP verification, login, forgot password, 2FA (authenticator app or email OTP), remember me sessions.

**Blog** — create and edit posts with a markdown editor, upload cover images and inline images, publish/draft/archive, view counts, likes, bookmarks, comments with replies, share links.

**User** — profile pages, follow/unfollow authors, following feed, notification inbox, edit profile and avatar, change password, 2FA setup.

**Admin** — dashboard with stats, manage users (block/unblock/delete/reset password), manage posts and comments, send announcements (in-app + optional email).

---

## Setup

**1. Clone and go into the folder**

```bash
cd blogsphere
```

**2. Create a virtual environment**

```bash
python -m venv venv
source venv/bin/activate       # Mac/Linux
venv\Scripts\activate          # Windows
```

**3. Install dependencies**

```bash
pip install -r requirements.txt
```

**4. Configure your environment**

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

The important ones to change:

```
SECRET_KEY        — any long random string
MAIL_USERNAME     — your Gmail address
MAIL_PASSWORD     — Gmail App Password (16 characters, not your regular password)
ADMIN_EMAIL       — email for the admin account
ADMIN_PASSWORD    — password for the admin account
```

> To get a Gmail App Password: Google Account → Security → 2-Step Verification → App Passwords

**5. Initialize upload folders**

```bash
python init_assets.py
```

**6. Run**

```bash
python run.py
```

Open http://localhost:5000

---

## Admin account

Created automatically on first run using the values in `.env`. Default credentials if you haven't changed them:

- Email: `admin@blogsphere.com`
- Password: `Admin@123`

Change the password after first login. The admin account email and username update automatically whenever you change `ADMIN_EMAIL` / `ADMIN_USERNAME` in `.env` and restart.

---

## Testing email

Visit this URL after starting the app to check if SMTP is configured correctly:

```
http://localhost:5000/auth/test-email
```

Returns `{"success": true}` if working, or the error message if something's wrong.

---

## Project structure

```
blogsphere/
├── run.py                        # start the app
├── init_assets.py                # create upload folders on first run
├── requirements.txt
├── .env                          # your secrets (never commit this)
├── .env.example                  # template for .env
├── .gitignore
└── app/
    ├── __init__.py               # app factory, extensions, admin setup
    ├── models.py                 # database models (User, Post, Comment, etc.)
    ├── utils.py                  # helpers: email, OTP, image upload, slug, 2FA
    ├── routes/
    │   ├── auth.py               # register, login, OTP, 2FA, password reset
    │   ├── blog.py               # posts, comments, likes, bookmarks
    │   ├── user.py               # dashboard, profile, follow, notifications
    │   ├── admin.py              # admin panel
    │   └── api.py                # AJAX endpoints (notification count)
    ├── static/
    │   ├── css/main.css
    │   ├── js/main.js
    │   └── uploads/              # user-uploaded images (gitignored)
    └── templates/
        ├── base.html             # shared layout, navbar, notification popup
        ├── auth/                 # login, register, verify, 2FA, reset password
        ├── blog/                 # post list, post view, editor
        ├── user/                 # dashboard, profile, notifications, bookmarks
        ├── admin/                # admin pages
        └── email/                # HTML email templates
```

---

## Tech

- Python / Flask 3.0
- SQLite via SQLAlchemy (swap to PostgreSQL by changing `DATABASE_URL`)
- Flask-Login for sessions, Werkzeug for password hashing
- Flask-Mail for SMTP
- PyOTP + qrcode for 2FA
- Python-Markdown + Bleach for safe markdown rendering
- Pillow for image resizing
- Vanilla HTML/CSS/JS frontend, no build step needed

---

## Production deployment (Railway)

This project is now set up for Railway with:

- `Procfile` (Gunicorn start command)
- `railway.json` (deploy config)
- Production-safe app config in `app/__init__.py`

### Required Railway environment variables

Set these in Railway Variables:

- `SECRET_KEY` (required)
- `DATABASE_URL` (Railway Postgres connection string)
- `APP_ENV=production`
- `FLASK_DEBUG=false`
- `FORCE_HTTPS=true`
- `AUTO_DB_CREATE=true` (or `false` if using only migrations)
- `MAIL_*` variables if email features are enabled
- `ANALYTICS_MEASUREMENT_ID` (optional, for GA4)

### Deploy steps

1. Push this repo to GitHub.
2. Create a new Railway project from the GitHub repo.
3. Add a Railway Postgres service and set `DATABASE_URL`.
4. Add the environment variables listed above.
5. Deploy. Railway will run:

```bash
gunicorn run:app --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120
```

### Important note on uploads

`app/static/uploads` is local filesystem storage. On Railway, local disk is ephemeral, so uploaded files can be lost after restart/redeploy. For production, move uploads to object storage (Cloudinary / S3 / R2).
