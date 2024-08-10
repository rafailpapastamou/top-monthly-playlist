from flask import Flask, redirect, url_for, session, request, render_template
import os
import datetime
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import spotipy.util as util
from dateutil.relativedelta import relativedelta
from dotenv import load_dotenv

load_dotenv('variables.env')

app = Flask(__name__)
app.secret_key = os.urandom(24)

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
    sp_oauth = create_spotify_oauth()
    auth_url = sp_oauth.get_authorize_url()
    return redirect(auth_url)

@app.route('/callback')
def callback():
    sp_oauth = create_spotify_oauth()
    code = request.args.get('code')

    if not code:
        return redirect(url_for('login'))

    token_info = sp_oauth.get_access_token(code)

    if not token_info:
        return redirect(url_for('login'))

    sp = spotipy.Spotify(auth=token_info['access_token'])
    user_id = sp.current_user()['id']

    # Use user-specific session keys
    session[f'{user_id}_token_info'] = token_info
    session.modified = True  # Ensure session data is saved
    return redirect(url_for('create_or_update_playlist', user_id=user_id))

@app.route('/create_or_update_playlist')
def create_or_update_playlist():
    user_id = request.args.get('user_id')
    token_info = get_token(user_id)

    if not token_info:
        return redirect(url_for('login'))
    
    sp = spotipy.Spotify(auth=token_info['access_token'])
    playlist_id = get_playlist_id(sp, user_id)
    playlist_name = None

    if playlist_id:
        playlist = sp.playlist(playlist_id)
        playlist_name = playlist['name']

    return render_template('options.html', playlist_exists=bool(playlist_id), playlist_name=playlist_name, user_id=user_id)

def get_token(user_id):
    token_info = session.get(f'{user_id}_token_info', None)
    if not token_info:
        return None

    now = datetime.datetime.now()
    is_expired = token_info['expires_at'] - now.timestamp() < 60

    if is_expired:
        sp_oauth = create_spotify_oauth()
        token_info = sp_oauth.refresh_access_token(token_info['refresh_token'])
        session[f'{user_id}_token_info'] = token_info

    return token_info

@app.route('/logout')
def logout():
    user_id = request.args.get('user_id')
    if user_id:
        session.pop(f'{user_id}_token_info', None)  # Remove the specific user's token info
    return redirect(url_for('index'))

@app.route('/signup_auto_update')
def signup_auto_update():
    message = "You have successfully signed up for automatic updates!"

def get_playlist_id(sp, user_id, playlist_prefix='My Monthly Top Tracks'):
    playlists = sp.user_playlists(user_id, limit=50)
    for playlist in playlists['items']:
        if playlist['name'].startswith(playlist_prefix):
            return playlist['id']
    return None

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)