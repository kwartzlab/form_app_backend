from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import requests as req
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from config import Config
from services import get_next_id_from_google_sheet, add_to_google_sheet, send_email_notification, send_slack_notification
from services import upload_to_google_drive, delete_from_google_drive

def validate_config():
    """Check all required environment variables are set"""
    required = [
        'CAPTCHA_SECRET',
        'EMAIL_ADDRESS',
        'EMAIL_PASSWORD',
        'RECIPIENT_EMAIL',
        'RR_SHEET_NAME',
        'PA_SHEET_NAME'
    ]
    
    missing = [var for var in required if not os.environ.get(var)]
    
    if missing:
        # logger.error(f"Missing required environment variables: {missing}")    #TODO implement proper logging
        print("Missing environment variables")
        raise EnvironmentError(f"Missing: {', '.join(missing)}")

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)

def verify_hcaptcha(token):
    """Verify hCAPTCHA token"""
    try:
        response = req.post(
            'https://hcaptcha.com/siteverify',
            data={
                'secret': Config.HCAPTCHA_SECRET_KEY,
                'response': token
            },
            timeout=5
        )
        result = response.json()
        return result.get('success', False)
    except Exception as e:
        print(f"Error verifying hCAPTCHA: {e}")
        return False

def validate_input(endpoint, submissionReq):
    # currently no need to apply different validation to different form types since they have the same fields
    try:
        # Verify captcha first before doing anything else
        captcha_token = submissionReq.form.get('captchaToken')
        if not captcha_token:
            return [0, 'Captcha token missing', 400]
        
        if not verify_hcaptcha(captcha_token):
            return [0, 'Captcha verification failed. Please try again.', 400]

        # Extract form data
        data = {
            'firstName': submissionReq.form.get('firstName'),
            'lastName': submissionReq.form.get('lastName'),
            'email': submissionReq.form.get('email'),
            'comments': submissionReq.form.get('comments', ''),
            'expenses': submissionReq.form.get('expenses')
        }
        
        # Validate required fields
        if not all([data['firstName'], data['lastName'], data['email'], data['expenses']]):
            return [0, 'Missing required fields', 400]
        
        return [1, data]
    except Exception as e:
        print(f"Error processing submission: {e}")
        return [0, 'Internal server error', 500]

def sheets_and_receipts(data, files, endpoint):
    # Upload files to Google Drive
    file_links = []
    files = []
    folder_id = Config.GOOGLE_DRIVE_FOLDER[endpoint]

    uploadFailed = False
    for key in files:
        file_data = files[key]
        if file_data.filename:
            link, fid = upload_to_google_drive(file_data, file_data.filename, request_id=data["id"], parent_folder_id=folder_id)
            if link:
                files.append({'fid': fid, 'link': link})
            else:
                uploadFailed = True

    results = {}
    if uploadFailed:
        #delete files that were uploaded, then return error
        for file in files:
            delete_from_google_drive(file['fid'])
        print(f"Error processing submission: one or more file uploads failed")
        return [0, 'Server Error: failed to upload one or more files', 500]
    else:
        for file in files:
            file_links.append(file['link'])
        results['files_uploaded'] = {"len": len(file_links), "list": file_links}

    results['google_sheet'] = add_to_google_sheet(endpoint, data, file_links)

    if not results['google_sheet']:
        #delete files that were uploaded, then return error
        for file in files:
            delete_from_google_drive(file['fid'])
        print(f"Error processing submission: failed to record entry in google sheet")
        return [0, 'Server Error: failed to record entry in google sheet', 500]

    return [1, results]
    
def build_return_message(results, endpoint):
    message = endpoint + ' Submission Succeeded'
    if not results['slack'] or not results['email']:
        message = message + ', but one or more integrations failed. Please contact the treasurer'
    message = message + '.'
    return message

@app.route('/submit-PA', methods=['POST'])
@limiter.limit("10 per hour")  # Max 10 submissions per hour per IP
def submit_purchApproval():
    """Handle Purcahse Approval submission"""
    endpoint = 'Purchase Approval'
    try:
        result = validate_input(endpoint, request)
        if result[0] == 0:
            return jsonify({'error': result[1]}), result[2]
        else:
            data = result[1]

        # establish an ID for the submission, needed for file upload folder name as well as sheet entries
        data['id'] = get_next_id_from_google_sheet(endpoint) 
        if data['id'] == 0:
            print(f"Error processing submission: could not access google sheet")
            return jsonify({'error': 'Server Error: failed to access spreadsheet'}), 500
        
        # core integrations are file upload and google sheets, do those first
        sheet_result = sheets_and_receipts(data, request.files, endpoint)
        if sheet_result[0] == 0:
            return jsonify({'error': sheet_result[1]}), sheet_result[2]
        else:
            results = sheet_result[1]
            file_links = results["files_uploaded"]["list"]

        # If we haven't returned before this point, submission is successful. Try to run slack and email integrations
        results['slack'] = send_slack_notification(data, file_links)
        results['email'] = send_email_notification(endpoint, data, file_links)
        
        message = build_return_message(results, endpoint)

        return jsonify({
            'message': message,
            'details': results
        }), 200

    except Exception as e:
        print(f"Error processing Purchase Approval submission: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/submit', methods=['POST'])
@limiter.limit("10 per hour")  # Max 10 submissions per hour per IP
def submit_reimbursement():
    """Handle reimbursement submission"""
    endpoint = 'Reimbursement Request'
    try:
        result = validate_input(endpoint, request)
        if result[0] == 0:
            return jsonify({'error': result[1]}), result[2]
        else:
            data = result[1]
        
        # establish an ID for the submission, needed for file upload folder name as well as sheet entries
        data['id'] = get_next_id_from_google_sheet(endpoint) 
        if data['id'] == 0:
            print(f"Error processing submission: could not access google sheet")
            return jsonify({'error': 'Server Error: failed to access spreadsheet'}), 500

        # core integrations are file upload and google sheets, do those first
        sheet_result = sheets_and_receipts(data, request.files, endpoint)
        print(sheet_result)
        if sheet_result[0] == 0:
            print("sheet access or file upload failed")
            return jsonify({'error': sheet_result[1]}), sheet_result[2]
        else:
            results = sheet_result[1]
            file_links = results["files_uploaded"]["list"]

        # If we haven't returned before this point, submission is successful. Try to run slack and email integrations
        results['slack'] = True         #we currently only bother sending PAs to a channel
        results['email'] = send_email_notification(endpoint, data, file_links)
        
        message = build_return_message(results, endpoint)

        return jsonify({
            'message': message,
            'details': results
        }), 200
                
    except Exception as e:
        print(f"Error processing Reimbursement Request submission: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'healthy'}), 200

if __name__ == '__main__':
    validate_config()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)