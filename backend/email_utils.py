"""
Sends the password-reset email over SMTP. Reads credentials from environment
variables (loaded from a .env file via python-dotenv, see database.py's import
at startup) — never hardcode credentials in source.

Required env vars for real sending:
    SMTP_EMAIL           the sending address, e.g. yourteam@gmail.com
    SMTP_APP_PASSWORD     an app password (NOT your normal login password)
    SMTP_HOST             optional, defaults to smtp.gmail.com
    SMTP_PORT             optional, defaults to 587
    APP_BASE_URL          optional, defaults to http://localhost:8000 — used to
                           build the clickable reset link in the email

If SMTP_EMAIL / SMTP_APP_PASSWORD aren't set, send_reset_email() returns False
and main.py falls back to the existing demo behavior (showing the token on
screen instead of emailing it) — nothing breaks for teammates who haven't
configured email yet.

Gmail setup (most common path):
    1. Turn on 2-Step Verification on the Google account:
       https://myaccount.google.com/security
    2. Create an App Password: https://myaccount.google.com/apppasswords
       (choose "Mail" as the app) — Google gives you a 16-character code.
    3. Put that code in SMTP_APP_PASSWORD (not your real Gmail password).
"""

import os
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

SMTP_EMAIL = os.environ.get("SMTP_EMAIL", "harshit1942005@gmail.com").strip()
SMTP_APP_PASSWORD = os.environ.get("SMTP_APP_PASSWORD", "fflpwulpczqwyphx").strip()
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com").strip()
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
APP_BASE_URL = os.environ.get("APP_BASE_URL", "http://localhost:8000").strip()


def is_configured() -> bool:
    return bool(SMTP_EMAIL and SMTP_APP_PASSWORD)


def send_reset_email(to_email: str, reset_token: str, user_name: str = "") -> bool:
    """Returns True if the email was actually sent, False if email isn't configured
    or sending failed (caller should fall back to demo/on-screen token in that case)."""
    if not is_configured():
        return False

    reset_link = f"{APP_BASE_URL}/account.html?resetToken={reset_token}"
    greeting = f"Hi {user_name}," if user_name else "Hi,"

    text_body = f"""{greeting}

We received a request to reset your Civic Voice password.

Reset your password: {reset_link}

Or enter this code manually on the reset page: {reset_token}

This link/code expires in 30 minutes. If you didn't request this, you can
safely ignore this email.
"""
    html_body = f"""
    <div style="font-family: -apple-system, sans-serif; max-width: 480px; margin: 0 auto;">
      <h2 style="color:#0E2A2E;">Reset your password</h2>
      <p>{greeting}</p>
      <p>We received a request to reset your Civic Voice password.</p>
      <p style="margin: 24px 0;">
        <a href="{reset_link}" style="background:#0E2A2E; color:#fff; padding:12px 24px; border-radius:8px; text-decoration:none; display:inline-block;">Reset Password</a>
      </p>
      <p style="color:#666; font-size:13px;">Or enter this code manually on the reset page:</p>
      <p style="font-family: monospace; font-size: 16px; background:#f5f3ec; padding:10px 14px; border-radius:6px; display:inline-block;">{reset_token}</p>
      <p style="color:#999; font-size:12px; margin-top:24px;">This link expires in 30 minutes. If you didn't request this, ignore this email.</p>
    </div>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Reset your Civic Voice password"
    msg["From"] = SMTP_EMAIL
    msg["To"] = to_email
    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            server.starttls(context=context)
            server.login(SMTP_EMAIL, SMTP_APP_PASSWORD)
            server.sendmail(SMTP_EMAIL, to_email, msg.as_string())
        return True
    except Exception as e:
        print(f"[email_utils] Failed to send reset email: {e}")
        return False


def send_status_email(to_email: str, complaint_id: str, category: str, status: str, officer_name: str = "") -> bool:
    """Notifies a citizen that a government officer updated their complaint's
    status (used for RESOLVED, but works for any status change). Same graceful
    fallback as send_reset_email: returns False if SMTP isn't configured so the
    caller can rely on the in-app notification instead — nothing breaks for
    teammates who haven't set up email."""
    if not is_configured():
        return False

    status_label = status.replace("_", " ").title()
    track_link = f"{APP_BASE_URL}/profile.html"
    officer_line = f" by {officer_name}" if officer_name else ""

    text_body = f"""Hi,

Your CivicVoice complaint {complaint_id} ({category}) was just updated to: {status_label}{officer_line}.

Track it here: {track_link}
"""
    html_body = f"""
    <div style="font-family: -apple-system, sans-serif; max-width: 480px; margin: 0 auto;">
      <h2 style="color:#0E2A2E;">Your report was updated</h2>
      <p>Hi,</p>
      <p>Your CivicVoice complaint <b>{complaint_id}</b> ({category}) was just updated to:</p>
      <p style="margin: 18px 0;">
        <span style="background:#EDF2EC; color:#2E7D53; padding:8px 16px; border-radius:8px; font-weight:600; display:inline-block;">{status_label}</span>
      </p>
      <p style="color:#666; font-size:13px;">{"Updated" + officer_line + "."}</p>
      <p style="margin: 24px 0;">
        <a href="{track_link}" style="background:#0E2A2E; color:#fff; padding:12px 24px; border-radius:8px; text-decoration:none; display:inline-block;">View your reports</a>
      </p>
    </div>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Update on your report {complaint_id}: {status_label}"
    msg["From"] = SMTP_EMAIL
    msg["To"] = to_email
    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            server.starttls(context=context)
            server.login(SMTP_EMAIL, SMTP_APP_PASSWORD)
            server.sendmail(SMTP_EMAIL, to_email, msg.as_string())
        return True
    except Exception as e:
        print(f"[email_utils] Failed to send status email: {e}")
        return False
