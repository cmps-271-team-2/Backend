import os
import smtplib
from email.message import EmailMessage


def send_otp_email(to_email: str, otp: str) -> None:
    """
    Sends a plain-text OTP email via SMTP.
    Raises an exception if sending fails.
    """

    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")
    smtp_from = os.getenv("SMTP_FROM", smtp_user)

    if not all([smtp_host, smtp_user, smtp_pass, smtp_from]):
        raise RuntimeError("Missing SMTP env vars. Check backend/.env")

    msg = EmailMessage()
    msg["Subject"] = "Your AUB Rate verification code"
    msg["From"] = smtp_from
    msg["To"] = to_email

    msg.set_content(
        f"""Your verification code is: {otp}

This code expires in 10 minutes.
If you didn’t request this, ignore this email.
"""
    )

    # Connect using TLS (secure)
    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.send_message(msg)