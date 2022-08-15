from datetime import datetime
from os import getenv, path
import locale
import base64
import email
import pytz

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

tz = pytz.timezone("America/Sao_Paulo")

# Path to file with Google Credentials
AUTH_FILE = 'oauth.json'
# Scope of API to generate the token file in 'token.json' path
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

# Label to search emails in
LABEL = 'Boragora'
# From email header content to match
FROM = 'magmacontabilidade'

# List of Doc types expected to get from attachment files
DOC_TYPES = [
    {
        # String to identify this type of Document
        'string': 'Documento de Arrecadação do Simples Nacional',
        'name': 'Imposto Simples Nacional',
        # Mongodb collection to save the new object
        'collection': 'expense',
        # List of info with positions to get from file data
        'get': [
            {
                'name': 'CNPJ',
                # Value *must* be equal to validate the file
                'value': '42.457.552/0001-73',
                # Positions in file's data where info appears
                'positions': [2,71],
            },
            {
                'name': 'Valor',
                'positions': [12,55,56,77],
                # Type of data to convert, default=string (as data ir read from file)
                'type': 'float',
            },
            {
                'name': 'Periodo',
                'positions': [15],
                'type': 'date',
            },
            {
                'name': 'Vencimento',
                'positions': [9,16,75],
                'type': 'date',
            },
        ]
    },
]

def main():
    # Get GMail service
    service = get_gmail_service()
    if not service:
        print('Fail to get gmail service')
        return

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
                # locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
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
        input('Enter to save...')
        # Save to database
        maildb.insert_one(mail_item)

def get_gmail_service():
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
        return build('gmail', 'v1', credentials=creds)
    except HttpError as error:
        # Handle errors from gmail API.
        print(f'An error occurred: {error}')
        return False

def get_file():
    mails = maildb.find({})
    for i in mails:
        # If have files get the first file
        if i.get('files') and len(i['files']) > 0:
            # # Save file to '/tmp' dir
            # filename = secure_filename(i['files'][0]['name'])
            # with open(f'/tmp/{filename}', 'wb') as f:
            #     f.write(fs.get(i['files'][0]['id']).read())

            return import_pdf(fs.get(i['files'][0]['id']))
    print('No files')

def import_pdf(file):
    if file.content_type != 'application/pdf':
        print('Not pdf')
        return False

    # Extract all data from PDF
    data = []
    with fitz.open(stream=file.read(), filetype='pdf') as doc:
        pages = doc.page_count
        for page in doc:
            data += page.get_text().split('\n')

    # Identify data positions (index of data list), change for each document, kept for history
    for i, x in enumerate(data):
        # print(x)

        # # Find and check CNPJ
        # if x == '42.457.552/0001-73':
        #     print(i)
        # # Value in positions 2,71 | put in DOC_TYPES 

        # # Find Valor position
        # if x == '13.567,44':
        #     print(i)
        # # Value in positions 12,55,56,77 | put in DOC_TYPES 

        # # Find Periodo
        # if x == 'Julho/2022':
        #     print(i)
        # # Value in position 15 | put in DOC_TYPES 

        # # Find Vencimento position
        # if x == '22/08/2022':
        #     print(i)
        # # Value in positions 9,16,75 | put in DOC_TYPES 

        pass

    doc = {}
    # Identify file type
    for dtype in DOC_TYPES:
        # First document type have the string splited in the two first data items
        if dtype['string'] == ' '.join(data[:2]):
            doc['name'] = dtype['name']
            # print(dtype['name'])

            # Get values
            for i in dtype['get']:
                # Get value from first position
                value = data[i['positions'][0]]
                # If more than 1 position, check if all positions match
                if len(i['positions']) > 1:
                    for p in i['positions'][1:]:
                        if value != data[p]:
                            print(f'"{i["name"]}" position values do not match:\n{value} | {data[p]}')
                            return False

                # Check if value match
                if i.get('value'):
                    if value != i['value']:
                        print(f"Wrong {i['name']}:\n{value} | {i['value']}")
                        return False

                # Format value type
                if i.get('type'):
                    # match i['type']:
                    if i['type'] == 'float':
                        value = value.replace('.', '').replace(',', '.')
                    elif i['type'] == 'date':
                        try:
                            value = datetime.strptime(value, '%d/%m/%Y').date()
                            # Treat error in mongodb to encode datetime.date object
                            value = str(value)
                        except ValueError:
                            # Treat locale language
                            locale.setlocale(locale.LC_ALL, 'pt_BR.UTF-8')
                            value = datetime.strptime(value, '%B/%Y').date()
                            value = str(value)
                    else:
                        print(f"Invalid data type: {i['type']}")
                        return False

                doc[i['name']] = value
                # print(f"{i['name']}: {value}")
            
            print(doc)

            coll = eval(f"db.{dtype['collection']}")
            result = coll.insert_one(doc)
            
            print(result.inserted_id)

            return(result.inserted_id)
            

    # print(f'\nPages: {pages}')
    return data

if __name__ == '__main__':
    # ! Clear database
    # maildb.delete_many({}) 

    # main()
    get_file()


