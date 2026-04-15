"""
Google Drive integration for uploading PPT files.
"""
import os
import pickle
from pathlib import Path
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

SCOPES = ['https://www.googleapis.com/auth/drive']


class GoogleDriveUploader:
    """Handles PPT uploads to Google Drive."""
    
    def __init__(self, credentials_path=None, token_path=None):
        self.credentials_path = credentials_path or 'credentials.json'
        self.token_path = token_path or 'token.pickle'
        self.service = None
        self.folder_id = None
        
    def authenticate(self):
        """Authenticate with Google Drive API."""
        creds = None
        
        if os.path.exists(self.token_path):
            with open(self.token_path, 'rb') as token:
                creds = pickle.load(token)
                
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists(self.credentials_path):
                    raise FileNotFoundError(
                        f"{self.credentials_path} not found. "
                        "Please follow GOOGLE_SETUP.md to create it."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_path, SCOPES)
                creds = flow.run_local_server(port=0)
                
            with open(self.token_path, 'wb') as token:
                pickle.dump(creds, token)
                
        self.service = build('drive', 'v3', credentials=creds)
        print("✓ Google Drive authentication successful")
        return self
    
    def create_folder(self, folder_name="PPT_Scraper_Downloads"):
        """Create main folder for PPT downloads."""
        query = f"mimeType='application/vnd.google-apps.folder' and name='{folder_name}' and trashed=false"
        results = self.service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
        items = results.get('files', [])
        
        if items:
            self.folder_id = items[0]['id']
            print(f"✓ Using existing folder: {folder_name}")
            return self.folder_id
        
        file_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder'
        }
        folder = self.service.files().create(body=file_metadata, fields='id').execute()
        self.folder_id = folder.get('id')
        print(f"✓ Created new folder: {folder_name}")
        return self.folder_id
    
    def upload_file(self, file_path, metadata=None):
        """Upload a PPT file to Google Drive."""
        if not self.service:
            raise RuntimeError("Not authenticated. Call authenticate() first.")
        if not self.folder_id:
            self.create_folder()
            
        file_path = Path(file_path)
        
        # Check if file already exists (by name in folder)
        query = f"name='{file_path.name}' and '{self.folder_id}' in parents and trashed=false"
        existing = self.service.files().list(q=query, spaces='drive', fields='files(id)').execute()
        
        if existing.get('files'):
            print(f"⚠ File already exists, skipping: {file_path.name}")
            return existing['files'][0]['id']
        
        file_metadata = {
            'name': file_path.name,
            'parents': [self.folder_id]
        }
        
        if metadata:
            description_parts = []
            if metadata.get('source_url'):
                description_parts.append(f"Source: {metadata['source_url']}")
            if metadata.get('domain'):
                description_parts.append(f"Domain: {metadata['domain']}")
            if metadata.get('scraped_date'):
                description_parts.append(f"Scraped: {metadata['scraped_date']}")
            if description_parts:
                file_metadata['description'] = ' | '.join(description_parts)
        
        # Determine MIME type based on extension
        file_lower = str(file_path).lower()
        if file_lower.endswith('.pptx'):
            mimetype = 'application/vnd.openxmlformats-officedocument.presentationml.presentation'
        else:
            mimetype = 'application/vnd.ms-powerpoint'
        
        media = MediaFileUpload(
            str(file_path),
            mimetype=mimetype,
            resumable=True
        )
        
        file = self.service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, name, webViewLink'
        ).execute()
        
        print(f"✓ Uploaded: {file_path.name}")
        return file.get('id')
    
    def list_files(self):
        """List all files in the PPT folder."""
        if not self.folder_id:
            self.create_folder()
            
        query = f"'{self.folder_id}' in parents and trashed=false"
        results = self.service.files().list(
            q=query,
            spaces='drive',
            fields='files(id, name, createdTime, webViewLink)'
        ).execute()
        return results.get('files', [])
