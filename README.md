# Reimbursement Form Backend

Flask backend for Kwartzlab's reimbursement request and purchase approval forms. Handles form submissions, file uploads to Google Drive, writes to Google Sheets, and sends notifications via email and Slack.

## Features

- Two form types: Reimbursement Request and Purchase Approval
- File upload to Google Drive with organization-restricted permissions
- Automatic ID generation with race condition handling
- Email notifications (dual emails: list notification + submitter acknowledgment)
- Slack notifications for Purchase Approvals
- hCaptcha verification
- Rate limiting (production only)
- Input validation and sanitization

## Prerequisites

- Python 3.8+
- Google Cloud Project with:
  - Google Sheets API enabled
  - Google Drive API enabled
  - Service Account created with credentials
- Google Workspace account with:
  - Shared Drive access (service accounts have no storage quota)
  - Google Sheets for storing submissions
  - Folders in Shared Drive for file storage
- Slack workspace (for Purchase Approval notifications)
- Gmail or SMTP server (for email notifications)
- hCaptcha account

## Local Development Setup

### 1. Clone and Install Dependencies

```bash
# Clone the repository
git clone <repository-url>
cd backend

# Create virtual environment
python -m venv venv

# Activate virtual environment
# On macOS/Linux:
source venv/bin/activate
# On Windows:
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Set Up Google Service Account

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing one
3. Enable Google Sheets API and Google Drive API
4. Create a Service Account:
   - Go to IAM & Admin → Service Accounts
   - Create Service Account
   - Download JSON credentials
5. Save the credentials file as `credentials.json` in the project root
6. Add the service account email to your Google Shared Drive:
   - Open your Shared Drive in Google Drive
   - Right-click → Manage members
   - Add the service account email with "Content Manager" or "Manager" role
7. The service account will automatically have access to sheets and folders within the Shared Drive

### 3. Create Google Sheets

Create two Google Sheets in your Shared Drive:

**Reimbursement Request Sheet - Columns:**
- ID | Timestamp | First Name | Last Name | Email | Approval/Project | Vendor | Description | Amount | HST | File Links | Comments

**Purchase Approval Sheet - Columns:**
- ID | Timestamp | First Name | Last Name | Email | Vendor | Description | Amount | File Links | Comments

Note the Sheet names and IDs from the URLs.

### 4. Create Google Drive Folders

Create two folders in your Shared Drive:
1. Reimbursement Request Files
2. Purchase Approval Files

Note the folder IDs from the URLs (the long string after `/folders/` in the browser).

### 5. Configure Environment Variables

Create a `.env` file in the project root:

```bash
# Flask Configuration
FLASK_ENV=development

# hCaptcha
CAPTCHA_SECRET=your_hcaptcha_secret_key

# Email Configuration
# Production email addresses (used when FLASK_ENV != development)
OUTBOUND_EMAIL_ADDRESS=treasurer@kwartzlab.ca
RR_RECIPIENT_EMAIL=reimbursements@kwartzlab.ca
PA_RECIPIENT_EMAIL=purchase-approvals@kwartzlab.ca

# Development email addresses (used when FLASK_ENV = development)
DEV_OUTBOUND_EMAIL_ADDRESS=your_dev_email@gmail.com
DEV_RECIPIENT_EMAIL=your_dev_email@gmail.com

# Email server settings
EMAIL_PASSWORD=your_app_specific_password
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587

# Google Sheets
RR_SHEET_NAME=Reimbursement Requests
PA_SHEET_NAME=Purchase Approvals

# Google Drive Folders
RR_GOOGLE_DRIVE_FOLDER_ID=your_rr_folder_id
PA_GOOGLE_DRIVE_FOLDER_ID=your_pa_folder_id

# Organization Domain (for file permissions)
ORGANIZATION_DOMAIN=kwartzlab.ca

# Slack (optional, only for Purchase Approvals)
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL

# Google Credentials (leave empty for local dev, uses credentials.json)
# GOOGLE_SHEETS_CREDENTIALS=
```

**Important Notes:**
- For Gmail, use an [App Password](https://support.google.com/accounts/answer/185833), not your regular password
- `credentials.json` is used for local development (don't commit this file!)
- In production, credentials will be in `GOOGLE_SHEETS_CREDENTIALS` environment variable
- Set `FLASK_ENV=development` to:
  - Disable rate limiting during development
  - Use DEV_OUTBOUND_EMAIL_ADDRESS and DEV_RECIPIENT_EMAIL (all emails go to your dev address)
- In production, omit `FLASK_ENV` or set to `production` to:
  - Enable rate limiting
  - Use OUTBOUND_EMAIL_ADDRESS and separate recipient lists (RR_RECIPIENT_EMAIL, PA_RECIPIENT_EMAIL)

### 6. Run the Application

```bash
# Make sure virtual environment is activated
python app.py

# Server will start on http://localhost:5000
```

### 7. Test the Endpoints

**Health Check:**
```bash
curl http://localhost:5000/health
```

**Submit Reimbursement Request:**
```bash
curl -X POST http://localhost:5000/submit \
  -F "firstName=John" \
  -F "lastName=Doe" \
  -F "email=john@example.com" \
  -F "comments=Test submission" \
  -F "expenses=[{\"id\":1,\"approval\":\"Test\",\"vendor\":\"TestCo\",\"description\":\"Test item\",\"amount\":\"10.00\",\"hst\":\"HST included in amount\"}]" \
  -F "captchaToken=test_token" \
  -F "file0=@/path/to/test.pdf"
```

**Submit Purchase Approval:**
```bash
curl -X POST http://localhost:5000/submit-PA \
  -F "firstName=Jane" \
  -F "lastName=Smith" \
  -F "email=jane@example.com" \
  -F "comments=Test PA" \
  -F "expenses=[{\"id\":1,\"vendor\":\"TestCo\",\"description\":\"Test item\",\"amount\":\"50.00\"}]" \
  -F "captchaToken=test_token" \
  -F "file0=@/path/to/test.pdf"
```

## Project Structure

```
backend/
├── app.py                 # Main Flask application
├── config.py              # Configuration from environment variables
├── requirements.txt       # Python dependencies
├── credentials.json       # Google service account (local only, gitignored)
├── .env                   # Environment variables (gitignored)
├── services/              # Service modules
│   ├── __init__.py
│   ├── google_auth.py     # Google API authentication
│   ├── google_sheets.py   # Google Sheets operations
│   ├── google_drive.py    # Google Drive file uploads
│   ├── notifications.py   # Email and Slack notifications
│   ├── validation.py      # Input validation and sanitization
│   └── utils.py           # Utility functions (profiling decorator)
└── templates/             # Email HTML template
    └── email_template.html  # Unified template for all emails
```

## Key Features Explained

### Race Condition Handling
The system generates sequential IDs. To prevent duplicate IDs when multiple submissions occur simultaneously:
1. Generate next ID based on last entry
2. Upload files
3. Check if ID is still unused (right before writing)
4. If duplicate detected, clean up files and retry with exponential backoff (max 5 attempts)

### File Storage
- Files uploaded to Google Drive Shared Drive (service accounts have no storage)
- Each submission gets its own subfolder (named by submission ID)
- Files restricted to organization domain members
- Links (not attachments) sent in emails to avoid size limits

### Email Strategy
Two emails sent per submission:
1. **List notification** - Full details to the appropriate mailing list:
   - Reimbursement Requests → RR_RECIPIENT_EMAIL
   - Purchase Approvals → PA_RECIPIENT_EMAIL
2. **Acknowledgment** - Thank you email to submitter with submission copy

In development mode (`FLASK_ENV=development`), all emails are sent to DEV_RECIPIENT_EMAIL instead of production mailing lists.

### Validation
Backend validates and sanitizes all inputs:
- File types (PDF, images, spreadsheets, documents)
- File sizes (10MB per file, 50MB total)
- Text field lengths
- Email format
- Amount values (positive numbers, max $1M)
- HTML tag removal from all text inputs

### Rate Limiting
- Disabled in development (`FLASK_ENV=development`)
- Enabled in production (10 submissions/hour per IP)
- Uses `X-Forwarded-For` header from Cloud Run proxy

## Development Tips

### Enable Request Profiling
The `@log_execution_time` decorator is available in `services/utils.py` and can be applied to any function to measure execution time:

```python
from services.utils import log_execution_time

@log_execution_time
def your_function():
    # Function execution time will be printed to console
    pass
```

This decorator is already applied to key functions in `app.py`, `notifications.py`, and other service modules.

```python
from services.utils import log_execution_time

@log_execution_time
def your_function():
    # Function execution time will be printed to console
    pass
```

### Testing Without hCaptcha
In development, you can temporarily bypass captcha by modifying `verify_hcaptcha()` in `app.py`:
```python
def verify_hcaptcha(token):
    if Config.FLASK_ENV == 'development':
        return True  # Skip verification in dev
    # ... rest of function
```

### Viewing Google Sheets Client Cache
The sheets client is cached globally. To clear it during development, restart the Flask server.

## Security Notes

- **Never commit** `credentials.json` or `.env` files
- `.gitignore` is configured to exclude sensitive files
- All user input is sanitized before storage
- Files are validated for type and size on backend (don't trust frontend)
- Service account has minimum required permissions

## Common Issues

**"Missing required environment variables"**
- Check that `.env` file exists and contains all required variables
- Ensure `.env` is in the same directory as `app.py`
- In development, verify you have DEV_OUTBOUND_EMAIL_ADDRESS and DEV_RECIPIENT_EMAIL set
- In production, verify you have OUTBOUND_EMAIL_ADDRESS, RR_RECIPIENT_EMAIL, and PA_RECIPIENT_EMAIL set

**"Error accessing Google Sheet"**
- Verify service account email has access to the sheets
- Check sheet names match exactly (case-sensitive)
- Ensure Google Sheets API is enabled in your project

**"Error uploading to Google Drive"**
- Verify service account has access to the Shared Drive folders
- Check folder IDs are correct
- Ensure Google Drive API is enabled

**"Email failed to send"**
- For Gmail, use App Password, not regular password
- Check SMTP settings are correct
- In development, verify DEV_OUTBOUND_EMAIL_ADDRESS and EMAIL_PASSWORD are correct
- In production, verify OUTBOUND_EMAIL_ADDRESS and EMAIL_PASSWORD are correct
- Ensure the sender email has appropriate permissions

**Rate limiting during development**
- Set `FLASK_ENV=development` in `.env` to disable rate limiting

**Emails going to wrong recipients in development**
- Verify `FLASK_ENV=development` is set in `.env`
- Check that DEV_RECIPIENT_EMAIL is configured correctly
- All emails (both list and acknowledgment) will go to DEV_RECIPIENT_EMAIL in development mode

## Next Steps

After local development is working:
1. Test all integrations end-to-end
2. Verify email templates render correctly
3. Test with frontend application
4. Prepare for deployment (see deployment section - to be added)
