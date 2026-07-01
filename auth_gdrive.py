#!/usr/bin/env python3
"""Run this once locally to authenticate Google Drive and generate token.pickle."""
import pickle
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

SCOPES = ["https://www.googleapis.com/auth/drive.file"]
CREDS_FILE = Path("credentials.json")
TOKEN_FILE = Path("token.pickle")

def main():
    creds = None
    if TOKEN_FILE.exists():
        with open(TOKEN_FILE, "rb") as f:
            creds = pickle.load(f)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "wb") as f:
            pickle.dump(creds, f)

    print("Authentication successful! token.pickle has been created.")
    print("Now run: scp credentials.json token.pickle root@167.233.129.72:/root/Document-Scraping/")

if __name__ == "__main__":
    main()
