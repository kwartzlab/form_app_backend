import os
import json

from oauth2client.service_account import ServiceAccountCredentials
from .utils import log_execution_time

def get_credentials(delegate_to=None):
    scope = ['https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive.file']

    creds_json = os.environ.get('GOOGLE_SHEETS_CREDENTIALS')
    if creds_json:
        creds_dict = json.loads(creds_json)
        credentials = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    else:
        credentials = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)

    # Add delegation if specified
    if delegate_to:
        credentials = credentials.create_delegated(delegate_to)

    return credentials