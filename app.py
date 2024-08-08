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
    session.clear()  # Clear session before setting new one
    token_info = sp_oauth.get_access_token(request.args['code'])

    if not token_info:
        return redirect(url_for('login'))

    session['token_info'] = token_info
    session.modified = True  # Ensure session data is saved
    return redirect(url_for('create_or_update_playlist'))

@app.route('/create_or_update_playlist')
def create_or_update_playlist():

    token_info = get_token()
    if not token_info:
        return redirect(url_for('login'))
    
    sp = spotipy.Spotify(auth=token_info['access_token'])
    user_id = sp.current_user()['id']
    playlist_id = get_playlist_id(sp, user_id)
    playlist_name = None

    if playlist_id:
        playlist = sp.playlist(playlist_id)
        playlist_name = playlist['name']

    return render_template('options.html', playlist_exists=bool(playlist_id), playlist_name=playlist_name)

@app.route('/create_playlist')
def create_playlist():
    token_info = get_token()
    if not token_info:
        return redirect(url_for('login'))
    
    sp = spotipy.Spotify(auth=token_info['access_token'])

    user_id = sp.current_user()['id']
    now = datetime.datetime.now()
    last_month = now - relativedelta(months=1)
    playlist_name = f"My Monthly Top Tracks - {last_month.strftime('%B %Y')}"
    playlist_description = "This playlist was created automatically using this: https://spotify-top-monthly-playlist.onrender.com/"

    playlist_id = get_playlist_id(sp, user_id, playlist_prefix=playlist_name)
    if playlist_id:
        message = f"Playlist '{playlist_name}' already exists."
        playlist_url = f"https://open.spotify.com/playlist/{playlist_id}"
    else:
        results = sp.current_user_top_tracks(time_range='short_term', limit=50)
        top_tracks = [track['uri'] for track in results['items']]

        playlist = sp.user_playlist_create(user_id, playlist_name, description=playlist_description)
        playlist_id = playlist['id']
        sp.playlist_add_items(playlist_id, top_tracks)
        message = f"Playlist '{playlist_name}' created successfully!"
        playlist_url = f"https://open.spotify.com/playlist/{playlist_id}"

    return render_template('created_playlist.html', message=message, playlist_exists=True, playlist_name=playlist_name, playlist_url=playlist_url)

@app.route('/update_playlist')
def update_playlist():
    token_info = get_token()
    if not token_info:
        return redirect(url_for('login'))

    sp = spotipy.Spotify(auth=token_info['access_token'])

    user_id = sp.current_user()['id']
    now = datetime.datetime.now()
    last_month = now - relativedelta(months=1)
    playlist_name = f"My Monthly Top Tracks - {last_month.strftime('%B %Y')}"
    playlist_description = "This playlist was created automatically using this: https://spotify-top-monthly-playlist.onrender.com/"

    playlist_id = get_playlist_id(sp, user_id)
    if playlist_id:
        sp.playlist_change_details(playlist_id, name=playlist_name, description=playlist_description)
        results = sp.current_user_top_tracks(time_range='short_term', limit=50)
        top_tracks = [track['uri'] for track in results['items']]
        sp.playlist_add_items(playlist_id, top_tracks)
        message = f"Playlist '{playlist_name}' updated successfully!"
        playlist_url = f"https://open.spotify.com/playlist/{playlist_id}"
        return render_template('updated_playlist.html', message=message, playlist_exists=True, playlist_name=playlist_name, playlist_url=playlist_url)
    else:
        message = f"No existing playlist to update."
        return render_template('options.html', message=message)

@app.route('/delete_playlist')
def delete_playlist():
    token_info = get_token()
    if not token_info:
        return redirect(url_for('login'))

    sp = spotipy.Spotify(auth=token_info['access_token'])
    user_id = sp.current_user()['id']
    playlist_id = get_playlist_id(sp, user_id)

    if playlist_id:
        sp.playlist_unfollow(playlist_id)
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
    message = "You have successfully signed up for automatic updates!"

def get_token():
  refresh_token = session.get('refresh_token', None)
  if not refresh_token:
    return None

  now = datetime.datetime.now()
  # Check expiry similar to the existing code
  is_expired = token_info['expires_at'] - now.timestamp() < 60

  if is_expired:
    sp_oauth = create_spotify_oauth()
    token_info = sp_oauth.refresh_access_token(refresh_token)
    session['token_info'] = token_info  # Update session with new token info

  return token_info

def get_playlist_id(sp, user_id, playlist_prefix='My Monthly Top Tracks'):
    playlists = sp.user_playlists(user_id, limit=50)
    for playlist in playlists['items']:
        if playlist['name'].startswith(playlist_prefix):
            return playlist['id']
    return None

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)