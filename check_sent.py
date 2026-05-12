import os
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

def check_sent():
    creds = Credentials.from_authorized_user_file('token.json', ['https://www.googleapis.com/auth/gmail.readonly', 'https://www.googleapis.com/auth/gmail.send'])
    service = build('gmail', 'v1', credentials=creds)
    
    print("Checking SENT emails...")
    results = service.users().messages().list(userId='me', labelIds=['SENT'], maxResults=5).execute()
    messages = results.get('messages', [])

    if not messages:
        print("No sent messages found.")
    else:
        for msg in messages:
            msg_data = service.users().messages().get(userId='me', id=msg['id'], format='metadata').execute()
            headers = msg_data.get('payload', {}).get('headers', [])
            subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
            to = next((h['value'] for h in headers if h['name'] == 'To'), 'Unknown')
            date = next((h['value'] for h in headers if h['name'] == 'Date'), 'Unknown')
            print(f"- To: {to}\n  Subject: {subject}\n  Date: {date}\n")

if __name__ == '__main__':
    check_sent()
