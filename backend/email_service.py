"""
Email service — Gmail SMTP.
Handles OTP verification emails and full HTML+PDF report emails.
"""
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import settings
from logger import get_logger, log_action

logger = get_logger("email_service")


def _send_via_gmail(to_email: str, subject: str, html_body: str,
                    pdf_bytes: bytes = None, pdf_filename: str = None) -> bool:
    """Core Gmail SMTP sender. Attaches PDF if provided."""
    if not settings.GMAIL_APP_PASSWORD:
        log_action(logger, "warning", "email_service", "SMTP_SKIPPED",
                   "GMAIL_APP_PASSWORD not configured")
        return False
    try:
        msg = MIMEMultipart("mixed")
        msg["From"] = f"AI Loan Advisor <{settings.GMAIL_SENDER}>"
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        if pdf_bytes and pdf_filename:
            part = MIMEApplication(pdf_bytes, _subtype="pdf")
            part.add_header("Content-Disposition", "attachment", filename=pdf_filename)
            msg.attach(part)

        ctx = ssl.create_default_context()
        with smtplib.SMTP("smtp.gmail.com", 587) as srv:
            srv.ehlo()
            srv.starttls(context=ctx)
            srv.login(settings.GMAIL_SENDER, settings.GMAIL_APP_PASSWORD)
            srv.sendmail(settings.GMAIL_SENDER, to_email, msg.as_string())

        log_action(logger, "info", "email_service", "EMAIL_SENT",
                   f"to={to_email} | subject={subject[:60]}")
        return True
    except Exception as e:
        log_action(logger, "error", "email_service", "EMAIL_FAILED",
                   f"to={to_email} | error={str(e)}")
        return False


# ─── OTP Email ────────────────────────────────────────────────────────────────
def send_otp_email(to_email: str, otp: str, full_name: str) -> bool:
    """Send a styled OTP verification email."""
    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="font-family:'Segoe UI',Arial,sans-serif;background:#0f0f1a;margin:0;padding:20px;">
<div style="max-width:480px;margin:0 auto;background:linear-gradient(135deg,#1a1a2e,#16213e);
     border-radius:16px;overflow:hidden;border:1px solid rgba(99,102,241,0.3);">
  <div style="background:linear-gradient(135deg,#6366f1,#a855f7);padding:28px 32px;text-align:center;">
    <div style="font-size:2.5rem;">🏦</div>
    <h1 style="color:#fff;margin:8px 0 4px;font-size:1.4rem;">AI Loan &amp; Credit Advisor</h1>
    <p style="color:rgba(255,255,255,0.8);margin:0;font-size:0.85rem;">Email Verification</p>
  </div>
  <div style="padding:32px;">
    <p style="color:#e0e7ff;font-size:1rem;margin-bottom:8px;">Hi {full_name},</p>
    <p style="color:rgba(199,210,254,0.8);font-size:0.9rem;line-height:1.6;">
      Welcome! Use the code below to verify your email address and activate your account.
    </p>
    <div style="background:rgba(99,102,241,0.15);border:2px solid rgba(99,102,241,0.4);
         border-radius:12px;padding:24px;text-align:center;margin:24px 0;">
      <p style="color:rgba(199,210,254,0.7);font-size:0.8rem;margin:0 0 8px;
         text-transform:uppercase;letter-spacing:0.1em;">Verification Code</p>
      <div style="font-size:2.8rem;font-weight:800;letter-spacing:0.35em;
           color:#a5b4fc;font-family:monospace;">{otp}</div>
      <p style="color:rgba(199,210,254,0.5);font-size:0.75rem;margin:8px 0 0;">
        Valid for <strong>10 minutes</strong>
      </p>
    </div>
    <p style="color:rgba(199,210,254,0.45);font-size:0.78rem;line-height:1.5;">
      If you didn't sign up, you can safely ignore this email.
    </p>
  </div>
  <div style="padding:14px 32px;border-top:1px solid rgba(255,255,255,0.07);text-align:center;">
    <p style="color:rgba(199,210,254,0.25);font-size:0.7rem;margin:0;">
      AI Loan &amp; Credit Advisor · Secure Banking Intelligence
    </p>
  </div>
</div>
</body></html>"""
    return _send_via_gmail(to_email, "🔐 Verify your email — AI Loan Advisor", html)


# ─── Report Email ─────────────────────────────────────────────────────────────
def send_report_email(to_email: str, full_name: str, subject: str,
                      html_body: str, pdf_bytes: bytes = None,
                      pdf_filename: str = None) -> bool:
    """Send report email with optional PDF attachment."""
    return _send_via_gmail(to_email, subject, html_body, pdf_bytes, pdf_filename)
