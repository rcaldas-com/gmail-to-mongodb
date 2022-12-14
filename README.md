Get emails from a GMail label, read attachments data and save to MongoDB.
-----
Python GMail API + MongoDB
===========================


Requirements
------------
* Google's json credential file `oauth.json`
  - Create one in [Google Cloud Console](https://console.cloud.google.com/apis/dashboard)
* Python pip or docker
* MongoDB
  - You can run a temp MongoDB instance in a new terminal with:

    `docker run --rm -it -v /tmp/mongodb:/data/db -p 27017:27017 mongo`

How to run
-----------
* You can create a venv inside repository dir with

    `python3 -m venv venv`

    `. venv/bin/activate`

    `pip install -r requirements.txt`

  
* And run

  `python3 gmail.py`


Settings
----------
* Set `LABEL` var with the label name to get emails from`
* Set `FROM` var with the string to match "from" email header
* The default connection URI is `mongodb://localhost/gmail`, set the env MONGO_URI to change
