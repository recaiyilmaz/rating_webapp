from flask import Flask, render_template, request, redirect, url_for, session, Response
from googleapiclient.http import MediaIoBaseDownload
import pandas as pd
import os, io, csv
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2 import service_account
import requests, glob
import json, random
from datetime import datetime

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

# Session variable to store interval ratings between requests
interval_ratings = {}


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

    total_videos = len(df)
    rated_videos = index
    videos_left = total_videos - rated_videos

    if index >= total_videos:
        return "All videos have been rated!"

    video_id = df['id'].iloc[index]
    random_id = random.randint(10000, 99999)
    video_path = f'static/current_video{random_id}.mp4'
    download_file_from_drive(video_id, video_path)
    print(f'This is the video we work on {video_id}')

    return render_template(
        'rate.html', video_file=video_path.split('static/')[1],
        rated_videos=rated_videos, total_videos=total_videos, videos_left=videos_left
    )


# -----------------------------
# SAVE INTERVAL RATINGS
# -----------------------------
@app.route('/submit_ratings', methods=['POST'])
def submit_ratings():
    if 'user' not in session:
        return redirect(url_for('login'))

    user = session['user']

    # Get the ratings data from the form
    ratings_json = request.form.get('all_ratings')
    ratings_data = json.loads(ratings_json)

    # Store in session for later use with category ratings
    # Convert to a format that can be stored in session
    session['interval_ratings'] = ratings_json

    # Return empty 204 response
    return Response(status=204)


# -----------------------------
# SAVE CATEGORY RATINGS AND UPDATE CSV
# -----------------------------
@app.route('/submit_category_ratings', methods=['POST'])
def submit_category_ratings():
    if 'user' not in session:
        return redirect(url_for('login'))

    user = session['user']
    folder_id = rater_drive_folders[user]

    # Retrieve interval ratings from session
    if 'interval_ratings' not in session:
        return "Error: Interval ratings not found. Please rate the intervals first."

    interval_ratings_json = session['interval_ratings']
    interval_ratings = json.loads(interval_ratings_json)

    # Get the category ratings data from the form
    category_ratings_json = request.form.get('category_ratings')
    category_data = json.loads(category_ratings_json)
    category_ratings = category_data['categoryRatings']

    # Find and download CSV file
    csv_file = find_csv_file_in_drive(folder_id)
    if not csv_file:
        return f"Error: No CSV found for user: {user}"

    csv_path = f'static/{user}_RaterFile.csv'  # already downloaded above

    # Read the CSV
    df = pd.read_csv(csv_path)

    # Get current video index and ID
    current_index = int(df['where_we_left'].iloc[0])

    # Update interval ratings in CSV
    # Map the interval keys to column names
    interval_mapping = {
        '0-15': '0-15',
        '15-30': '15-30',
        '30-45': '30-45',
        '45-60': '45-60',
        '60-75': '60-75',
        '75-90': '75-90',
        '90-105': '90-105',
        '105-120': '105-120'
    }

    # Update interval ratings in the CSV
    for interval_key, rating_data in interval_ratings.items():
        col_name = interval_mapping.get(interval_key)
        if col_name and col_name in df.columns:
            df.at[current_index, col_name] = rating_data['rating']

    # Update category ratings in CSV
    category_mapping = {
        'RespectForTissue': 'Respect for Tissue',
        'Hemostasis': 'Hemostasis',
        'InstrumentHandling': 'Instrument Handling',
        'EconomyOfMovement': 'Economy of Movement',
        'Flow': 'Flow',
        'Overall': 'Overall'
    }

    for category_key, category_name in category_mapping.items():
        if category_key in category_ratings and category_name in df.columns:
            df.at[current_index, category_name] = category_ratings[category_key]

    # Update date of rating
    if 'Date of Rating' in df.columns:
        df.at[current_index, 'Date of Rating'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Update the progress counter
    df.at[0, 'where_we_left'] = current_index + 1

    # Save updated CSV
    df.to_csv(csv_path, index=False)

    # Upload updated CSV back to Google Drive
    update_csv_in_drive(csv_path, csv_file['id'])

    # Clear the session ratings
    if 'interval_ratings' in session:
        session.pop('interval_ratings')

    mp4_files = glob.glob(os.path.join('static', "current_video*"))
    for file_path in mp4_files:
        os.remove(file_path)
        print(f"Deleted: {file_path}")

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