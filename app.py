import os
import flask
from flask import request, url_for
import pymongo
import base64
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import time
from email.utils import formataddr
from flask_cors import CORS
import google.oauth2.credentials
import google_auth_oauthlib.flow
import googleapiclient.discovery
from threading import Thread
from dotenv import load_dotenv
import json

load_dotenv()

app = flask.Flask(__name__)
CORS(app, origins=json.loads(os.environ.get('ALLOWED_ORIGINS')))
app.secret_key = os.environ.get('FLASK_SECRET_KEY')

myclient = pymongo.MongoClient(os.environ.get('MONGO_URI'))
mydb = myclient["users"]
mycol = mydb["user_info"]
mycol_results = mydb["users_records_results"]
mycol_errors = mydb["users_records_errors"]
CLIENT_SECRET = {
    "web": {
        "client_id": os.environ.get('CLIENT_ID'),
        "project_id": os.environ.get('PROJECT_ID'),
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_secret": os.environ.get('CLIENT_SECRET'),
        "redirect_uris": json.loads(os.environ.get('REDIRECT_URIS')),
        "javascript_origins": json.loads(os.environ.get('JAVASCRIPT_ORIGINS'))

    }
}
API_NAME_SHEETS = 'sheets'
API_VERSION_SHEETS = 'v4'
API_NAME_EMAIL = 'gmail'
API_VERSION_EMAIL = 'v1'
@app.route('/', methods=['POST', 'GET'])
def serve():
    if request.method == 'GET':
        print("flask.session during GET: ", flask.session)  # Debugging print statement
        if 'credentials' in flask.session:
            print("EMAIL 2: "+flask.session['email'])
            print("Name 2: "+flask.session['name'])
            print("PICTURE 2: "+flask.session['picture'])
            print("ID 2: "+flask.session['id'])
            user_dict={"name": flask.session['name'], "email": flask.session['email'], "picture": flask.session['picture'], "id": flask.session['id']}
            print("flask.session during POST: ", flask.session)  # Debugging print statement
            if(list(mycol.find({"id": flask.session["id"]},{})) == []):
                mycol.insert_one(user_dict)
            myquery ={'id':flask.session['id']}
            newvalues = {'$set': {"credentials": flask.session['credentials']}}
            mycol.update_one(myquery,newvalues)
            return flask.redirect(url_for("account"))
        return flask.render_template("signin.html")
    
@app.route('/authorize')
def authorize():
    flow = google_auth_oauthlib.flow.Flow.from_client_config(
        CLIENT_SECRET,
        scopes=['https://www.googleapis.com/auth/drive.metadata.readonly',
                'https://www.googleapis.com/auth/spreadsheets.readonly',
                'https://www.googleapis.com/auth/gmail.send',
                'https://www.googleapis.com/auth/userinfo.email',
                'https://www.googleapis.com/auth/userinfo.profile',
                'openid'],
        redirect_uri=url_for('oauth2callback', _external=True)
    )
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true')
    flask.session['state'] = state
    print("flask.session during AUTORIZE: ", flask.session)  # Debugging print statement
    return flask.redirect(authorization_url)

@app.route('/oauth2callback')
def oauth2callback():
    state = flask.session['state']
    flow = google_auth_oauthlib.flow.Flow.from_client_config(
        CLIENT_SECRET,
        scopes=['https://www.googleapis.com/auth/drive.metadata.readonly',
                'https://www.googleapis.com/auth/spreadsheets.readonly',
                'https://www.googleapis.com/auth/gmail.send',
                'https://www.googleapis.com/auth/userinfo.email',
                'https://www.googleapis.com/auth/userinfo.profile',
                'openid'],
        state=state,
        redirect_uri=url_for('oauth2callback', _external=True)
    )
    authorization_response = flask.request.url
    flow.fetch_token(authorization_response=authorization_response)
    credentials = flow.credentials
    flask.session['credentials'] = credentials_to_dict(credentials)
    user_info_service = googleapiclient.discovery.build('oauth2', 'v2', credentials=credentials)
    user_info = user_info_service.userinfo().get().execute()
    flask.session['email'] = user_info['email']
    flask.session['name'] = user_info['name']
    flask.session['picture'] = user_info['picture']
    flask.session['id'] = user_info['id']
    return flask.redirect(url_for("serve"))

@app.route("/account", methods = ['POST','GET'])
def account():
    if request.method == 'GET':
        results=list(mycol_results.find({"id": flask.session["id"]},{"_id":0}))
        errors_list = list(mycol_errors.find({"id": flask.session["id"]},{}))
        return flask.render_template("account.html", name=flask.session['name'], email = flask.session['email'], picture = flask.session['picture'], results=results, errors=errors_list)
    if request.method == 'POST':
        print("flask.session during ACCOUNT POST: ", flask.session)  # Debugging print statement
        if 'credentials' not in flask.session:
            return flask.redirect('authorize')
        result = request.form
        print(result)
        flask.session['columnTo'] = result["columnTo"]
        flask.session['columnSubject'] = result["columnSubject"]
        flask.session['columnBody'] = result["columnBody"]
        flask.session['rangeFirst'] = result["rangeFirst"]
        flask.session['rangeLast'] = result["rangeLast"]
        flask.session['sheetName'] = result["sheetName"]
        pp=str(result["link"]).rsplit('/',2)[1:]
        flask.session['sheetId'] = pp[0]
        succes_result = {}

        list_results = []
        
        # Load credentials from the session.
        credentials = google.oauth2.credentials.Credentials(
            **flask.session['credentials'])

        sheet = googleapiclient.discovery.build(API_NAME_SHEETS, API_VERSION_SHEETS, credentials=credentials)
        email = googleapiclient.discovery.build(API_NAME_EMAIL, API_VERSION_EMAIL, credentials=credentials)

        response_recipients = sheet.spreadsheets().values().get(
            spreadsheetId = flask.session['sheetId'],
            majorDimension = 'ROWS',
            range = flask.session['sheetName']+"!"+flask.session['columnTo']+flask.session['rangeFirst']+":"+flask.session['columnTo']+flask.session['rangeLast']
        ).execute()

        response_body_text = sheet.spreadsheets().values().get(
            spreadsheetId = flask.session['sheetId'],
            majorDimension = 'ROWS',
            range = flask.session['sheetName']+"!"+flask.session['columnBody']+flask.session['rangeFirst']+":"+flask.session['columnBody']+flask.session['rangeLast']
        ).execute()

        response_subject_text = sheet.spreadsheets().values().get(
            spreadsheetId = flask.session['sheetId'],
            majorDimension = 'ROWS',
            range = flask.session['sheetName']+"!"+flask.session['columnSubject']+flask.session['rangeFirst']+":"+flask.session['columnSubject']+flask.session['rangeLast']
        ).execute()

        thr = Thread(target=send_email, args=(response_recipients, response_subject_text, response_body_text, succes_result, list_results, email, app, flask.session['id']))
        thr.start()
        flask.session['credentials'] = credentials_to_dict(credentials)
        flask.session['list_results'] = list_results
        return flask.redirect(url_for("account"))
    
@app.route('/clear', methods=['POST', 'GET'])
def clear():
    if request.method == 'GET':
        if 'credentials' not in flask.session:
            return flask.redirect(url_for("serve"))
        return flask.render_template("logout.html")
    
    if request.method == 'POST':
        if 'credentials' in flask.session:
            flask.session.clear()
            return flask.redirect(url_for("serve"))
        return flask.redirect(url_for("serve"))
           
def send_email(response_recipients, response_subject_text, response_body_text, success_result, list_results, email, app, user_id):
    with app.app_context():
        i = 0
        for recipient, subject, body in zip(response_recipients['values'], response_subject_text['values'], response_body_text['values']):
            print()
            print(recipient)
            print(subject)
            print(body)
            recipient = recipient
            mimeMessage = MIMEMultipart()
            if len(recipient) == 0:
                continue

            mimeMessage['to'] = recipient[0]
            mimeMessage['subject'] = subject[0]

            body_space = body[0].replace("\n", "<br/>")

            html = f'''
                    <html>
                        <body>
                            <p>{body_space}</p>
                        </body>
                    </html>
                    '''
            success_result["recipient"] = recipient
            success_result["subject"] = subject
            success_result["status"] = "SENT"
            success_result["id"] = user_id
            try:
                mimeMessage.attach(MIMEText(html, "html"))
                raw_string = base64.urlsafe_b64encode(mimeMessage.as_bytes()).decode()
                message = email.users().messages().send(userId='me', body={'raw': raw_string}).execute()
            except googleapiclient.errors.HttpError as e:
                result_error = str(e).find("Invalid To header")
                result_error429 = str(e).find("429")
                if result_error != -1:
                    success_result["status"] = "Invalid email"
                if result_error429 != -1:
                    success_result["status"] = "Daily limit"
                print(result_error)
            list_results.append(success_result.copy())
            mycol_results.insert_one(success_result.copy())
            i = i + 1
            time.sleep(1)

        print("Finished")
        print(i)

def credentials_to_dict(credentials):
  return {'token': credentials.token,
          'refresh_token': credentials.refresh_token,
          'token_uri': credentials.token_uri,
          'client_id': credentials.client_id,
          'client_secret': credentials.client_secret,
          'scopes': credentials.scopes}

if __name__ == '__main__':
    app.run(threaded=True, processes=1)