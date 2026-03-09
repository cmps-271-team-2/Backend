import os
import logging
import resend


logger = logging.getLogger(__name__)


def _get_resend_config() -> tuple[str, str]:
    """
    Get Resend API configuration from environment variables.
    Returns: (api_key, from_email)
    """
    api_key = os.getenv("RESEND_API_KEY")
    from_email = os.getenv("RESEND_FROM_EMAIL")

    if not api_key:
        raise RuntimeError("Missing RESEND_API_KEY environment variable")
    if not from_email:
        raise RuntimeError("Missing RESEND_FROM_EMAIL environment variable")

    return api_key, from_email


def _send_email_resend(to_email: str, subject: str, body_text: str, body_html: str = None) -> None:
    """
    Send email using Resend API over HTTPS.
    Raises RuntimeError if sending fails.
    """
    api_key, from_email = _get_resend_config()
    
    logger.info("Email sending started: provider=Resend to=%s subject=%s", to_email, subject)
    
    # Configure Resend with API key
    resend.api_key = api_key
    
    try:
        # Prepare email parameters
        params = {
            "from": from_email,
            "to": [to_email],
            "subject": subject,
            "text": body_text,
        }
        
        # Add HTML body if provided
        if body_html:
            params["html"] = body_html
        
        # Send email via Resend API
        response = resend.Emails.send(params)
        
        logger.info("Email sending success: provider=Resend to=%s email_id=%s", to_email, response.get("id", "unknown"))
        
    except Exception as exc:
        logger.exception("Email sending failed: provider=Resend to=%s error=%s", to_email, str(exc))
        raise RuntimeError(f"Resend email send failed: {str(exc)}") from exc


def send_otp_email(to_email: str, otp: str) -> None:
    """
    Sends OTP email via Resend API over HTTPS.
    Raises an exception if sending fails.
    """
    subject = "Your Unitok OTP Code"
    
    # Plain text version
    body_text = f"""Your Unitok verification code is: {otp}

This code expires in 10 minutes.
If you didn't request this, please ignore this email.

- Unitok Team"""
    
    # HTML version for better presentation
    body_html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #8B5CF6;">Your Unitok Verification Code</h2>
        <p style="font-size: 16px; color: #333;">Your verification code is:</p>
        <div style="background-color: #F3F4F6; padding: 20px; border-radius: 8px; text-align: center; margin: 20px 0;">
            <span style="font-size: 32px; font-weight: bold; color: #8B5CF6; letter-spacing: 8px;">{otp}</span>
        </div>
        <p style="font-size: 14px; color: #666;">This code expires in 10 minutes.</p>
        <p style="font-size: 14px; color: #666;">If you didn't request this, please ignore this email.</p>
        <hr style="border: none; border-top: 1px solid #E5E7EB; margin: 30px 0;">
        <p style="font-size: 12px; color: #999;">- Unitok Team</p>
    </div>
    """
    
    _send_email_resend(to_email, subject, body_text, body_html)


def send_password_reset_otp_email(to_email: str, otp: str) -> None:
    """
    Sends password reset OTP email via Resend API over HTTPS.
    Raises an exception if sending fails.
    """
    subject = "Your Unitok Password Reset OTP"
    
    # Plain text version
    body_text = f"""Your Unitok password reset code is: {otp}

This code expires in 10 minutes.
If you didn't request this, please ignore this email and your password will remain unchanged.

- Unitok Team"""
    
    # HTML version for better presentation
    body_html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #8B5CF6;">Password Reset Request</h2>
        <p style="font-size: 16px; color: #333;">Your password reset code is:</p>
        <div style="background-color: #F3F4F6; padding: 20px; border-radius: 8px; text-align: center; margin: 20px 0;">
            <span style="font-size: 32px; font-weight: bold; color: #8B5CF6; letter-spacing: 8px;">{otp}</span>
        </div>
        <p style="font-size: 14px; color: #666;">This code expires in 10 minutes.</p>
        <p style="font-size: 14px; color: #666;">If you didn't request this, please ignore this email and your password will remain unchanged.</p>
        <hr style="border: none; border-top: 1px solid #E5E7EB; margin: 30px 0;">
        <p style="font-size: 12px; color: #999;">- Unitok Team</p>
    </div>
    """
    
    _send_email_resend(to_email, subject, body_text, body_html)
