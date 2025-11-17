from flask import Flask, request, jsonify
from flask_cors import CORS
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
        upload_to_google_drive, delete_from_google_drive

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

MAX_RETRIES = 5

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

def validate_and_extract_input(endpoint, submissionReq):
    # currently no need to apply different validation to different form types 
    # since they have the same fields
    schema = {
        "Reimbursement Request": ['firstName', 'lastName', 'email', ['comments', ''], 'expenses'],
        "Purchase Approval": ['firstName', 'lastName', 'email', ['comments', ''], 'expenses']
    }
    expenses_schema = {
        "Reimbursement Request": ['approval', 'vendor', 'description', 'amount', 'hst'],
        "Purchase Approval": ['vendor', 'description', 'amount']
    }
    try:
        # Verify captcha first before doing anything else
        captcha_token = submissionReq.form.get('captchaToken')
        if not captcha_token:
            return [0, 'Captcha token missing', 400]
        
        if not verify_hcaptcha(captcha_token):
            return [0, 'Captcha verification failed. Please try again.', 400]

        # extract form data
        data = {}
        for entry in schema[endpoint]:
            if isinstance(entry, list):
                data[entry[0]] = submissionReq.form.get(entry[0], entry[1])
            else:
                data[entry] = submissionReq.form.get(entry)

        json_expenses = data['expenses']
        data['expenses'] = json.loads(json_expenses)        #transform from json to list of dicts now instead of later

        # Validate required fields
        # TODO improve data validation to include type, not just being present
        if not all([data['firstName'], data['lastName'], data['email'], data['expenses']]):
            return [0, 'Missing required fields', 400]
        
        if not all(
            all(field in row and row[field] is not None for field in expenses_schema[endpoint])
            for row in data.get('expenses', [])
        ):
            return [0, 'Missing required fields in expense line', 400]
        
        return [1, data]
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
    # establish an ID for the submission, needed for file upload folder name as well as sheet entries
    data['id'] = get_next_id_from_google_sheet(endpoint) 
    if data['id'] == 0:
        print(f"Error processing submission: could not access google sheet")
        return [0, 'Server Error: failed to access spreadsheet', 500]
    
    # Upload files to Google Drive
    """first element of return: 1 success, 0 error, -1 race condition was detected.
    If the return is an error, the next two elements are a string of the error to return and 
    the http code for the server to return.
    If the return is a success, the second element is a dictionary reporting the status of 
    the different endpoints the server is trying to hit.
    If the return is -1, the calling function will use the fid_list to clean up the files uploaded by this function.
    """
    results = {}
    results['files_uploaded'] = {'len': 0, 'list': [], 'fid_list': []}
    uploaded_files = []
    folder_id = Config.GOOGLE_DRIVE_FOLDER[endpoint]

    uploadFailed = False
    for key in files:
        file_data = files[key]
        if file_data.filename:
            link, fid = upload_to_google_drive(file_data, file_data.filename, 
                        request_id=data["id"], parent_folder_id=folder_id)
            if link:
                uploaded_files.append({'fid': fid, 'link': link})
            else:
                uploadFailed = True

    if uploadFailed:
        #delete files that were uploaded, then return error
        for file in uploaded_files:
            delete_from_google_drive(file['fid'])
        print(f"Error processing submission: one or more file uploads failed")
        return [0, 'Server Error: failed to upload one or more files', 500]
    else:
        # upload succeeded, pack files and file ids into results struct, throw length on for good measure
        for file in uploaded_files:
            results['files_uploaded']['list'].append(file['link'])
            results['files_uploaded']['fid_list'].append(file['fid'])
        results['files_uploaded']["len"] = len(results['files_uploaded']['list'])

    unique_id = is_id_unused(endpoint, data["id"])
    if unique_id > 0:                   # no race condition, submission handler can proceed
        results['google_sheet'] = add_to_google_sheet(endpoint, data, results['files_uploaded']['list'])
    elif unique_id == 0:                # some other error, return to user
        return [0, "Connection to Google Sheet failed", 500]
    else:                               # race condition occurred, report to submission handler
        return [-1, results]            

    if not results['google_sheet']:     # id was fine, but writing to sheet failed for some other reason. delete files that were uploaded, then return error
        for file in uploaded_files:
            delete_from_google_drive(file['fid'])
        print(f"Error processing submission: failed to record entry in google sheet")
        return [0, 'Server Error: failed to record entry in google sheet', 500]

    return [1, results]

def submission_handler_with_retry(data, files, endpoint):
    """process flow has a small gap between when an id is grabbed and new line with that id is uploaded to spreadsheet, 
    meaning a potential race condition. This block calls for a check for the calculated id immediately before the call 
    to write to the spreadsheet. If the id is found in the spreadsheet, the function cleans up the uploaded files, then
    causes this block to wait for a bit and try again (up to 5 times)."""
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
        else:                   # race condition occurred, cleanup and wait, or exit after 5 tries
            counter += 1
            results = submission_results[1]
            for file in results['files_uploaded']['fid_list']:
                delete_from_google_drive(file['fid'])
            if counter < MAX_RETRIES:
                wait_time = (2 ** counter) + random.random()
                time.sleep(wait_time)
            else:
                print(f"Error when accessing Google Sheet")
                return [0, "Internal Server Error", 500]
    return submission_results

@app.route('/submit-PA', methods=['POST'])
@limiter.limit("10 per hour")  # Max 10 submissions per hour per IP
def submit_purchApproval():
    """Handle Purcahse Approval submission"""
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
        validation_result = validate_and_extract_input(endpoint, request)
        if validation_result[0] == 0:
            return jsonify({'error': validation_result[1]}), validation_result[2]
        data = validation_result[1]            

        submission_results = submission_handler_with_retry(data, request.files, endpoint)
        if submission_results[0] == 0:
            return jsonify({'error': submission_results[1]}), submission_results[2]
        results = submission_results[1]
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