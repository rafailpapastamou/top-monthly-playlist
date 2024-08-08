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
sp_oauth = SpotifyOAuth(
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
    if 'token_info' in session:
        return redirect(url_for('create_or_update_playlist'))

    auth_url = sp_oauth.get_authorize_url()
    return redirect(auth_url)

@app.route('/callback')
def callback():
    token_info = sp_oauth.get_access_token(request.args['code'])
    if not token_info:
        return redirect(url_for('login'))

    session['token_info'] = token_info
    return redirect(url_for('create_or_update_playlist'))

@app.route('/create_or_update_playlist')
def create_or_update_playlist():
    if 'token_info' not in session:
        return redirect(url_for('login'))

    token_info = session['token_info']
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
    if 'token_info' not in session:
        return redirect(url_for('login'))
    
    token_info = session['token_info']
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
    if 'token_info' not in session:
        return redirect(url_for('login'))
    
    token_info = session['token_info']
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
    if 'token_info' not in session:
        return redirect(url_for('login'))

    token_info = session['token_info']
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

@app.template_filter('json_pretty')
def json_pretty_filter(value):
    return json.dumps(value, indent=4, sort_keys=True)

def get_playlist_id(sp, user_id, playlist_prefix='My Monthly Top Tracks'):
    playlists = sp.user_playlists(user_id, limit=50)
    for playlist in playlists['items']:
        if playlist['name'].startswith(playlist_prefix):
            return playlist['id']
    return None

if __name__ == '__main__':
    app.run(debug=True)