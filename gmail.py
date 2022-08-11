import os.path
import base64

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

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
        labels = result.get('labels', [])
        for i in labels:
            if i['name'] == LABEL:
                label = i['id']
        result = service.users().messages().list(userId='me', labelIds=label).execute()
        mails = result.get('messages', [])
        for mailid in mails:
            mail = service.users().messages().get(userId='me', id=mailid['id']).execute()
            
            # print(mail)
            print(mail['internalDate'])
            for k in mail['payload']['headers']:
                if k['name'] == 'Subject':
                    print(k['value'])
            print(mail['snippet'])

            print('\n\n')

            parts = mail['payload']['parts']
            for part in parts:
                if part['partId'] == '0':
                    for i in part['parts']:
                        for j in i['body']:
                            if j == 'data':
                                b64data = f"{i['body'][j]}{'=' * ((4 - len(i['body'][j]) % 4) % 4)}"
                                try:
                                    base64_bytes = b64data.encode('utf-8')
                                    message_bytes = base64.b64decode(base64_bytes)
                                    message = message_bytes.decode('utf-8')

                                    # print(message)

                                except Exception:
                                    pass
                else:
                    if not part['filename']:
                        print('No Filename')
                    print(part['filename'])
                    print(part['mimeType'])
                    print(part['body']['attachmentId'])

                    file = service.users().messages().attachments().get(userId='me', messageId=mailid['id'], id=part['body']['attachmentId']).execute()
                    print(file['data'])
                        # print()

                    # for k in part.keys():
                    #     print(k)
                    #     print(part[k])
                    #     print('\n')

                print('\n')
            
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

