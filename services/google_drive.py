import os
import json
import io
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

from config import Config

def delete_from_google_drive(file_id):
    try:
        # Use same credentials as Google Sheets
        scope = ['https://spreadsheets.google.com/feeds',
                 'https://www.googleapis.com/auth/drive']
        
        creds_json = os.environ.get('GOOGLE_SHEETS_CREDENTIALS')
        if creds_json:
            creds_dict = json.loads(creds_json)
            credentials = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        else:
            credentials = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
        
        # Build Drive API service
        service = build('drive', 'v3', credentials=credentials)

        # Use Shared Drive
        supports_all_drives = {'supportsAllDrives': True}

        # Delete the file
        service.files().delete(
            fileId=file_id,
            supportsAllDrives=True
        ).execute()
        
        return True
        
    except Exception as e:
        print(f"Error deleting file from Google Drive: {e}")
        return False

def upload_to_google_drive(file_data, filename, request_id, parent_folder_id=None):
    """Upload file to Google Drive in a request-specific subfolder and return shareable link"""
    try:
        # Use same credentials as Google Sheets
        scope = ['https://spreadsheets.google.com/feeds',
                 'https://www.googleapis.com/auth/drive']
        
        creds_json = os.environ.get('GOOGLE_SHEETS_CREDENTIALS')
        if creds_json:
            creds_dict = json.loads(creds_json)
            credentials = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        else:
            credentials = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
        
        # Build Drive API service
        service = build('drive', 'v3', credentials=credentials)

        # Use Shared Drive
        supports_all_drives = {'supportsAllDrives': True}
        
        # Create or find the request-specific folder
        folder_metadata = {
            'name': request_id,
            'mimeType': 'application/vnd.google-apps.folder'
        }
        
        # If parent_folder_id is specified, create subfolder inside it
        if parent_folder_id:
            folder_metadata['parents'] = [parent_folder_id]
        
        # Check if folder already exists (in case multiple files in same request)
        query = f"name='{request_id}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
        if parent_folder_id:
            query += f" and '{parent_folder_id}' in parents"
        
        results = service.files().list(
            q=query, 
            fields='files(id)',
            **supports_all_drives,
            includeItemsFromAllDrives=True
        ).execute()
        folders = results.get('files', [])
        
        if folders:
            # Folder already exists, use it
            folder_id = folders[0]['id']
        else:
            # Create new folder
            folder = service.files().create(
                body=folder_metadata, 
                fields='id',
                **supports_all_drives
            ).execute()
            folder_id = folder.get('id')
            
            # Make folder accessible to organisation members
            permission = {
                'type': 'domain',
                'role': 'reader',
                'domain': 'kwartzlab.ca'
            }
            try:
                service.permissions().create(
                    fileId=folder_id,
                    body=permission,
                    **supports_all_drives
                ).execute()
            except Exception as e:
                print(f"Error editing folder permissions: {e}")
        
        # Prepare file metadata (upload into the request folder)
        file_metadata = {
            'name': filename,
            'parents': [folder_id]
        }
        
        # Create media upload
        media = MediaIoBaseUpload(
            io.BytesIO(file_data.read()),
            mimetype=file_data.content_type or 'application/octet-stream',
            resumable=True
        )
        
        # Upload file
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, webViewLink',
                **supports_all_drives
        ).execute()
        
        # Make file accessible to organisation members
        permission = {
            'type': 'domain',
            'role': 'reader',
            'domain': 'kwartzlab.ca'
        }
        try:
            service.permissions().create(
                fileId=file.get('id'),
                body=permission,
                **supports_all_drives
            ).execute()
        except Exception as e:
            print(f"Error editing file permissions: {e}")
        
        return file.get('webViewLink')
        
    except Exception as e:
        print(f"Error uploading to Google Drive: {e}")
        return None