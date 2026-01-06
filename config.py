import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Configuration - Set these as environment variables in Railway
    FLASK_ENV = os.environ.get('FLASK_ENV', 'production')
    SLACK_WEBHOOK_URL = os.environ.get('SLACK_WEBHOOK_URL')
    SMTP_SERVER = os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
    SMTP_PORT = int(os.environ.get('SMTP_PORT', '587'))
    OUTBOUND_EMAIL_ADDRESS = os.environ.get('OUTBOUND_EMAIL_ADDRESS')
    DEV_OUTBOUND_EMAIL_ADDRESS = os.environ.get('DEV_OUTBOUND_EMAIL_ADDRESS')
    EMAIL_PASSWORD = os.environ.get('EMAIL_PASSWORD')
    RECIPIENT_EMAIL = os.environ.get('RECIPIENT_EMAIL')
    GOOGLE_SHEET_NAME = {
        "Reimbursement Request": os.environ.get('RR_SHEET_NAME'),
        "Purchase Approval": os.environ.get('PA_SHEET_NAME')
    }
    GOOGLE_WORKSHEET_NAME = {
        "Reimbursement Request": os.environ.get('RR_WORKSHEET_NAME'),
        "Purchase Approval": os.environ.get('PA_WORKSHEET_NAME')
    }
    HCAPTCHA_SECRET_KEY = os.environ.get('CAPTCHA_SECRET')
    GOOGLE_DRIVE_FOLDER = {
        "Reimbursement Request": os.environ.get('RR_GOOGLE_DRIVE_FOLDER_ID'),
        "Purchase Approval": os.environ.get('PA_GOOGLE_DRIVE_FOLDER_ID'),
    }
    ORGANIZATION_DOMAIN = os.environ.get('ORGANIZATION_DOMAIN'),
    RECIPIENT_EMAIL = {
        "Reimbursement Request": os.environ.get('RR_RECIPIENT_EMAIL'),
        "Purchase Approval": os.environ.get('PA_RECIPIENT_EMAIL')
    }
    DEV_RECIPIENT_EMAIL = os.environ.get('DEV_RECIPIENT_EMAIL')