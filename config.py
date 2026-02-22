import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    FLASK_ENV = os.environ.get('FLASK_ENV', 'production')
    HCAPTCHA_SECRET_KEY = os.environ.get('CAPTCHA_SECRET')
    SLACK_WEBHOOK_URL = os.environ.get('SLACK_WEBHOOK_URL')

    # email
    OUTBOUND_EMAIL_ADDRESS = os.environ.get('OUTBOUND_EMAIL_ADDRESS')
    RECIPIENT_EMAIL = {
        "Reimbursement Request": os.environ.get('RR_RECIPIENT_EMAIL'),
        "Purchase Approval": os.environ.get('PA_RECIPIENT_EMAIL')
    }
    DEV_OUTBOUND_EMAIL_ADDRESS = os.environ.get('DEV_OUTBOUND_EMAIL_ADDRESS')
    DEV_RECIPIENT_EMAIL = os.environ.get('DEV_RECIPIENT_EMAIL')

    EMAIL_PASSWORD = os.environ.get('EMAIL_PASSWORD')
    SMTP_SERVER = os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
    SMTP_PORT = int(os.environ.get('SMTP_PORT', '587'))
    
    # google sheets for data backend, google drive for file uploads
    GOOGLE_SHEET_ID = {
        "Reimbursement Request": os.environ.get('RR_SHEET_ID'),
        "Purchase Approval": os.environ.get('PA_SHEET_ID')
    }
    GOOGLE_WORKSHEET_NAME = {
        "Reimbursement Request": os.environ.get('RR_WORKSHEET_NAME'),
        "Purchase Approval": os.environ.get('PA_WORKSHEET_NAME')
    }
    GOOGLE_DRIVE_FOLDER = {
        "Reimbursement Request": os.environ.get('RR_GOOGLE_DRIVE_FOLDER_ID'),
        "Purchase Approval": os.environ.get('PA_GOOGLE_DRIVE_FOLDER_ID'),
    }
    ORGANIZATION_DOMAIN = os.environ.get('ORGANIZATION_DOMAIN'),
    
    