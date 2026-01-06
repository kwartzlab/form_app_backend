import os
import json

from google.oauth2 import service_account

def get_credentials(delegate_to=None):
    SCOPES = ['https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive.file']

    creds_json = os.environ.get('GOOGLE_SHEETS_CREDENTIALS')
    if creds_json:
        creds_dict = json.loads(creds_json)
        credentials = service_account.Credentials.from_service_account_file(creds_dict, scopes=SCOPES)
    else:
        credentials = service_account.Credentials.from_service_account_file('credentials.json', scopes=SCOPES)

    # Add delegation if specified
    if delegate_to:
        delegated_credentials = credentials.with_subject(delegate_to)
        return delegated_credentials

    return credentials