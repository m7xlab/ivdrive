"""Reusable SMTP email service for iVDrive."""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.config import settings

logger = logging.getLogger(__name__)


def _build_invite_html(invite_link: str, email: str) -> str:
    """Build a clean HTML invitation email."""
    return f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin:0;padding:0;background-color:#0a0a0f;font-family:'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color:#0a0a0f;">
<tr><td align="center" style="padding:40px 20px;">
<table role="presentation" width="560" cellspacing="0" cellpadding="0" style="background-color:#141419;border-radius:16px;border:1px solid #1e1e2a;overflow:hidden;">

  <!-- Header -->
  <tr><td style="padding:40px 40px 24px;text-align:center;">
    <h1 style="margin:0;font-size:28px;font-weight:700;letter-spacing:-0.5px;">
      <span style="background:linear-gradient(135deg,#00e676,#00bcd4);-webkit-background-clip:text;-webkit-text-fill-color:transparent;">iV</span><span style="color:#e0f7fa;">Drive</span>
    </h1>
    <p style="margin:8px 0 0;font-size:13px;color:#888;text-transform:uppercase;letter-spacing:2px;font-weight:600;">You're Invited</p>
  </td></tr>

  <!-- Divider -->
  <tr><td style="padding:0 40px;">
    <div style="height:1px;background:linear-gradient(90deg,transparent,#1e1e2a,transparent);"></div>
  </td></tr>

  <!-- Body -->
  <tr><td style="padding:32px 40px;">
    <p style="margin:0 0 16px;font-size:16px;color:#c8c8d0;line-height:1.6;">
      Great news! Your request to join <strong style="color:#e0f7fa;">iVDrive</strong> has been approved.
    </p>
    <p style="margin:0 0 24px;font-size:15px;color:#888;line-height:1.6;">
      Click the button below to create your account and start monitoring your electric vehicle.
    </p>

    <!-- CTA Button -->
    <table role="presentation" cellspacing="0" cellpadding="0" style="margin:0 auto;">
    <tr><td style="border-radius:10px;background:linear-gradient(135deg,#00e676,#00bcd4);">
      <a href="{invite_link}" target="_blank" style="display:inline-block;padding:14px 40px;font-size:16px;font-weight:600;color:#0a0a0f;text-decoration:none;letter-spacing:0.3px;">
        Create Your Account &rarr;
      </a>
    </td></tr>
    </table>

    <p style="margin:28px 0 0;font-size:13px;color:#555;line-height:1.5;text-align:center;">
      This invitation was sent to <strong style="color:#888;">{email}</strong>.<br>
      If you did not request access, you can safely ignore this email.
    </p>
  </td></tr>

  <!-- Footer -->
  <tr><td style="padding:24px 40px;border-top:1px solid #1e1e2a;">
    <p style="margin:0;font-size:12px;color:#444;text-align:center;">
      &copy; iVDrive &mdash; Premium EV Monitoring
    </p>
  </td></tr>

</table>
</td></tr>
</table>
</body>
</html>"""


def _build_invite_plain(invite_link: str, email: str) -> str:
    """Plaintext fallback for the invitation email."""
    return (
        f"You're Invited to iVDrive!\n\n"
        f"Your request to join iVDrive has been approved.\n\n"
        f"Create your account here:\n{invite_link}\n\n"
        f"This invitation was sent to {email}.\n"
        f"If you did not request access, you can safely ignore this email.\n\n"
        f"— iVDrive"
    )


def _build_password_reset_html(reset_link: str, email: str) -> str:
    """Build a clean HTML password reset email."""
    return f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin:0;padding:0;background-color:#0a0a0f;font-family:'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color:#0a0a0f;">
<tr><td align="center" style="padding:40px 20px;">
<table role="presentation" width="560" cellspacing="0" cellpadding="0" style="background-color:#141419;border-radius:16px;border:1px solid #1e1e2a;overflow:hidden;">

  <!-- Header -->
  <tr><td style="padding:40px 40px 24px;text-align:center;">
    <h1 style="margin:0;font-size:28px;font-weight:700;letter-spacing:-0.5px;">
      <span style="background:linear-gradient(135deg,#00e676,#00bcd4);-webkit-background-clip:text;-webkit-text-fill-color:transparent;">iV</span><span style="color:#e0f7fa;">Drive</span>
    </h1>
    <p style="margin:8px 0 0;font-size:13px;color:#888;text-transform:uppercase;letter-spacing:2px;font-weight:600;">Password Reset</p>
  </td></tr>

  <!-- Divider -->
  <tr><td style="padding:0 40px;">
    <div style="height:1px;background:linear-gradient(90deg,transparent,#1e1e2a,transparent);"></div>
  </td></tr>

  <!-- Body -->
  <tr><td style="padding:32px 40px;">
    <p style="margin:0 0 16px;font-size:16px;color:#c8c8d0;line-height:1.6;">
      We received a request to reset the password for your <strong style="color:#e0f7fa;">iVDrive</strong> account.
    </p>
    <p style="margin:0 0 24px;font-size:15px;color:#888;line-height:1.6;">
      Click the button below to set a new password. This link is valid for <strong style="color:#c8c8d0;">30 minutes</strong>.
    </p>

    <!-- CTA Button -->
    <table role="presentation" cellspacing="0" cellpadding="0" style="margin:0 auto;">
    <tr><td style="border-radius:10px;background:linear-gradient(135deg,#00e676,#00bcd4);">
      <a href="{reset_link}" target="_blank" style="display:inline-block;padding:14px 40px;font-size:16px;font-weight:600;color:#0a0a0f;text-decoration:none;letter-spacing:0.3px;">
        Reset Password &rarr;
      </a>
    </td></tr>
    </table>

    <p style="margin:28px 0 0;font-size:13px;color:#555;line-height:1.5;text-align:center;">
      This email was sent to <strong style="color:#888;">{email}</strong>.<br>
      If you did not request a password reset, you can safely ignore this email.<br>
      Your password will not change unless you click the link above.
    </p>
  </td></tr>

  <!-- Footer -->
  <tr><td style="padding:24px 40px;border-top:1px solid #1e1e2a;">
    <p style="margin:0;font-size:12px;color:#444;text-align:center;">
      &copy; iVDrive &mdash; Premium EV Monitoring
    </p>
  </td></tr>

</table>
</td></tr>
</table>
</body>
</html>"""


def _build_password_reset_plain(reset_link: str, email: str) -> str:
    """Plaintext fallback for the password reset email."""
    return (
        f"iVDrive — Password Reset\n\n"
        f"We received a request to reset the password for your account ({email}).\n\n"
        f"Reset your password here (link valid for 30 minutes):\n{reset_link}\n\n"
        f"If you did not request this, you can safely ignore this email.\n\n"
        f"— iVDrive"
    )


def send_password_reset_email(to_email: str, reset_link: str) -> bool:
    """Send a password reset email. Returns True on success, False on failure.

    If SMTP is not configured, logs the reset link and returns True
    (graceful degradation for dev/testing).
    """
    if not all([settings.smtp_host, settings.smtp_user, settings.smtp_pass]):
        logger.warning(
            "SMTP not configured — password reset link for %s: %s",
            to_email,
            reset_link,
        )
        return True  # non-blocking: the token will appear in logs for dev use

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Reset your iVDrive password"
    msg["From"] = settings.smtp_from or settings.smtp_user
    msg["To"] = to_email

    msg.attach(MIMEText(_build_password_reset_plain(reset_link, to_email), "plain"))
    msg.attach(MIMEText(_build_password_reset_html(reset_link, to_email), "html"))

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
            server.ehlo()
            if settings.smtp_port != 25:
                server.starttls()
                server.ehlo()
            server.login(settings.smtp_user, settings.smtp_pass)
            server.sendmail(msg["From"], [to_email], msg.as_string())
        logger.info("Password reset email sent to %s", to_email)
        return True
    except Exception:
        logger.exception("Failed to send password reset email to %s", to_email)
        return False


def send_invite_email(to_email: str, invite_link: str) -> bool:
    """Send an invitation email. Returns True on success, False on failure.

    If SMTP is not configured, logs the invite link and returns True
    (graceful degradation for dev/testing).
    """
    if not all([settings.smtp_host, settings.smtp_user, settings.smtp_pass]):
        logger.warning(
            "SMTP not configured — invite link for %s: %s",
            to_email,
            invite_link,
        )
        return True  # non-blocking: admin still sees the link in the response

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "You're Invited to iVDrive"
    msg["From"] = settings.smtp_from or settings.smtp_user
    msg["To"] = to_email

    msg.attach(MIMEText(_build_invite_plain(invite_link, to_email), "plain"))
    msg.attach(MIMEText(_build_invite_html(invite_link, to_email), "html"))

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
            server.set_debuglevel(1)  # Enable debug output
            server.ehlo()
            if settings.smtp_port != 25:
                server.starttls()
                server.ehlo()
            server.login(settings.smtp_user, settings.smtp_pass)
            server.sendmail(msg["From"], [to_email], msg.as_string())
        logger.info("Invitation email sent to %s", to_email)
        return True
    except Exception:
        logger.exception("Failed to send invitation email to %s", to_email)
        return False
