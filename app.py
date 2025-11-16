from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import requests as req

from config import Config
from services import get_next_id_from_google_sheet, add_to_google_sheet, send_email_notification, send_slack_notification
from services import upload_to_google_drive, delete_from_google_drive


app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

def verify_hcaptcha(token):
    """Verify hCAPTCHA token"""
    try:
        response = req.post(
            'https://hcaptcha.com/siteverify',
            data={
                'secret': Config.HCAPTCHA_SECRET_KEY,
                'response': token
            }
        )
        result = response.json()
        return result.get('success', False)
    except Exception as e:
        print(f"Error verifying hCAPTCHA: {e}")
        return False

@app.route('/submit', methods=['POST'])
def submit_reimbursement():
    """Handle reimbursement submission"""
    try:
        # Verify captcha FIRST before doing anything else
        captcha_token = request.form.get('captchaToken')
        if not captcha_token:
            return jsonify({'error': 'Captcha token missing'}), 400
        
        if not verify_hcaptcha(captcha_token):
            return jsonify({'error': 'Captcha verification failed. Please try again.'}), 400

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
        if nextId == 0:
            print(f"Error processing submission: could not access google sheet")
            return jsonify({'error': 'Server Error: failed to access spreadsheet'}), 500

        data['id'] = nextId
        
        # core integrations are file upload and google sheets, do those first

        # Upload files to Google Drive
        file_links = []
        files = []
        folder_id = os.environ.get('GOOGLE_DRIVE_FOLDER_ID')  # Optional: specific folder

        # In your submit endpoint, where you upload files:
        uploadFailed = False
        for key in request.files:
            file_data = request.files[key]
            if file_data.filename:
                link, fid = upload_to_google_drive(file_data, file_data.filename, request_id=nextId, parent_folder_id=folder_id)
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
            return jsonify({'error': 'Server Error: failed to upload one or more files'}), 500
        else:
            for file in files:
                file_links.append(file['link'])
            results['files_uploaded'] = len(file_links)

        results['google_sheet'] = add_to_google_sheet(data, file_links)

        if not results['google_sheet']:
            #delete files that were uploaded, then return error
            for file in files:
                delete_from_google_drive(file['fid'])
            print(f"Error processing submission: failed to record entry in google sheet")
            return jsonify({'error': 'Server Error: failed to record entry in google sheet'}), 500

        # If we haven't returned before this point, submission is successful. Try to run slack and email integrations
        results['slack'] = send_slack_notification(data, file_links)
        results['email'] = send_email_notification(data, file_links)
        
        if not results['slack'] or not results['email']:
            message = 'Submission succeeded, but one or more integrations failed. Please contact the treasurer.'
        else:
            message = 'Submission succeeded.'

        return jsonify({
            'message': message,
            'details': results
        }), 200
                
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