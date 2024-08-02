from flask import Flask, redirect, url_for, session, request, render_template
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
    return render_template('index.html')

@app.route('/login')
def login():
    sp_oauth = get_spotify_oauth()
    auth_url = sp_oauth.get_authorize_url()
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
    user_id = sp.current_user()['id']
    playlist_id = get_playlist_id(sp, user_id)
    playlist_name = None

    if playlist_id:
        playlist = sp.playlist(playlist_id)
        playlist_name = playlist['name']

    return render_template('options.html', playlist_exists=bool(playlist_id), playlist_name=playlist_name)

@app.route('/create_playlist')
def create_playlist():
    if 'token_info' not in session:
        return redirect(url_for('login'))
    
    token_info = session['token_info']
    sp = Spotify(auth=token_info['access_token'])

    # Determine the playlist name for the last month
    user_id = sp.current_user()['id']
    now = datetime.datetime.now()
    last_month = now - relativedelta(months=1)
    playlist_name = f"My Monthly Top Tracks - {last_month.strftime('%B %Y')}"
    playlist_description = "This playlist was created automatically using this: https://shorturl.at/KUHCh"

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
    playlist_description = "This playlist was created automatically using this: https://shorturl.at/KUHCh"

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
    if 'token_info' not in session:
        return redirect(url_for('login'))

    token_info = session['token_info']
    sp = Spotify(auth=token_info['access_token'])
    user_id = sp.current_user()['id']
    playlist_id = get_playlist_id(sp, user_id)

    if playlist_id:
        sp.current_user_unfollow_playlist(playlist_id)
        message = "Playlist deleted successfully."
    else:
        message = "No playlist found to delete."

    return render_template('options.html', message=message, playlist_exists=False)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/signup_auto_update')
def signup_auto_update():
    # Placeholder for future implementation
    return "Sign up for automatic monthly updates feature is coming soon!"

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)