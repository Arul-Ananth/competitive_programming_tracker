import json
import os

import gspread
from google.oauth2.service_account import Credentials


SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]


class AuthenticationError(Exception):
    pass


class SheetAccessError(Exception):
    pass


def create_gspread_client() -> gspread.Client:
    service_account_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    service_account_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip()

    try:
        if service_account_json:
            info = json.loads(service_account_json)
            credentials = Credentials.from_service_account_info(info, scopes=SCOPES)
        elif service_account_file:
            credentials = Credentials.from_service_account_file(
                service_account_file, scopes=SCOPES
            )
        else:
            raise AuthenticationError(
                "Missing Google credentials. Set GOOGLE_SERVICE_ACCOUNT_JSON or GOOGLE_SERVICE_ACCOUNT_FILE."
            )

        return gspread.authorize(credentials)
    except AuthenticationError:
        raise
    except Exception as exc:
        raise AuthenticationError("Failed to authenticate with Google APIs.") from exc


def open_spreadsheet(sheet_id: str):
    client = create_gspread_client()
    try:
        return client.open_by_key(sheet_id)
    except Exception as exc:
        raise SheetAccessError(f"Failed to open Google Sheet: {sheet_id}") from exc

