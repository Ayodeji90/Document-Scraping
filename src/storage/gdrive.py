"""
Google Drive uploader — uploads scraped PPT files to a Drive folder.
Requires credentials.json (OAuth2) — see GOOGLE_SETUP.md.
"""
import logging
import os
import pickle
from pathlib import Path

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive.file"]
FOLDER_NAME = "ScrapedPPTs"


class GoogleDriveUploader:
    def __init__(self):
        self.creds = None
        self.service = None
        self.folder_id = None

    def authenticate(self):
        """Authenticate with Google Drive via OAuth2."""
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
        except ImportError:
            raise ImportError(
                "Google API libraries not installed. Run: "
                "pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib"
            )

        token_path = Path("token.pickle")
        creds_path = Path("credentials.json")

        if not creds_path.exists():
            raise FileNotFoundError(
                "credentials.json not found. See GOOGLE_SETUP.md to set up OAuth2 credentials."
            )

        if token_path.exists():
            with open(token_path, "rb") as f:
                self.creds = pickle.load(f)

        if not self.creds or not self.creds.valid:
            if self.creds and self.creds.expired and self.creds.refresh_token:
                self.creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
                self.creds = flow.run_local_server(port=0)
            with open(token_path, "wb") as f:
                pickle.dump(self.creds, f)

        from googleapiclient.discovery import build
        self.service = build("drive", "v3", credentials=self.creds)
        logger.info("Google Drive authenticated successfully")

    def create_folder(self, name: str = FOLDER_NAME) -> str:
        """Create or find an existing folder in Drive, return its ID."""
        # Check if folder exists
        query = f"name='{name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
        results = self.service.files().list(q=query, fields="files(id, name)").execute()
        folders = results.get("files", [])

        if folders:
            self.folder_id = folders[0]["id"]
            logger.info(f"Using existing Drive folder: {name} ({self.folder_id})")
        else:
            meta = {
                "name": name,
                "mimeType": "application/vnd.google-apps.folder",
            }
            folder = self.service.files().create(body=meta, fields="id").execute()
            self.folder_id = folder.get("id")
            logger.info(f"Created Drive folder: {name} ({self.folder_id})")

        return self.folder_id

    def upload_file(self, file_path: Path, extra_meta: dict = None) -> str:
        """Upload a single file to the Drive folder, return the file ID."""
        from googleapiclient.http import MediaFileUpload

        if not self.folder_id:
            raise RuntimeError("Call create_folder() first")

        mime = (
            "application/vnd.openxmlformats-officedocument.presentationml.presentation"
            if str(file_path).endswith(".pptx")
            else "application/vnd.ms-powerpoint"
        )

        meta = {"name": file_path.name, "parents": [self.folder_id]}
        if extra_meta:
            meta.update(extra_meta)

        media = MediaFileUpload(str(file_path), mimetype=mime, resumable=True)
        result = (
            self.service.files()
            .create(body=meta, media_body=media, fields="id")
            .execute()
        )
        file_id = result.get("id")
        logger.info(f"Uploaded {file_path.name} → Drive ID {file_id}")
        return file_id
