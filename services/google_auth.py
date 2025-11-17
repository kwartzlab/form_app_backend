import os
import json

from oauth2client.service_account import ServiceAccountCredentials
from .utils import log_execution_time

def get_credentials():
    scope = ['https://spreadsheets.google.com/feeds',
            'https://www.googleapis.com/auth/drive']

    creds_json = os.environ.get('GOOGLE_SHEETS_CREDENTIALS')
    if creds_json:
        creds_dict = json.loads(creds_json)
        credentials = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    else:
        credentials = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)

    return credentials