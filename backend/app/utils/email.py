from flask import current_app
from flask_mail import Message

from ..extensions import mail


def send_reset_email(to_email, reset_token):
    """
    Sends a password-reset link to the given email address.

    Args:
        to_email    : recipient email string
        reset_token : the raw token value (goes into the URL)
    """
    base_url  = current_app.config.get("APP_URL", "http://localhost:5000")
    reset_url = f"{base_url}/auth/reset-password?token={reset_token}"
    sender    = current_app.config.get("MAIL_USERNAME")

    msg = Message(
        subject    = "Reset Your KYFF Store Password",
        sender     = sender,
        recipients = [to_email]
    )
    msg.body = (
        f"Hi,\n\n"
        f"You requested a password reset for your KYFF Store account.\n\n"
        f"Click the link below to reset your password (valid for 1 hour):\n"
        f"{reset_url}\n\n"
        f"If you didn't request this, you can safely ignore this email.\n\n"
        f"— The KYFF Team"
    )
    msg.html = (
        f"<p>Hi,</p>"
        f"<p>You requested a password reset for your KYFF Store account.</p>"
        f"<p><a href=\"{reset_url}\">Reset your password</a> (link valid for 1 hour)</p>"
        f"<p>If you didn't request this, you can safely ignore this email.</p>"
        f"<p>— The KYFF Team</p>"
    )
    mail.send(msg)
