from datetime import datetime
import os.path
import base64
from io import BytesIO

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from werkzeug.utils import secure_filename
from pymongo import MongoClient
import gridfs

db = MongoClient()
fs = gridfs.GridFS(db)

AUTH_FILE = 'oauth.json'

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
LABEL = 'Boragora'


def main():
    creds = None
    if os.path.exists('token.json'):
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
        result = service.users().labels().list(userId='me').execute()
        label = False
        for i in result.get('labels', []):
            if i['name'] == LABEL:
                label = i['id']
        if not label:
            print('Label not found')
            return 
        result = service.users().messages().list(userId='me', labelIds=label).execute()
        mails = result.get('messages', [])
        mail_list = []
        for mailid in mails:
            mail = service.users().messages().get(userId='me', id=mailid['id']).execute()
            mail_item = {
                'id': mailid['id'],
                'snippet': mail['snippet'],
                'files': [],
            }
            for k in mail['payload']['headers']:
                if k['name'] == 'Subject':
                    mail_item['subject'] = k['value']
                elif k['name'] == 'Date':
                    mail_item['date'] = k['value']
                elif k['name'] == 'From':
                    mail_item['from'] = k['value']
            parts = mail['payload']['parts']
            for part in parts:
                if part['partId'] == '0':
                    for i in part['parts']:
                        for j in i['body']:
                            if j == 'data':
                                try:
                                    message_bytes = base64.b64decode(i['body'][j].encode('utf-8'))
                                    mail_item['body'] = message_bytes.decode('utf-8')
                                except Exception:
                                    pass
                else:
                    if not part['filename']:
                        print('No Filename in part > 0')
                        return
                    filename = secure_filename(part['filename'])
                    file = service.users().messages().attachments().get(userId='me', messageId=mailid['id'], id=part['body']['attachmentId']).execute()

                    # print(file['data'])

                    file_id = fs.put(BytesIO(base64.b64decode(file['data']+'===')), filename=filename)
                    file_item = {
                        'id': file_id,
                        'name': filename,
                        'type': part['mimeType'],
                    }
                    mail_item['files'].append(file_item)
                print('\n')

            for i in mail_item.keys():
                print(i)
                print(mail_item[i])

            mail_list.append(mail_item)
            
            # for k in parts:
            #     print(k)
            #     # print(mail['payload']['parts'][k])
            #     print('\n\n')

            # # print('\n\n')
            return



    except HttpError as error:
        # TODO(developer) - Handle errors from gmail API.
        print(f'An error occurred: {error}')


if __name__ == '__main__':
    main()

