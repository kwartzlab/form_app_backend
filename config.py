import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Configuration - Set these as environment variables in Railway
    SLACK_WEBHOOK_URL = os.environ.get('SLACK_WEBHOOK_URL')
    SMTP_SERVER = os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
    SMTP_PORT = int(os.environ.get('SMTP_PORT', '587'))
    EMAIL_ADDRESS = os.environ.get('EMAIL_ADDRESS')
    EMAIL_PASSWORD = os.environ.get('EMAIL_PASSWORD')
    RECIPIENT_EMAIL = os.environ.get('RECIPIENT_EMAIL')
    GOOGLE_SHEET_NAME = os.environ.get('GOOGLE_SHEET_NAME')
    HCAPTCHA_SECRET_KEY = os.environ.get('CAPTCHA_SECRET')