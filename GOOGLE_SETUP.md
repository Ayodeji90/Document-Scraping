# Google Drive Setup Guide

This guide walks you through setting up Google Drive API access for the PPT scraper.

## Step 1: Create Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click the project dropdown → "New Project"
3. Name it: `ppt-scraper-project`
4. Click "Create"

## Step 2: Enable Google Drive API

1. In your new project, go to "APIs & Services" → "Library"
2. Search for "Google Drive API"
3. Click on "Google Drive API" → "Enable"

## Step 3: Create OAuth 2.0 Credentials

1. Go to "APIs & Services" → "Credentials"
2. Click "Create Credentials" → "OAuth 2.0 Client ID"
3. If prompted, configure consent screen:
   - User Type: External
   - App name: PPT Scraper
   - User support email: your email
   - Developer contact: your email
   - Save & Continue (skip scopes and test users for now)
4. Application type: "Desktop app"
5. Name: "PPT Scraper Desktop"
6. Click "Create"
7. Click "Download JSON"
8. Rename the downloaded file to `credentials.json`
9. Move it to the project root folder (next to `run.py`)

## Step 4: First Run

```bash
python run.py --dry-run
```

The first time you run:
1. A browser window will open
2. Sign in with your Google account
3. Click "Allow" to grant Drive permissions
4. The browser will show "Authentication successful"
5. Return to the terminal

Your authentication token will be saved to `token.pickle` for future runs.

## Troubleshooting

### "This app isn't verified"
- Click "Advanced" → "Go to [your app] (unsafe)"
- This is normal for personal OAuth apps

### "Access blocked"
- Ensure you're using the correct Google account
- Check that the Drive API is enabled
- Verify `credentials.json` is in the project folder

### Token expired
- Delete `token.pickle`
- Run the script again to re-authenticate

## Security Notes

- Keep `credentials.json` and `token.pickle` secure
- Do not commit these files to git (already in `.gitignore`)
- The app only accesses files it creates, not your entire Drive
