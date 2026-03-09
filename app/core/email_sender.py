import os
import ssl
import smtplib
import logging
from email.message import EmailMessage


logger = logging.getLogger(__name__)


def _get_smtp_config() -> tuple[str, int, int, str, str, str, bool]:
    smtp_host = os.getenv("SMTP_HOST")
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")
    smtp_from = os.getenv("SMTP_FROM") or os.getenv("EMAIL_FROM") or smtp_user

    smtp_port_raw = os.getenv("SMTP_PORT", "587")
    smtp_timeout_raw = os.getenv("SMTP_TIMEOUT", "15")

    try:
        smtp_port = int(smtp_port_raw)
    except ValueError as exc:
        raise RuntimeError(f"Invalid SMTP_PORT value: {smtp_port_raw}") from exc

    try:
        smtp_timeout = int(smtp_timeout_raw)
    except ValueError as exc:
        raise RuntimeError(f"Invalid SMTP_TIMEOUT value: {smtp_timeout_raw}") from exc

    if not all([smtp_host, smtp_user, smtp_pass, smtp_from]):
        raise RuntimeError("Missing SMTP env vars. Check SMTP_HOST/SMTP_USER/SMTP_PASS/SMTP_FROM")

    starttls_env = os.getenv("SMTP_USE_STARTTLS")
    if starttls_env is None:
        use_starttls = smtp_port == 587
    else:
        use_starttls = starttls_env.strip().lower() in {"1", "true", "yes", "on"}

    return smtp_host, smtp_port, smtp_timeout, smtp_user, smtp_pass, smtp_from, use_starttls


def _send_email(to_email: str, subject: str, body: str) -> None:
    smtp_host, smtp_port, smtp_timeout, smtp_user, smtp_pass, smtp_from, use_starttls = _get_smtp_config()

    logger.info("Email sending started: to=%s host=%s port=%s", to_email, smtp_host, smtp_port)

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = smtp_from
    msg["To"] = to_email
    msg.set_content(body)

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=smtp_timeout) as server:
            server.ehlo()
            if use_starttls:
                server.starttls(context=ssl.create_default_context())
                server.ehlo()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
        logger.info("Email sending success: to=%s", to_email)
    except Exception as exc:
        logger.exception("Email sending failed: to=%s host=%s port=%s error=%s", to_email, smtp_host, smtp_port, str(exc))
        raise RuntimeError(f"Email send failed: {str(exc)}") from exc


def send_otp_email(to_email: str, otp: str) -> None:
    """
    Sends a plain-text OTP email via SMTP.
    Raises an exception if sending fails.
    """

    _send_email(
        to_email=to_email,
        subject="Your AUB Rate verification code",
        body=f"""Your verification code is: {otp}

This code expires in 10 minutes.
If you didn’t request this, ignore this email.
"""
    )


def send_password_reset_otp_email(to_email: str, otp: str) -> None:
    """
    Sends a plain-text password reset OTP email via SMTP.
    """

    _send_email(
        to_email=to_email,
        subject="Your password reset code",
        body=f"""Your password reset code is: {otp}

This code expires in 10 minutes.
If you didn’t request this, ignore this email.
"""
    )
