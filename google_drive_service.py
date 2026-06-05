# google_drive_service.py

import os
import pickle

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request


SCOPES = [
    "https://www.googleapis.com/auth/drive"
]

# GANTI DENGAN FOLDER ID KAMU
FOLDER_ID = "1qltHd7y8SGGFMFZvBlJwQ1PwXLwHRSBD"


def get_drive_service():

    creds = None

    # LOAD TOKEN
    if os.path.exists("token.pickle"):

        with open("token.pickle", "rb") as token:
            creds = pickle.load(token)

    # LOGIN
    if not creds or not creds.valid:

        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())

        else:

            flow = InstalledAppFlow.from_client_secrets_file(
                "credentials.json",
                SCOPES
            )

            creds = flow.run_local_server(port=0)

        # SAVE TOKEN
        with open("token.pickle", "wb") as token:
            pickle.dump(creds, token)

    service = build(
        "drive",
        "v3",
        credentials=creds
    )

    return service


drive_service = get_drive_service()


def upload_file_to_drive(file_path, mime_type):

    file_name = os.path.basename(file_path)

    file_metadata = {
        "name": file_name,
        "parents": [FOLDER_ID]
    }

    media = MediaFileUpload(
        file_path,
        mimetype=mime_type
    )

    uploaded_file = drive_service.files().create(
        body=file_metadata,
        media_body=media,
        fields="id"
    ).execute()

    file_id = uploaded_file.get("id")

    # PUBLIC ACCESS
    drive_service.permissions().create(
        fileId=file_id,
        body={
            "role": "reader",
            "type": "anyone"
        }
    ).execute()

    public_url = f"https://drive.google.com/file/d/{file_id}/view"

    return public_url