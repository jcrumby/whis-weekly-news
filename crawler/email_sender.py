import os
import smtplib
import jinja2
import json
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import date
from dotenv import load_dotenv

# Load credentials from .env
load_dotenv()

SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
EMAIL_TO = [email.strip() for email in os.getenv("EMAIL_TO", "").split(",") if email.strip()]

def send_json_email(summary_json: dict):
    # Load Jinja2 template
    template_loader = jinja2.FileSystemLoader(searchpath=".")
    template_env = jinja2.Environment(loader=template_loader)
    template = template_env.get_template("email_template.html")

    # Render template with summary_json
    full_html = template.render(summary=summary_json)

    # Build multipart email
    msg = MIMEMultipart("alternative")
    today = date.today().strftime("%B %d, %Y")
    msg['Subject'] = f"FemTech News - {today}"
    msg['From'] = EMAIL_USER
    msg['To'] = ", ".join(EMAIL_TO)

    # Attach HTML version only
    msg.attach(MIMEText(full_html, "html"))

    # Send email
    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as smtp:
            smtp.starttls()
            smtp.login(EMAIL_USER, EMAIL_PASSWORD)
            smtp.send_message(msg)
        print(f"✅ Email sent to {msg['To']} with subject: {msg['Subject']}")
    except Exception as e:
        print(f"❌ Failed to send email: {e}")