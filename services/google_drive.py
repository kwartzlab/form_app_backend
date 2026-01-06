import os
import json
import io
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

from config import Config
from .google_auth import get_credentials
from .utils import log_execution_time
from services.logger import logger

_folder_cache = {}

@log_execution_time
def delete_from_google_drive(file_id):
    try:
        delegate = Config.OUTBOUND_EMAIL_ADDRESS if Config.FLASK_ENV == 'production' else Config.DEV_OUTBOUND_EMAIL_ADDRESS #todo: refactor, move this inside get_credentials?
        credentials = get_credentials(delegate_to=delegate)
        
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
        # print(f"Error deleting file from Google Drive: {e}")
        logger.error("Error Occurred", extra={'error deleting file from google drive':str(e)}, exc_info=True)
        return False

@log_execution_time
def upload_to_google_drive(file_data, filename, request_id, parent_folder_id=None):
    """Upload file to Google Drive in a request-specific subfolder and return shareable link"""
    try:
        delegate = Config.OUTBOUND_EMAIL_ADDRESS if Config.FLASK_ENV == 'production' else Config.DEV_OUTBOUND_EMAIL_ADDRESS
        credentials = get_credentials(delegate_to=delegate)
        service = build('drive', 'v3', credentials=credentials)
        supports_all_drives = {'supportsAllDrives': True}
        
        cache_key = f"{parent_folder_id}_{request_id}"
        if cache_key in _folder_cache:
            folder_id = _folder_cache[cache_key]
        else:
            # Create or find folder (existing logic)
            folder_metadata = {
                'name': request_id,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            
            if parent_folder_id:
                folder_metadata['parents'] = [parent_folder_id]
            
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
                folder_id = folders[0]['id']
            else:
                folder = service.files().create(
                    body=folder_metadata, 
                    fields='id',
                    **supports_all_drives
                ).execute()
                folder_id = folder.get('id')
                
                # Make folder accessible to organisation members
                """permission = {
                    'type': 'domain',
                    'role': 'reader',
                    'domain': Config.ORGANIZATION_DOMAIN
                }
                try:
                    service.permissions().create(
                        fileId=folder_id,
                        body=permission,
                        **supports_all_drives
                    ).execute()
                except Exception as e:
                    print(f"Error editing folder permissions: {e}")"""
            
            # Cache the folder ID
            _folder_cache[cache_key] = folder_id
            
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
        """permission = {
            'type': 'domain',
            'role': 'reader',
            'domain': Config.ORGANIZATION_DOMAIN
        }
        try:
            service.permissions().create(
                fileId=file.get('id'),
                body=permission,
                **supports_all_drives
            ).execute()
        except Exception as e:
            print(f"Error editing file permissions: {e}")"""
        
        return file.get('webViewLink'), file.get('id')
        
    except Exception as e:
        # print(f"Error uploading to Google Drive: {e}")
        logger.error("Error Occurred", extra={'error uploading to google drive':str(e)}, exc_info=True)
        return None