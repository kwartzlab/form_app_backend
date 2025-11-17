from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix
import os
import requests as req
import random
import time
import json
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from config import Config
from services import get_next_id_from_google_sheet, add_to_google_sheet, \
        is_id_unused, send_email_notification, send_slack_notification, \
        upload_to_google_drive, delete_from_google_drive, \
        validate_form_data, validate_file, validate_total_file_size

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
        #TODO implement proper logging
        # logger.error(f"Missing required environment variables: {missing}")    
        print("Missing environment variables")
        raise EnvironmentError(f"Missing: {', '.join(missing)}")

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Add ProxyFix to properly handle X-Forwarded-For headers from Cloud Run
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

MAX_RETRIES = 5

# Only enable rate limiting in production
if Config.FLASK_ENV != 'development':
    limiter = Limiter(
        app=app,
        key_func=get_remote_address,
        default_limits=["200 per day", "50 per hour"]
    )
else:
    # Create a disabled limiter for development
    limiter = Limiter(
        app=app,
        key_func=get_remote_address,
        default_limits=[]
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

def validate_and_extract_input(endpoint, submissionReq):
    """
    Validate captcha, extract form data, validate files, and sanitize all inputs
    Returns: [status, data/error_message, http_code]
    """
    try:
        # Verify captcha first before doing anything else
        captcha_token = submissionReq.form.get('captchaToken')
        if not captcha_token:
            return [0, 'Captcha token missing', 400]
        
        if not verify_hcaptcha(captcha_token):
            return [0, 'Captcha verification failed. Please try again.', 400]

        # Extract form data
        raw_data = {
            'firstName': submissionReq.form.get('firstName'),
            'lastName': submissionReq.form.get('lastName'),
            'email': submissionReq.form.get('email'),
            'comments': submissionReq.form.get('comments', ''),
            'expenses': submissionReq.form.get('expenses')
        }

        # Parse expenses JSON
        try:
            if raw_data['expenses']:
                raw_data['expenses'] = json.loads(raw_data['expenses'])
            else:
                return [0, 'No expenses provided', 400]
        except json.JSONDecodeError:
            return [0, 'Invalid expenses data format', 400]

        # Validate and sanitize form data
        valid, error_or_data, sanitized_data = validate_form_data(endpoint, raw_data)
        if not valid:
            return [0, error_or_data, 400]
        
        # Validate total file size
        if submissionReq.files:
            valid, error = validate_total_file_size(submissionReq.files)
            if not valid:
                return [0, error, 400]
        
        return [1, sanitized_data]
        
    except Exception as e:
        print(f"Error processing submission: {e}")
        return [0, 'Internal server error', 500]
    
def build_return_message(results, endpoint):
    message = endpoint + ' Submission Succeeded'
    if not results['slack'] or not results['email']:
        message = message + ', but one or more integrations failed. Please contact the treasurer'
    message = message + '.'
    return message

def core_submission(data, files, endpoint):
    """
    Process a submission: generate ID, validate and upload files, write to sheet
    Returns: [status, data/error, http_code] where status: 1=success, 0=error, -1=race condition
    """
    # Establish an ID for the submission
    data['id'] = get_next_id_from_google_sheet(endpoint) 
    if data['id'] == 0:
        print(f"Error processing submission: could not access google sheet")
        return [0, 'Server Error: failed to access spreadsheet', 500]
    
    # Validate and upload files to Google Drive
    results = {}
    results['files_uploaded'] = {'len': 0, 'list': [], 'fid_list': []}
    uploaded_files = []
    folder_id = Config.GOOGLE_DRIVE_FOLDER[endpoint]

    uploadFailed = False
    upload_errors = []
    
    for key in files:
        file_data = files[key]
        if file_data.filename:
            # Validate file
            valid, error, safe_filename = validate_file(file_data, file_data.filename)
            if not valid:
                upload_errors.append(error)
                uploadFailed = True
                continue
            
            # Upload with sanitized filename
            link, fid = upload_to_google_drive(file_data, safe_filename, 
                        request_id=data["id"], parent_folder_id=folder_id)
            if link:
                uploaded_files.append({'fid': fid, 'link': link})
            else:
                uploadFailed = True
                upload_errors.append(f"Failed to upload {safe_filename}")

    if uploadFailed:
        # Delete files that were uploaded, then return error
        for file in uploaded_files:
            delete_from_google_drive(file['fid'])
        error_msg = 'File upload failed: ' + '; '.join(upload_errors) if upload_errors else 'Server Error: failed to upload one or more files'
        print(f"Error processing submission: {error_msg}")
        return [0, error_msg, 400]
    
    # Pack files and file ids into results struct
    for file in uploaded_files:
        results['files_uploaded']['list'].append(file['link'])
        results['files_uploaded']['fid_list'].append(file['fid'])
    results['files_uploaded']["len"] = len(results['files_uploaded']['list'])

    # Check for race condition
    unique_id = is_id_unused(endpoint, data["id"])
    if unique_id > 0:  # No race condition, proceed
        results['google_sheet'] = add_to_google_sheet(endpoint, data, results['files_uploaded']['list'])
    elif unique_id == 0:  # Connection error
        return [0, "Connection to Google Sheet failed", 500]
    else:  # Race condition occurred
        return [-1, results]

    if not results['google_sheet']:
        # ID was fine but writing to sheet failed - delete uploaded files
        for file in uploaded_files:
            delete_from_google_drive(file['fid'])
        print(f"Error processing submission: failed to record entry in google sheet")
        return [0, 'Server Error: failed to record entry in google sheet', 500]

    return [1, results]

def submission_handler_with_retry(data, files, endpoint):
    """
    Handle submissions with retry logic for race conditions
    Returns: [status, data/error, http_code]
    """
    race_condition = True
    counter = 0
    
    while race_condition:
        try:
            submission_results = core_submission(data, files, endpoint)
        except Exception as e:
            print(f"Error when writing to google sheet: {e}")
            return [0, "Internal Server Error", 500]
            
        if submission_results[0] > 0:
            race_condition = False
            results = submission_results[1]
        elif submission_results[0] == 0:
            return submission_results
        else:  # Race condition occurred
            counter += 1
            results = submission_results[1]
            # Clean up uploaded files
            for file in results['files_uploaded']['fid_list']:
                delete_from_google_drive(file['fid'])
            
            if counter < MAX_RETRIES:
                wait_time = (2 ** counter) + random.random()
                time.sleep(wait_time)
            else:
                print(f"Error when accessing Google Sheet: max retries exceeded")
                return [0, "Internal Server Error", 500]
                
    return submission_results

@app.route('/submit-PA', methods=['POST'])
@limiter.limit("10 per hour")  # Max 10 submissions per hour per IP
def submit_purchApproval():
    """Handle Purchase Approval submission"""
    endpoint = 'Purchase Approval'
    try:
        validation_result = validate_and_extract_input(endpoint, request)
        if validation_result[0] == 0:
            return jsonify({'error': validation_result[1]}), validation_result[2]
        data = validation_result[1]            

        submission_results = submission_handler_with_retry(data, request.files, endpoint)
        if submission_results[0] == 0:
            return jsonify({'error': submission_results[1]}), submission_results[2]
        results = submission_results[1]
        file_links = results["files_uploaded"]["list"]
            
        # If we haven't returned before this point, submission is successful
        # Try to run slack and email integrations
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
        validation_result = validate_and_extract_input(endpoint, request)
        if validation_result[0] == 0:
            return jsonify({'error': validation_result[1]}), validation_result[2]
        data = validation_result[1]            

        submission_results = submission_handler_with_retry(data, request.files, endpoint)
        if submission_results[0] == 0:
            return jsonify({'error': submission_results[1]}), submission_results[2]
        results = submission_results[1]
        file_links = results["files_uploaded"]["list"]

        # If we haven't returned before this point, submission is successful
        # Try to run email integration (no Slack for RR currently)
        results['slack'] = True  # We currently only bother sending PAs to a channel
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