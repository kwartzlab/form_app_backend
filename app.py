from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import json
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import requests
from dotenv import load_dotenv
import math
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import io


app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

load_dotenv()  # Load environment variables from .env file

# Configuration - Set these as environment variables in Railway
SLACK_WEBHOOK_URL = os.environ.get('SLACK_WEBHOOK_URL')
SMTP_SERVER = os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
SMTP_PORT = int(os.environ.get('SMTP_PORT', '587'))
EMAIL_ADDRESS = os.environ.get('EMAIL_ADDRESS')
EMAIL_PASSWORD = os.environ.get('EMAIL_PASSWORD')
RECIPIENT_EMAIL = os.environ.get('RECIPIENT_EMAIL')
GOOGLE_SHEET_NAME = os.environ.get('GOOGLE_SHEET_NAME')

def setup_google_sheets():
    """Initialize Google Sheets API connection"""
    scope = ['https://spreadsheets.google.com/feeds',
             'https://www.googleapis.com/auth/drive']
    
    # Load credentials from environment variable (JSON string)
    #original
    """
    creds_json = os.environ.get('GOOGLE_SHEETS_CREDENTIALS')
    if not creds_json:
        print("Warning: GOOGLE_SHEETS_CREDENTIALS not set")
        return None
    
    creds_dict = json.loads(creds_json)
    credentials = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(credentials)
    return client"""

    #new
    creds_json = os.environ.get('GOOGLE_SHEETS_CREDENTIALS')
    if creds_json:
        creds_dict = json.loads(creds_json)
        credentials = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    else:
        # Load from credentials.json file (for local testing)
        credentials = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
    
    client = gspread.authorize(credentials)
    return client

def get_next_id_from_google_sheet():
    try:
        client = setup_google_sheets()
        if not client:
            return (datetime.now().year * 10000 + 1)
        
        sheet = client.open(GOOGLE_SHEET_NAME).sheet1   
        # get last index
        numRows = len(sheet.col_values(1))
        lastId = sheet.cell(numRows, 1).value
        #print(lastId)
        newId = 0
        try:
            lastId_num = int(lastId)
            #print("last id is valid")
            id_year = math.floor(lastId_num/10000)
            #print(id_year)
            id_index = lastId_num - (id_year * 10000)
            #print(id_index)
            current_year = datetime.now().year
            if id_year < current_year:
                newId = (current_year * 10000) + 1
            else:
                newId = (current_year * 10000) + id_index + 1 
        except ValueError:
            #print("last id is invalid")
            newId = (datetime.now().year * 10000) + 1
        return newId
    except Exception as e:
        print(f"Error accessing google sheet: {e}")
        return (datetime.now().year * 10000 + 1)

def add_to_google_sheet(data, file_links):
    """Add reimbursement data to Google Sheet"""
    try:
        client = setup_google_sheets()
        if not client:
            return False
        
        sheet = client.open(GOOGLE_SHEET_NAME).sheet1       #todo: add additional error handling if this fails. Create new sheet with specified name, or just return error and exit as currently?
        
        # Prepare row data
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        expenses = json.loads(data['expenses'])
        
        # Calculate total
        total = sum(float(exp.get('amount', 0) or 0) for exp in expenses)

        # Format file links
        file_links_str = ', '.join(file_links) if file_links else 'No attachments'
        
        # Add each expense as a separate row
        for expense in expenses:
            row = [
                data['id'],
                timestamp,
                data['firstName'],
                data['lastName'],
                data['email'],
                expense.get('approval', ''),
                expense.get('vendor', ''),
                expense.get('description', ''),
                expense.get('amount', ''),
                expense.get('hst', ''),
                data.get('comments', ''),
                file_links_str  # Add file links column
            ]
            sheet.append_row(row)
        
        return True
    except Exception as e:
        print(f"Error adding to Google Sheet: {e}")
        return False

def upload_to_google_drive(file_data, filename, request_id, parent_folder_id=None):
    """Upload file to Google Drive in a request-specific subfolder and return shareable link"""
    try:
        # Use same credentials as Google Sheets
        scope = ['https://spreadsheets.google.com/feeds',
                 'https://www.googleapis.com/auth/drive']
        
        creds_json = os.environ.get('GOOGLE_SHEETS_CREDENTIALS')
        if creds_json:
            creds_dict = json.loads(creds_json)
            credentials = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        else:
            credentials = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
        
        # Build Drive API service
        service = build('drive', 'v3', credentials=credentials)

        # Use Shared Drive
        supports_all_drives = {'supportsAllDrives': True}
        
        # Create or find the request-specific folder
        folder_metadata = {
            'name': request_id,
            'mimeType': 'application/vnd.google-apps.folder'
        }
        
        # If parent_folder_id is specified, create subfolder inside it
        if parent_folder_id:
            folder_metadata['parents'] = [parent_folder_id]
        
        # Check if folder already exists (in case multiple files in same request)
        query = f"name='{request_id}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
        if parent_folder_id:
            query += f" and '{parent_folder_id}' in parents"
        
        results = service.files().list(
            q=query, 
            fields='files(id)',
            **supports_all_drives,
            includeItemsFromAllDrives=True
        ).execute()
        folders = results.get('files', [])
        
        if folders:
            # Folder already exists, use it
            folder_id = folders[0]['id']
        else:
            # Create new folder
            folder = service.files().create(
                body=folder_metadata, 
                fields='id',
                **supports_all_drives
            ).execute()
            folder_id = folder.get('id')
            
            # Make folder accessible to organisation members
            permission = {
                'type': 'domain',
                'role': 'reader',
                'domain': 'kwartzlab.ca'
            }
            try:
                service.permissions().create(
                    fileId=folder_id,
                    body=permission,
                    **supports_all_drives
                ).execute()
            except Exception as e:
                print(f"Error editing folder permissions: {e}")
        
        # Prepare file metadata (upload into the request folder)
        file_metadata = {
            'name': filename,
            'parents': [folder_id]
        }
        
        # Create media upload
        media = MediaIoBaseUpload(
            io.BytesIO(file_data.read()),
            mimetype=file_data.content_type or 'application/octet-stream',
            resumable=True
        )
        
        # Upload file
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, webViewLink',
                **supports_all_drives
        ).execute()
        
        # Make file accessible to organisation members
        permission = {
            'type': 'domain',
            'role': 'reader',
            'domain': 'kwartzlab.ca'
        }
        try:
            service.permissions().create(
                fileId=file.get('id'),
                body=permission,
                **supports_all_drives
            ).execute()
        except Exception as e:
            print(f"Error editing file permissions: {e}")
        
        return file.get('webViewLink')
        
    except Exception as e:
        print(f"Error uploading to Google Drive: {e}")
        return None

def send_slack_notification(data, file_links):
    """Send notification to Slack with file links"""
    try:
        if not SLACK_WEBHOOK_URL:
            print("Warning: SLACK_WEBHOOK_URL not set")
            return False
        
        expenses = json.loads(data['expenses'])
        total = sum(float(exp.get('amount', 0) or 0) for exp in expenses)
        
        # Format expenses for Slack
        expense_lines = []
        for exp in expenses:
            expense_lines.append(
                f"• {exp.get('description', 'N/A')} - ${exp.get('amount', '0')} ({exp.get('hst', 'N/A')})"
            )
        
        message = {
            "text": "New Reimbursement Request",
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "💰 New Reimbursement Request"
                    }
                },
                {
                    "type": "section",
                    "fields": [
                        {
                            "type": "mrkdwn",
                            "text": f"*Name:*\n{data['firstName']} {data['lastName']}"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Email:*\n{data['email']}"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Total Amount:*\n${total:.2f}"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Date:*\n{datetime.now().strftime('%Y-%m-%d %H:%M')}"
                        }
                    ]
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Expenses:*\n" + "\n".join(expense_lines)
                    }
                }
            ]
        }
        
        if data.get('comments'):
            message["blocks"].append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Comments:*\n{data['comments']}"
                }
            })
        
        # Add file links
        if file_links:
            file_links_formatted = '\n'.join([f"• <{link}|View File>" for link in file_links])
            message["blocks"].append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Attached Files:*\n{file_links_formatted}"
                }
            })
        
        response = requests.post(SLACK_WEBHOOK_URL, json=message)
        return response.status_code == 200
    except Exception as e:
        print(f"Error sending Slack notification: {e}")
        return False

def send_email_notification(data, file_links):
    """Send email notification with file links instead of attachments"""
    try:
        if not all([EMAIL_ADDRESS, EMAIL_PASSWORD, RECIPIENT_EMAIL]):
            print("Warning: Email credentials not fully configured")
            return False
        
        msg = MIMEMultipart()
        msg['From'] = EMAIL_ADDRESS
        msg['To'] = RECIPIENT_EMAIL
        msg['Subject'] = f"New Reimbursement Request - {data['firstName']} {data['lastName']}"
        
        # Email body
        expenses = json.loads(data['expenses'])
        total = sum(float(exp.get('amount', 0) or 0) for exp in expenses)
        
        body = f"""
New reimbursement request submitted:

Submitted by: {data['firstName']} {data['lastName']}
Email: {data['email']}
Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

EXPENSES:
"""
        for i, exp in enumerate(expenses, 1):
            body += f"""
{i}. Approval/Project: {exp.get('approval', 'N/A')}
   Vendor: {exp.get('vendor', 'N/A')}
   Description: {exp.get('description', 'N/A')}
   Amount: ${exp.get('amount', '0')}
   HST: {exp.get('hst', 'N/A')}
"""
        
        body += f"\nTOTAL: ${total:.2f}\n"
        
        if data.get('comments'):
            body += f"\nAdditional Comments:\n{data['comments']}\n"
        
        # Add file links
        if file_links:
            body += "\n\nATTACHED FILES:\n"
            for i, link in enumerate(file_links, 1):
                body += f"{i}. {link}\n"
        else:
            body += "\n\nNo files attached.\n"
        
        msg.attach(MIMEText(body, 'plain'))
        
        # Send email (no attachments)
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        server.send_message(msg)
        server.quit()
        
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False

@app.route('/submit', methods=['POST'])
def submit_reimbursement():
    """Handle reimbursement submission"""
    try:
        # Extract form data
        data = {
            'firstName': request.form.get('firstName'),
            'lastName': request.form.get('lastName'),
            'email': request.form.get('email'),
            'comments': request.form.get('comments', ''),
            'expenses': request.form.get('expenses')
        }
        
        # Validate required fields
        if not all([data['firstName'], data['lastName'], data['email'], data['expenses']]):
            return jsonify({'error': 'Missing required fields'}), 400
        
        #establish an ID for the submission
        nextId = get_next_id_from_google_sheet()
        data['id'] = nextId
        
        # Upload files to Google Drive
        file_links = []
        folder_id = os.environ.get('GOOGLE_DRIVE_FOLDER_ID')  # Optional: specific folder

        # In your submit endpoint, where you upload files:
        for key in request.files:
            file_data = request.files[key]
            if file_data.filename:
                link = upload_to_google_drive(
                    file_data, 
                    file_data.filename, 
                    request_id=nextId,
                    parent_folder_id=folder_id
                )
                if link:
                    file_links.append(link)

        # Process the submission with file links
        results = {
            'google_sheet': add_to_google_sheet(data, file_links),
            'slack': send_slack_notification(data, file_links),
            'email': send_email_notification(data, file_links),
            'files_uploaded': len(file_links)
        }
        
        # Check if at least one integration succeeded
        if any(results.values()):
            return jsonify({
                'message': 'Reimbursement request submitted successfully',
                'details': results
            }), 200
        else:
            return jsonify({
                'error': 'Failed to process submission',
                'details': results
            }), 500
            
    except Exception as e:
        print(f"Error processing submission: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'healthy'}), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)