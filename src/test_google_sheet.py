import gspread
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

SERVICE_ACCOUNT_FILE = "service_account.json"
SPREADSHEET_ID = "1qnf-7IHyfwucyRblk-weOv6h2pET0IkLmdnfPssyVUQ"

creds = Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE,
    scopes=SCOPES
)

client = gspread.authorize(creds)
sheet = client.open_by_key(SPREADSHEET_ID).sheet1

print("Connected successfully")
print("Sheet title:", sheet.title)
print("First 5 rows:")
rows = sheet.get_all_values()[:5]
for row in rows:
    print(row)