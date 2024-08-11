from flask import Flask, redirect, url_for, request, render_template, session, flash, jsonify
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from flask_sqlalchemy import SQLAlchemy
from spotipy.oauth2 import SpotifyOAuth
import spotipy
import os
import datetime
from dateutil.relativedelta import relativedelta
import urllib.parse
import uuid
import requests

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your_secret_key')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///users.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize Spotify OAuth
def create_spotify_oauth():
    return SpotifyOAuth(
        client_id=os.getenv('SPOTIPY_CLIENT_ID'),
        client_secret=os.getenv('SPOTIPY_CLIENT_SECRET'),
        redirect_uri=os.getenv('SPOTIPY_REDIRECT_URI'),
        scope='playlist-modify-public playlist-modify-private user-library-read'
    )

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login')
def login():
    authentication_request_params = {
        'response_type': 'code',
        'client_id': os.getenv('SPOTIPY_CLIENT_ID'),
        'redirect_uri': os.getenv('SPOTIPY_REDIRECT_URI'),
        'scope': 'playlist-modify-public playlist-modify-private user-library-read',
        'state': str(uuid.uuid4()),
        'show_dialog': 'true'
    }
    auth_url = 'https://accounts.spotify.com/authorize/?' + urllib.parse.urlencode(authentication_request_params)

def get_access_token(authorization_code:str):
    spotify_request_access_token_url = 'https://accounts.spotify.com/api/token/?'
    body = {
        'grant_type': 'authorization_code',
        'code': 'authorization_code',
        'client_id': os.getenv('SPOTIPY_CLIENT_ID'),
        'client_secret': os.getenv('SPOTIPY_CLIENT_SECRET'),
        'redirect_uri': os.getenv('SPOTIPY_REDIRECT_URI')
    }
    response = requests.post(spotify_request_access_token_url, data = body)
    if response.status_code == 200:
        return response.json()  
        raise Exception ('Failed to obtain Access token')

@app.route('/callback')
def callback():
    code = request.args.get('code')
    credentials = get_access_token(authorization_code=code)
    os.environ['token'] = credentials['access_token']

    return redirect(url_for('create_or_update_playlist'))

@app.route('/create_or_update_playlist')
@login_required
def create_or_update_playlist():
    access_token = current_user.access_token
    sp = spotipy.Spotify(auth=access_token)
    playlist_id = get_playlist_id(sp, current_user.spotify_user_id)
    playlist_name = None

    if playlist_id:
        playlist = sp.playlist(playlist_id)
        playlist_name = playlist['name']

    return render_template('options.html', playlist_exists=bool(playlist_id), playlist_name=playlist_name)

@app.route('/create_playlist')
@login_required
def create_playlist():
    access_token = current_user.access_token
    sp = spotipy.Spotify(auth=access_token)

    now = datetime.datetime.now()
    last_month = now - relativedelta(months=1)
    playlist_name = f"My Monthly Top Tracks - {last_month.strftime('%B %Y')}"
    playlist_description = "This playlist was created automatically using this: https://spotify-top-monthly-playlist.onrender.com/"

    playlist_id = get_playlist_id(sp, current_user.spotify_user_id, playlist_prefix=playlist_name)
    if playlist_id:
        message = f"Playlist '{playlist_name}' already exists."
        playlist_url = f"https://open.spotify.com/playlist/{playlist_id}"
    else:
        results = sp.current_user_top_tracks(time_range='short_term', limit=50)
        top_tracks = [track['uri'] for track in results['items']]
        playlist = sp.user_playlist_create(current_user.spotify_user_id, playlist_name, public=True, description=playlist_description)
        sp.playlist_add_items(playlist['id'], top_tracks)
        playlist_id = get_playlist_id(sp, current_user.spotify_user_id, playlist_prefix=playlist_name)
        message = f"Playlist '{playlist_name}' created successfully!"
        playlist_url = f"https://open.spotify.com/playlist/{playlist_id}"

    return render_template('created_playlist.html', message=message, playlist_exists=True, playlist_name=playlist_name, playlist_url=playlist_url)

@app.route('/update_playlist')
@login_required
def update_playlist():
    access_token = current_user.access_token
    sp = spotipy.Spotify(auth=access_token)

    results = sp.current_user_top_tracks(time_range='short_term', limit=50)
    top_tracks = [track['uri'] for track in results['items']]
    now = datetime.datetime.now()
    last_month = now - relativedelta(months=1)
    playlist_name = f"My Monthly Top Tracks - {last_month.strftime('%B %Y')}"
    playlist_description = "This playlist was created automatically using this: https://spotify-top-monthly-playlist.onrender.com/"

    playlist_id = get_playlist_id(sp, current_user.spotify_user_id)
    if playlist_id:
        sp.user_playlist_change_details(current_user.spotify_user_id, playlist_id, name=playlist_name, description=playlist_description)
        sp.playlist_replace_items(playlist_id, top_tracks)
        message = f"Playlist '{playlist_name}' updated successfully!"
        playlist_url = f"https://open.spotify.com/playlist/{playlist_id}"
        return render_template('updated_playlist.html', message=message, playlist_exists=True, playlist_name=playlist_name, playlist_url=playlist_url)
    else:
        message = f"No existing playlist to update."
        return render_template('options.html', message=message)

@app.route('/delete_playlist')
@login_required
def delete_playlist():
    access_token = current_user.access_token
    sp = spotipy.Spotify(auth=access_token)
    playlist_id = get_playlist_id(sp, current_user.spotify_user_id)

    if playlist_id:
        sp.current_user_unfollow_playlist(playlist_id)
        message = "Playlist deleted successfully."
    else:
        message = "No playlist found to delete."

    return render_template('options.html', message=message, playlist_exists=False)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/signup_auto_update')
def signup_auto_update():
    message = "You have successfully signed up for automatic updates!"
    return jsonify({'message': message})

def get_playlist_id(sp, user_id, playlist_prefix='My Monthly Top Tracks'):
    playlists = sp.user_playlists(user_id, limit=50)
    for playlist in playlists['items']:
        if playlist['name'].startswith(playlist_prefix):
            return playlist['id']
    return None

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)