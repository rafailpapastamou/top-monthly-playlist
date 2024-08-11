from flask import Flask, redirect, url_for, request, render_template
import spotipy
import os
import datetime
from dateutil.relativedelta import relativedelta
import urllib.parse
import uuid
import requests

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your_secret_key')

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
    return redirect(auth_url)

def get_access_token(authorization_code: str):
    spotify_request_access_token_url = 'https://accounts.spotify.com/api/token'
    body = {
        'grant_type': 'authorization_code',
        'code': authorization_code,
        'client_id': os.getenv('SPOTIPY_CLIENT_ID'),
        'client_secret': os.getenv('SPOTIPY_CLIENT_SECRET'),
        'redirect_uri': os.getenv('SPOTIPY_REDIRECT_URI')
    }
    response = requests.post(spotify_request_access_token_url, data=body)
    if response.status_code == 200:
        return response.json()
    else:
        raise Exception('Failed to obtain Access token')

@app.route('/callback')
def callback():
    code = request.args.get('code')
    credentials = get_access_token(authorization_code=code)
    
    # Store access token in environment variable
    os.environ['token'] = credentials['access_token']

    return redirect(url_for('create_or_update_playlist'))

@app.route('/create_or_update_playlist')
def create_or_update_playlist():
    access_token = os.getenv('token')
    if not access_token:
        return redirect(url_for('login'))

    sp = spotipy.Spotify(auth=access_token)
    
    # Fetch the user's Spotify ID
    user_profile = sp.current_user()
    spotify_user_id = user_profile['id']

    playlist_id = get_playlist_id(sp, spotify_user_id)
    playlist_name = None

    if playlist_id:
        playlist = sp.playlist(playlist_id)
        playlist_name = playlist['name']

    return render_template('options.html', playlist_exists=bool(playlist_id), playlist_name=playlist_name)

@app.route('/create_playlist')
def create_playlist():
    access_token = os.getenv('token')
    if not access_token:
        return redirect(url_for('login'))

    sp = spotipy.Spotify(auth=access_token)
    
    # Fetch the user's Spotify ID
    user_profile = sp.current_user()
    spotify_user_id = user_profile['id']

    now = datetime.datetime.now()
    last_month = now - relativedelta(months=1)
    playlist_name = f"My Monthly Top Tracks - {last_month.strftime('%B %Y')}"
    playlist_description = "This playlist was created automatically."

    playlist_id = get_playlist_id(sp, spotify_user_id, playlist_prefix=playlist_name)
    if playlist_id:
        message = f"Playlist '{playlist_name}' already exists."
        playlist_url = f"https://open.spotify.com/playlist/{playlist_id}"
    else:
        results = sp.current_user_top_tracks(time_range='short_term', limit=50)
        top_tracks = [track['uri'] for track in results['items']]
        playlist = sp.user_playlist_create(spotify_user_id, playlist_name, public=True, description=playlist_description)
        sp.playlist_add_items(playlist['id'], top_tracks)
        playlist_id = get_playlist_id(sp, spotify_user_id, playlist_prefix=playlist_name)
        message = f"Playlist '{playlist_name}' created successfully!"
        playlist_url = f"https://open.spotify.com/playlist/{playlist_id}"

    return render_template('created_playlist.html', message=message, playlist_exists=True, playlist_name=playlist_name, playlist_url=playlist_url)

@app.route('/update_playlist')
def update_playlist():
    access_token = os.getenv('token')
    if not access_token:
        return redirect(url_for('login'))

    sp = spotipy.Spotify(auth=access_token)
    
    # Fetch the user's Spotify ID
    user_profile = sp.current_user()
    spotify_user_id = user_profile['id']

    results = sp.current_user_top_tracks(time_range='short_term', limit=50)
    top_tracks = [track['uri'] for track in results['items']]
    now = datetime.datetime.now()
    last_month = now - relativedelta(months=1)
    playlist_name = f"My Monthly Top Tracks - {last_month.strftime('%B %Y')}"
    playlist_description = "This playlist was created automatically."

    playlist_id = get_playlist_id(sp, spotify_user_id)
    if playlist_id:
        sp.user_playlist_change_details(spotify_user_id, playlist_id, name=playlist_name, description=playlist_description)
        sp.playlist_replace_items(playlist_id, top_tracks)
        message = f"Playlist '{playlist_name}' updated successfully!"
        playlist_url = f"https://open.spotify.com/playlist/{playlist_id}"
        return render_template('updated_playlist.html', message=message, playlist_exists=True, playlist_name=playlist_name, playlist_url=playlist_url)
    else:
        message = f"No existing playlist to update."
        return render_template('options.html', message=message)

@app.route('/delete_playlist')
def delete_playlist():
    access_token = os.getenv('token')
    if not access_token:
        return redirect(url_for('login'))

    sp = spotipy.Spotify(auth=access_token)
    
    # Fetch the user's Spotify ID
    user_profile = sp.current_user()
    spotify_user_id = user_profile['id']

    playlist_id = get_playlist_id(sp, spotify_user_id)

    if playlist_id:
        sp.current_user_unfollow_playlist(playlist_id)
        message = "Playlist deleted successfully."
    else:
        message = "No playlist found to delete."

    return render_template('options.html', message=message, playlist_exists=False)

@app.route('/logout')
def logout():
    # Clear the token from the environment variable (optional)
    os.environ.pop('token', None)
    return redirect(url_for('index'))

def get_playlist_id(sp, user_id, playlist_prefix='My Monthly Top Tracks'):
    playlists = sp.user_playlists(user_id, limit=50)
    for playlist in playlists['items']:
        if playlist['name'].startswith(playlist_prefix):
            return playlist['id']
    return None

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
