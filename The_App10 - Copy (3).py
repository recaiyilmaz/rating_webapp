from flask import Flask, Response, render_template, request, redirect, url_for, session
from googleapiclient.http import MediaIoBaseDownload
import pandas as pd
import os, io, csv
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2 import service_account
import requests
import json

app = Flask(__name__)
app.secret_key = os.urandom(24)

# -----------------------------
# SET YOUR USERS AND FOLDERS
# -----------------------------
rater_credentials = {
    'RECAI': 'RECAI',
    'DEMO': 'DEMO',
    'DONOHO': 'DONOHO',
    'BAKHAIDAR': 'BAKHAIDAR',
    'ALSAYEGH': 'ALSAYEGH',
    'OBRIEN': 'OBRIEN',
    'KHAN': 'KHAN',
    'ALHANTOOBI': 'ALHANTOOBI',
    'ALMANSOURI': 'ALMANSOURI',
    'SMITH': 'SMITH'
}

rater_drive_folders = {
    'RECAI': '1zKnJZXAJX-ivShT0Hyhk_cgaVPXoTYXl',  # RATER 1 (RECAI)
    'DEMO': '1mbOKAVMCekcsery6MkE-W9YBAamJZRI7',  # RATER 2 (DEMO)
    'DONOHO': '1EXmHX_eYWNcRpYfMRaKbSNn3qtYXj4mF',  # RATER 3 (DONOHO)
    'BAKHAIDAR': '1Hm45hI29P-_mCbf76LuEC9xfWRrlMwUY',  # RATER 4 (BAKHAIDAR)
    'ALSAYEGH': '1d_o8UTelVuZGC-v0nohRoMHtGV2zkCmD',  # RATER 5 (ALSAYEGH)
    'OBRIEN': '1ROw-cJ9YNFMuclxFuJKDzVzmGtpeYqtu',  # RATER 6 (O'BRIEN)
    'KHAN': '1qLklpSpGuCvKu-3wtBtAfjPQ6f-cvWU4',  # RATER 7 (KHAN)
    'ALHANTOOBI': '1Khk_0y_qBnYF8D7UQoU4s0dZjxZLNDHS',  # RATER 8 (ALHANTOOBI)
    'ALMANSOURI': '1R6JUSyi1Pptf1a8zPBYDthjwr7BXOedx',  # RATER 9 (ALMANSOURI)
    'SMITH': '1R8UfpiF33fuey-FVnjh-H3ABOebyQBBa'  # RATER 10 (SMITH)
}

# Load Google Drive API
# ACCESS TO GOOGLE CREDENTIALS
credentials_share_link = 'https://drive.google.com/file/d/180TACdy1uZuFwmAUCtNFJxcW9rvK1Qa2/view?usp=sharing'
credentials_id = credentials_share_link.split('/')[5]
direct_link = f'https://drive.google.com/uc?id={credentials_id}'
response = requests.get(direct_link)
json_string = response.text
credentials_dict = json.loads(json_string)
credentials_json = json.dumps(credentials_dict)
credentials = service_account.Credentials.from_service_account_info(json.loads(credentials_json))
# Create the service client
drive_service = build('drive', 'v3', credentials=credentials)

# -----------------------------
# LOGIN PAGE
# -----------------------------
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username in rater_credentials and rater_credentials[username] == password:
            session['user'] = username
            return redirect(url_for('rate_video'))
        else:
            return render_template('login.html', error='Invalid login')
    return render_template('login.html')

# -----------------------------
# VIDEO RATING PAGE
# -----------------------------
@app.route('/rate', methods=['GET', 'POST'])
def rate_video():
    if 'user' not in session:
        return redirect(url_for('login'))

    user = session['user']
    folder_id = rater_drive_folders[user]

    # Find CSV file in folder
    csv_file = find_csv_file_in_drive(folder_id)
    if not csv_file:
        return f"No CSV found for user: {user}"

    # Download and read CSV
    csv_path = f'static/{user}_RaterFile.csv'
    download_file_from_drive(csv_file['id'], csv_path)

    df = pd.read_csv(csv_path)
    if 'where_we_left' not in df.columns or 'id' not in df.columns:
        return "CSV file must have 'id' and 'where_we_left' columns"

    index = int(df['where_we_left'].iloc[0])
    if index >= len(df):
        return "All videos have been rated!"

    video_id = df['id'].iloc[index]
    video_path = f'static/current_video.mp4'
    download_file_from_drive(video_id, video_path)

    return render_template('rate.html', video_file=video_path.split('static/')[1])

# -----------------------------
# SAVE INTERVAL RATINGS
# -----------------------------
@app.route('/submit_ratings', methods=['POST'])
def submit_ratings():
    if 'user' not in session:
        return redirect(url_for('login'))

    user = session['user']
    folder_id = rater_drive_folders[user]

    # Get the ratings data from the form
    ratings_json = request.form.get('all_ratings')
    ratings_data = json.loads(ratings_json)

    # Find and download CSV file
    csv_file = find_csv_file_in_drive(folder_id)
    if not csv_file:
        return f"Error: No CSV found for user: {user}"

    csv_path = f'static/{user}_RaterFile.csv'
    download_file_from_drive(csv_file['id'], csv_path)

    # Read the CSV
    df = pd.read_csv(csv_path)

    # Get current video index
    index = int(df['where_we_left'].iloc[0])
    video_id = df['id'].iloc[index]

    # Create ratings filename
    ratings_filename = f"{user}_video_{index}_ratings.json"
    ratings_path = f"static/{ratings_filename}"

    # Save ratings to file
    with open(ratings_path, 'w') as f:
        f.write(ratings_json)

    # Upload ratings to Google Drive
    upload_file_to_drive(ratings_path, ratings_filename, folder_id)

    # Return empty 204 response
    return Response(status=204)

# -----------------------------
# SAVE CATEGORY RATINGS
# -----------------------------
@app.route('/submit_category_ratings', methods=['POST'])
def submit_category_ratings():
    if 'user' not in session:
        return redirect(url_for('login'))

    user = session['user']
    folder_id = rater_drive_folders[user]

    # Get the category ratings data from the form
    category_ratings_json = request.form.get('category_ratings')
    category_ratings_data = json.loads(category_ratings_json)

    # Find and download CSV file
    csv_file = find_csv_file_in_drive(folder_id)
    if not csv_file:
        return f"Error: No CSV found for user: {user}"

    csv_path = f'static/{user}_RaterFile.csv'
    download_file_from_drive(csv_file['id'], csv_path)

    # Read the CSV
    df = pd.read_csv(csv_path)

    # Get current video index
    index = int(df['where_we_left'].iloc[0])
    video_id = df['id'].iloc[index]

    # Create category ratings filename
    category_ratings_filename = f"{user}_video_{index}_category_ratings.json"
    category_ratings_path = f"static/{category_ratings_filename}"

    # Save category ratings to file
    with open(category_ratings_path, 'w') as f:
        f.write(category_ratings_json)

    # Upload category ratings to Google Drive
    upload_file_to_drive(category_ratings_path, category_ratings_filename, folder_id)

    # Update the progress in CSV
    df.at[0, 'where_we_left'] = index + 1
    df.to_csv(csv_path, index=False)

    # Upload updated CSV to Google Drive
    update_csv_in_drive(csv_path, csv_file['id'])

    # Redirect to the next video
    return redirect(url_for('rate_video'))

# -----------------------------
# DOWNLOAD FILE FROM DRIVE
# -----------------------------
def download_file_from_drive(file_id, dest_path):
    request = drive_service.files().get_media(fileId=file_id)
    fh = io.FileIO(dest_path, 'wb')
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while done is False:
        status, done = downloader.next_chunk()

# -----------------------------
# UPLOAD FILE TO DRIVE
# -----------------------------
def upload_file_to_drive(file_path, file_name, folder_id):
    file_metadata = {
        'name': file_name,
        'parents': [folder_id]
    }

    media = MediaFileUpload(file_path, mimetype='application/json')
    file = drive_service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id'
    ).execute()

    return file.get('id')

# -----------------------------
# UPDATE CSV IN DRIVE
# -----------------------------
def update_csv_in_drive(csv_path, file_id):
    media = MediaFileUpload(csv_path, mimetype='text/csv')
    file = drive_service.files().update(
        fileId=file_id,
        media_body=media
    ).execute()

    return file.get('id')

# -----------------------------
# FIND CSV FILE IN DRIVE FOLDER
# -----------------------------
def find_csv_file_in_drive(folder_id):
    query = f"'{folder_id}' in parents and mimeType='text/csv'"
    results = drive_service.files().list(q=query, fields="files(id, name)").execute()
    files = results.get('files', [])
    for file in files:
        if file['name'] == 'RaterFile.csv':
            return file
    return None

if __name__ == '__main__':
    app.run(debug=True)