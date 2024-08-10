from flask import Flask, redirect, url_for, session, request, render_template
import os
import datetime
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from dateutil.relativedelta import relativedelta
import sqlite3
import json

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

    # Save token info to the database
    save_token(user_id, token_info)
    
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

@app.route('/create_playlist')
def create_playlist():
    user_id = request.args.get('user_id')
    token_info = get_token(user_id)

    if not token_info:
        return redirect(url_for('login'))
    
    sp = spotipy.Spotify(auth=token_info['access_token'])

    # Determine the playlist name for the last month
    now = datetime.datetime.now()
    last_month = now - relativedelta(months=1)
    playlist_name = f"My Monthly Top Tracks - {last_month.strftime('%B %Y')}"
    playlist_description = "This playlist was created automatically using this: https://spotify-top-monthly-playlist.onrender.com/"

    # Check if the playlist already exists
    playlist_id = get_playlist_id(sp, user_id, playlist_prefix=playlist_name)
    if playlist_id:
        message = f"Playlist '{playlist_name}' already exists."
        playlist_url = f"https://open.spotify.com/playlist/{playlist_id}"
    else:
        # Get the top tracks of the last month
        results = sp.current_user_top_tracks(time_range='short_term', limit=50)
        top_tracks = [track['uri'] for track in results['items']]

        # Create a new playlist
        playlist = sp.user_playlist_create(user_id, playlist_name, public=True, description=playlist_description)
        sp.playlist_add_items(playlist['id'], top_tracks)
        playlist_id = get_playlist_id(sp, user_id, playlist_prefix=playlist_name)
        message = f"Playlist '{playlist_name}' created successfully!"
        playlist_url = f"https://open.spotify.com/playlist/{playlist_id}"

    return render_template('created_playlist.html', message=message, playlist_exists=True, playlist_name=playlist_name, playlist_url=playlist_url)

@app.route('/update_playlist')
def update_playlist():
    user_id = request.args.get('user_id')
    token_info = get_token(user_id)

    if not token_info:
        return redirect(url_for('login'))
    
    sp = spotipy.Spotify(auth=token_info['access_token'])

    # Get the top tracks of the last month
    results = sp.current_user_top_tracks(time_range='short_term', limit=50)
    top_tracks = [track['uri'] for track in results['items']]

    # Determine the playlist name for the last month
    now = datetime.datetime.now()
    last_month = now - relativedelta(months=1)
    playlist_name = f"My Monthly Top Tracks - {last_month.strftime('%B %Y')}"
    playlist_description = "This playlist was created automatically using this: https://spotify-top-monthly-playlist.onrender.com/"

    # Check if the playlist already exists
    playlist_id = get_playlist_id(sp, user_id)
    if playlist_id:
        sp.user_playlist_change_details(user_id, playlist_id, name=playlist_name, description=playlist_description)
        sp.playlist_replace_items(playlist_id, top_tracks)
        message = f"Playlist '{playlist_name}' updated successfully!"
        playlist_url = f"https://open.spotify.com/playlist/{playlist_id}"
        return render_template('updated_playlist.html', message=message, playlist_exists=True, playlist_name=playlist_name, playlist_url=playlist_url)
    else:
        message = f"No existing playlist to update."
        return render_template('options.html', message=message)

@app.route('/delete_playlist')
def delete_playlist():
    user_id = request.args.get('user_id')
    token_info = get_token(user_id)

    if not token_info:
        return redirect(url_for('login'))
    
    sp = spotipy.Spotify(auth=token_info['access_token'])
    playlist_id = get_playlist_id(sp, user_id)

    if playlist_id:
        sp.current_user_unfollow_playlist(playlist_id)
        message = "Playlist deleted successfully."
    else:
        message = "No playlist found to delete."

    return render_template('options.html', message=message, playlist_exists=False)

@app.route('/logout')
def logout():
    user_id = request.args.get('user_id')
    if user_id:
        # Remove the token from the database
        delete_token(user_id)
    return redirect(url_for('index'))

@app.route('/signup_auto_update')
def signup_auto_update():
    message = "You have successfully signed up for automatic updates!"

def save_token(user_id, token_info):
    conn = sqlite3.connect('data/tokens.db')  # Ensure the path is correct
    cur = conn.cursor()
    token_info_json = json.dumps(token_info)
    cur.execute('''
        INSERT OR REPLACE INTO tokens (user_id, token_info)
        VALUES (?, ?);
    ''', (user_id, token_info_json))
    conn.commit()
    cur.close()
    conn.close()

def get_token(user_id):
    conn = sqlite3.connect('data/tokens.db')  # Ensure the path is correct
    cur = conn.cursor()
    cur.execute('''
        SELECT token_info FROM tokens WHERE user_id = ?;
    ''', (user_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if row:
        return json.loads(row[0])
    return None

def delete_token(user_id):
    conn = sqlite3.connect('data/tokens.db')  # Ensure the path is correct
    cur = conn.cursor()
    cur.execute('''
        DELETE FROM tokens WHERE user_id = ?;
    ''', (user_id,))
    conn.commit()
    cur.close()
    conn.close()

def get_playlist_id(sp, user_id, playlist_prefix='My Monthly Top Tracks'):
    playlists = sp.user_playlists(user_id, limit=50)
    for playlist in playlists['items']:
        if playlist['name'].startswith(playlist_prefix):
            return playlist['id']
    return None

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)