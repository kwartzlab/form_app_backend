import math
from datetime import datetime
import gspread

from config import Config
from .google_auth import get_credentials

def setup_google_sheets():
    """Initialize Google Sheets API connection"""
    credentials = get_credentials()

    client = gspread.authorize(credentials)
    return client


def id_iterator(client, endpoint):
    try:
        sheet = client.open(Config.GOOGLE_SHEET_NAME[endpoint]).sheet1 
        if endpoint == "Reimbursement Request":
            numRows = len(sheet.col_values(1))
            lastId = sheet.cell(numRows, 1).value
            newId = 0
            try:
                lastId_num = int(lastId)
                id_year = math.floor(lastId_num/10000)
                id_index = lastId_num - (id_year * 10000)
                current_year = datetime.now().year
                if id_year < current_year:
                    newId = (current_year * 10000) + 1
                else:
                    newId = (current_year * 10000) + id_index + 1 
            except ValueError:          #either id field is invalid, or the sheet is empty. Restart numbering at current year
                newId = (datetime.now().year * 10000) + 1
            return [1, newId]
        elif endpoint == "Purchase Approval":
            numRows = len(sheet.col_values(1))
            lastId = sheet.cell(numRows, 1).value
            newId = 0
            if lastId[:2] == "PA":      #valid format
                try:
                    lastId_num = int(lastId[2:])
                except ValueError: # invalid integer after "PA"
                    return [-1]
                newId_num = lastId_num + 1
                newId = "PA" + f"{newId_num:04d}"
                return [1, newId]
            else:
                return [-1]
        else:       #invalid endpoint
            print(f"Invalid endoint")
            return [-1]
    except Exception as e:
        print(f"Error accessing google sheet: {e}")
        return [-1]            #if accessing google sheet failed, abort attempt

def is_id_unused(endpoint, id):     # returns -1 for collision, 0 for error, 1 for success
    try:
        client = setup_google_sheets()
        if not client:
            print(f"Error with google sheet authentication")
            return 0
        sheet = client.open(Config.GOOGLE_SHEET_NAME[endpoint]).sheet1
        existing = sheet.findall(str(id))
        if existing:
            return -1
        else:
            return 1
    except Exception as e:
        print(f"Error accessing google sheet: {e}")
        return 0            #if accessing google sheet failed, abort attempt

def get_next_id_from_google_sheet(endpoint):
    try:
        client = setup_google_sheets()
        if not client:
            print(f"Error with google sheet authentication")
            return 0
        
        newId = id_iterator(client, endpoint)
        if newId[0] > 0:
            return newId[1]
        else:
            raise ValueError("invalid ID")
    except Exception as e:
        print(f"Error accessing google sheet: {e}")
        return 0            #if accessing google sheet failed, abort attempt
    
def buildrow(timestamp, endpoint, data, expense, file_links_str):
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
            file_links_str,
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
            file_links_str,
            data.get('comments', '')
        ]
    else:
        print ("invalid endpoint, returning empty row")
        row = []
    return row

def add_to_google_sheet(endpoint, data, file_links):
    """Add reimbursement data to Google Sheet"""
    try:
        client = setup_google_sheets()
        if not client:
            return False
        
        sheet = client.open(Config.GOOGLE_SHEET_NAME[endpoint]).sheet1       #todo: add additional error handling if this fails. Create new sheet with specified name, or just return error and exit as currently?
        
        # Prepare row data
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        file_links_str = ', '.join(file_links) if file_links else 'No attachments'
        expenses = json.loads(data['expenses'])

        # Add each expense as a separate row
        for expense in expenses:
            row = buildrow(timestamp, endpoint, data, expense, file_links_str)
            sheet.append_row(row)
        
        return True
    except Exception as e:
        print(f"Error adding to Google Sheet: {e}")
        return False
