from datetime import datetime
from os import getenv, path
import base64
import email

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from werkzeug.utils import secure_filename
from pymongo import MongoClient
import gridfs
import fitz

MONGO_URI = getenv('MONGO_URI', 'mongodb://localhost/gmail')
db = MongoClient(MONGO_URI).get_database()
fs = gridfs.GridFS(db)
maildb = db.mail

# Path to file with Google Credentials
AUTH_FILE = 'oauth.json'
# Scope of API to generate the token file in 'token.json' path
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

# Label to search emails in
LABEL = 'Boragora'
# From email header content to match
FROM = 'magmacontabilidade'


def main():
    creds = None
    if path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                AUTH_FILE, SCOPES)
            creds = flow.run_console()
            # creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    try:
        service = build('gmail', 'v1', credentials=creds)

        # Get Label ID
        result = service.users().labels().list(userId='me').execute()
        label = False
        for i in result.get('labels', []):
            if i['name'] == LABEL:
                label = i['id']
        if not label:
            print('Label not found')
            return

        # Get email list
        result = service.users().messages().list(userId='me', labelIds=label).execute()
        mails = result.get('messages', [])
        for mailid in mails:
            if maildb.find_one({'mailid': mailid['id']}):
                continue # Already in database
            
            # Get email data
            mail = service.users().messages().get(userId='me', id=mailid['id']).execute()
            mail_item = {
                'mailid': mailid['id'],
                'snippet': mail['snippet'],
                'files': [],
            }
            for k in mail['payload']['headers']:
                if k['name'] == 'From':
                    mail_item['from'] = k['value']
                elif k['name'] == 'Subject':
                    mail_item['subject'] = k['value']
                elif k['name'] == 'Date':
                    date = k['value'].split('(')[0].strip()
                    mail_item['date'] = datetime.strptime(date, '%a, %d %b %Y %X %z')

            # Check sender
            if not FROM in mail_item['from']:
                continue # Not from sender "FROM"

            # If mail is just text
            if mail['payload']['mimeType'] in ['text/plain', 'text/html']:
                msg = email.message_from_string(mail['payload']['body']['data'])
                message_bytes = base64.urlsafe_b64decode(msg.get_payload(decode=True))
                mail_item[mail['payload']['mimeType'].split('/')[1]] = message_bytes.decode('utf-8')
            else: # or have parts
                if mail['payload']['mimeType'] == 'multipart/mixed':
                    parts = mail['payload']['parts']
                elif mail['payload']['mimeType'] == 'multipart/alternative':
                    parts = [ mail['payload'] ]

                for part in parts:
                    if part['mimeType'] == 'multipart/alternative':
                        for i in part['parts']:
                            if i['mimeType'] in ['text/plain', 'text/html']:
                                msg = email.message_from_string(i['body']['data'])
                                message_bytes = base64.urlsafe_b64decode(msg.get_payload(decode=True))
                                mail_item[i['mimeType'].split('/')[1]] = message_bytes.decode('utf-8')
                            else:
                                print(f"Not identified:\n{i['mimeType']}")
                                return
                    elif part['filename']:
                        filename = secure_filename(part['filename'])
                        file = service.users().messages().attachments().get(userId='me', messageId=mailid['id'], id=part['body']['attachmentId']).execute()
                        file_id = fs.put(base64.urlsafe_b64decode(file['data']), content_type=part['mimeType'], filename=filename)
                        file_item = {
                            'id': file_id,
                            'name': filename,
                            'type': part['mimeType'],
                            # 'size': '?',
                        }
                        mail_item['files'].append(file_item)
                    else:
                        print(f"Not texts or file, not predicted:\n{part['mimeType']}")
                        return
            
            # Print dict created
            for i in mail_item.keys():
                print(f'{i}\n{mail_item[i]}\n')
            # Wait for check
            input('Enter to continue...')
            # Save to database
            maildb.insert_one(mail_item)

    except HttpError as error:
        # Handle errors from gmail API.
        print(f'An error occurred: {error}')

def get_file():
    mails = maildb.find({})
    for i in mails:
        # If have files get the first file
        if i.get('files') and len(i['files']) > 0:
            # # Save file to '/tmp' dir
            # filename = secure_filename(i['files'][0]['name'])
            # with open(f'/tmp/{filename}', 'wb') as f:
            #     f.write(fs.get(i['files'][0]['id']).read())

            import_pdf(fs.get(i['files'][0]['id']))
            return
    print('No files')

def import_pdf(file):
    if file.content_type != 'application/pdf':
        print('Not pdf')
        return False
    data = []
    with fitz.open(stream=file.read(), filetype='pdf') as doc:
        pages = doc.page_count
        for page in doc:
            data += page.get_text().split('\n')

    for i in data:
        print(i)
    print(f'\nPages: {pages}')




if __name__ == '__main__':
    # ! Clear database
    # maildb.delete_many({}) 

    # main()
    get_file()


