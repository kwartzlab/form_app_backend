import os
import json
import math
from datetime import datetime
import gspread

from config import Config
from services import get_credentials

def setup_google_sheets():
    """Initialize Google Sheets API connection"""
    credentials = get_credentials()

    client = gspread.authorize(credentials)
    return client

def get_next_id_from_google_sheet():
    try:
        client = setup_google_sheets()
        if not client:
            return (datetime.now().year * 10000 + 1)
        
        sheet = client.open(Config.GOOGLE_SHEET_NAME).sheet1   
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
        except ValueError:
            newId = (datetime.now().year * 10000) + 1
        return newId
    except Exception as e:
        print(f"Error accessing google sheet: {e}")
        return 0            #if accessing google sheete failed, abort attempt
    
def add_to_google_sheet(data, file_links):
    """Add reimbursement data to Google Sheet"""
    try:
        client = setup_google_sheets()
        if not client:
            return False
        
        sheet = client.open(Config.GOOGLE_SHEET_NAME).sheet1       #todo: add additional error handling if this fails. Create new sheet with specified name, or just return error and exit as currently?
        
        # Prepare row data
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        expenses = json.loads(data['expenses'])

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
