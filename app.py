from flask import Flask, redirect, url_for, session, request
from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth
import os
import datetime
from dotenv import load_dotenv
from dateutil.relativedelta import relativedelta

load_dotenv('variables.env')

app = Flask(__name__)
app.secret_key = os.urandom(24)

def get_spotify_oauth():
    redirect_uri = url_for('callback', _external=True)
    print(f"Redirect URI used: {redirect_uri}")  # Debug statement
    return SpotifyOAuth(
        client_id=os.getenv('SPOTIPY_CLIENT_ID'),
        client_secret=os.getenv('SPOTIPY_CLIENT_SECRET'),
        redirect_uri=redirect_uri,
        scope='user-top-read playlist-modify-public playlist-modify-private'
    )

def get_playlist_id(sp, user_id, playlist_prefix="My Monthly Top Tracks"):
    playlists = sp.user_playlists(user_id)
    for playlist in playlists['items']:
        if playlist['name'].startswith(playlist_prefix):
            return playlist['id']
    return None

@app.route('/')
def index():
    return '<a href="/login">Login with Spotify</a>'

@app.route('/login')
def login():
    sp_oauth = get_spotify_oauth()
    auth_url = sp_oauth.get_authorize_url()
    print(f"Authorization URL: {auth_url}")  # Debug statement
    return redirect(auth_url)

@app.route('/callback')
def callback():
    sp_oauth = get_spotify_oauth()
    code = request.args.get('code')
    token_info = sp_oauth.get_access_token(code)
    
    session['token_info'] = token_info
    return redirect(url_for('create_or_update_playlist'))

@app.route('/create_or_update_playlist')
def create_or_update_playlist():
    if 'token_info' not in session:
        return redirect(url_for('login'))
    
    token_info = session['token_info']
    sp = Spotify(auth=token_info['access_token'])

    # Get the top tracks of the last month
    results = sp.current_user_top_tracks(time_range='short_term', limit=50)
    top_tracks = [track['uri'] for track in results['items']]

    # Determine the playlist name for the last month
    user_id = sp.current_user()['id']
    now = datetime.datetime.now()
    last_month = now - relativedelta(months=1)
    playlist_name = f"My Monthly Top Tracks - {last_month.strftime('%B %Y')}"
    playlist_description = "This playlist was created automatically using a script."

    # Check if the playlist already exists
    playlist_id = get_playlist_id(sp, user_id)
    if playlist_id:
        # Playlist exists, update its name and tracks
        sp.user_playlist_change_details(user_id, playlist_id, name=playlist_name, description=playlist_description)
        sp.playlist_replace_items(playlist_id, top_tracks)
    else:
        # Playlist does not exist, create a new one
        playlist = sp.user_playlist_create(user_id, playlist_name, public=True, description=playlist_description)
        sp.playlist_add_items(playlist['id'], top_tracks)

    return f"Playlist '{playlist_name}' created or updated successfully!"

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)