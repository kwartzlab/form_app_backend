import math
from datetime import datetime
import gspread

from config import Config
from .google_auth import get_credentials
from .utils import log_execution_time
from services.logger import logger

_sheets_client = None

def setup_google_sheets():
    """Initialize Google Sheets API connection with caching"""
    global _sheets_client
    delegate = Config.OUTBOUND_EMAIL_ADDRESS if Config.FLASK_ENV == 'production' else Config.DEV_OUTBOUND_EMAIL_ADDRESS
    credentials = get_credentials(delegate_to=delegate)
    if _sheets_client is None:
        delegate = Config.OUTBOUND_EMAIL_ADDRESS if Config.FLASK_ENV == 'production' else Config.DEV_OUTBOUND_EMAIL_ADDRESS
        credentials = get_credentials(delegate_to=delegate)
        _sheets_client = gspread.authorize(credentials)
    return _sheets_client

def get_worksheet(client, endpoint):
    spreadsheet = client.open_by_key(Config.GOOGLE_SHEET_ID[endpoint])
    logger.info("accessed spreadsheet")
    sheet = spreadsheet.worksheet(Config.GOOGLE_WORKSHEET_NAME[endpoint]) 
    logger.info("accessed worksheet")

    return sheet

@log_execution_time
def id_iterator(client, endpoint):
    try:
        sheet = get_worksheet(client, endpoint)

        id_column = sheet.col_values(1)

        if endpoint == "Reimbursement Request":
            if not id_column or len(id_column) == 0:
                return [0]
            
            lastId = id_column[-1]  # Last value in column
            try:
                lastId_num = int(lastId)
                id_year = lastId_num // 10000
                id_index = lastId_num % 10000
                current_year = datetime.now().year
                if id_year < current_year:
                    return [1, ((current_year * 10000) + 1)]
                else:
                    return [1, (current_year * 10000) + id_index + 1]
            except ValueError:
                return [0]
        elif endpoint == "Purchase Approval":
            if not id_column or len(id_column) == 0:
                return [0]
            lastId = id_column[-1]
            if lastId[:2] == "PA":      #valid format
                try:
                    lastId_num = int(lastId[2:])
                    newId_num = lastId_num + 1
                    return [1, f"PA{newId_num:04d}"]
                except ValueError: # invalid integer after "PA"
                    return [0]
            else:
                return [0]
        else:       #invalid endpoint
            # print(f"Invalid endoint")
            logger.warning("Invalid Endpoint")
            return [0]
    except Exception as e:
        # print(f"Error accessing google sheet: {e}")
        logger.exception("Exception Occurred", extra={'failed to access google sheet':str(e)}, exc_info=True)

        return [0]            #if accessing google sheet failed, abort attempt

def is_id_unused(endpoint, id):     # returns -1 for collision, 0 for error, 1 for success
    try:
        client = setup_google_sheets()
        if not client:
            # print(f"Error with google sheet authentication")
            logger.error("Error with google sheet authentication")
            return 0
        sheet = get_worksheet(client, endpoint)
        id_column = sheet.col_values(1)
        if str(id) in id_column:
            return -1
        else:
            return 1
    except Exception as e:
        # print(f"Error accessing google sheet: {e}")
        logger.exception("Exception Occurred", extra={'error accessing google sheet':str(e)}, exc_info=True)
        return 0            #if accessing google sheet failed, abort attempt

@log_execution_time
def get_next_id_from_google_sheet(endpoint):
    logger.info("attempting to retrieve next id from google sheet")
    try:
        client = setup_google_sheets()
        if not client:
            logger.error("Error with google sheet authentication")
            # print(f"Error with google sheet authentication")
            return 0
        
        newId = id_iterator(client, endpoint)
        if newId[0] > 0:
            return newId[1]
        else:
            raise ValueError("invalid ID")
    except Exception as e:
        logger.exception("Exception Occurred", extra={'error accessing google sheet':str(e)}, exc_info=True)
        # print(f"Error accessing google sheet: {e}")
        return 0            #if accessing google sheet failed, abort attempt
    
def buildrow(timestamp, endpoint, data, expense, row_file_entry):
    if endpoint == "Reimbursement Request":
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
            row_file_entry,
            data.get('comments', '')
        ]
    elif endpoint == "Purchase Approval":
        row = [
            data['id'],
            timestamp,
            data['firstName'],
            data['lastName'],
            data['email'],
            expense.get('vendor', ''),
            expense.get('description', ''),
            expense.get('amount', ''),
            row_file_entry,
            data.get('comments', '')
        ]
    else:
        logger.warning("invalid endpoint, returning empty row")
        # print ("invalid endpoint, returning empty row")
        row = []
    return row

@log_execution_time
def add_to_google_sheet(endpoint, data, file_links):
    """Add reimbursement data to Google Sheet"""
    try:
        client = setup_google_sheets()
        sheet = get_worksheet(client, endpoint)     #todo: add additional error handling if this fails. Create new sheet with specified name, or just return error and exit as currently?
        
        # Prepare row data
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # Add each expense as a separate row
        rows = []
        for i, expense in enumerate(data['expenses']):
            # add one receipt link per expense row, so file links work in google sheets
            row_file_entry = file_links[i] if (i < len(file_links)) else '-'
            row = buildrow(timestamp, endpoint, data, expense, row_file_entry)
            rows.append(row)

        #if there are more file links than expense rows, add extra lines
        if (len(data['expenses']) < len(file_links)):
            for leftover_file in file_links[len(data['expenses']):]:
                dummy_expense = {
                    'approval': '-',
                    'vendor': '-',
                    'description': '-',
                    'amount': '-',
                    'hst': '-'
                }
                row = buildrow(timestamp, endpoint, data, dummy_expense, leftover_file)
                rows.append(row)

        sheet.append_rows(rows, table_range="A1", value_input_option='USER_ENTERED')
        
        return True
    except Exception as e:
        # print(f"Error adding to Google Sheet: {e}")
        logger.error("Error Occurred", extra={'error adding to google sheet':str(e)}, exc_info=True)
        return False
