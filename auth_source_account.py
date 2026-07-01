#!/usr/bin/env python3
"""
Run this ONCE to authenticate the SOURCE Google account (the old one with 50K files).
When the browser opens, sign in with the account that OWNS the old Drive folder.
"""
import pickle
from pathlib import Path
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
TOKEN  = Path("source_token.pickle")
CREDS  = Path("credentials.json")

SOURCE_FOLDER_ID = "1eShoyLCH1ulzGUtlYHLiaIIbrBohUJkZ"

def main():
    print("\n" + "="*60)
    print("  SIGN IN WITH THE OLD GOOGLE ACCOUNT (the one with 50K files)")
    print("="*60 + "\n")

    flow = InstalledAppFlow.from_client_secrets_file(str(CREDS), SCOPES)
    creds = flow.run_local_server(port=0)

    with open(TOKEN, "wb") as f:
        pickle.dump(creds, f)

    svc = build("drive", "v3", credentials=creds)
    about = svc.about().get(fields="user").execute()
    email = about["user"]["emailAddress"]
    print(f"\n  Authenticated as: {email}")

    try:
        folder = svc.files().get(fileId=SOURCE_FOLDER_ID, fields="id,name").execute()
        print(f"  Folder found: {folder['name']} ({folder['id']})")
        print(f"\n  SUCCESS — source_token.pickle saved. Now run: python gdrive_transfer.py")
    except Exception as e:
        print(f"\n  WARNING: Folder not visible to {email}: {e}")
        print("  Make sure you signed in with the account that OWNS the old folder.")

if __name__ == "__main__":
    main()
