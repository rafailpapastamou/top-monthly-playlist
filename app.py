from flask import Flask, redirect, url_for, request, render_template, jsonify
import spotipy
import os
import datetime
from dateutil.relativedelta import relativedelta
import urllib.parse
import uuid
import requests
from flask_pymongo import PyMongo

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your_secret_key')

# Configuring the MongoDB Database
mongo_uri = os.getenv('MONGO_URI', 'your_mongodb_connection_string_here')
app.config['MONGO_URI'] = mongo_uri
mongo = PyMongo(app)

# Define the User model for MongoDB
class User:
    def __init__(self, spotify_user_id, access_token, refresh_token=None):
        self.spotify_user_id = spotify_user_id
        self.access_token = access_token
        self.refresh_token = refresh_token

    def to_dict(self):
        return {
            "spotify_user_id": self.spotify_user_id,
            "access_token": self.access_token,
            "refresh_token": self.refresh_token
        }
    
    @staticmethod
    def from_dict(data):
        return User(
            spotify_user_id=data['spotify_user_id'],
            access_token=data['access_token'],
            refresh_token=data.get('refresh_token')
        )

@app.route('/')
def index():
    # Check if the access token exists and is valid
    access_token = os.getenv('token')
    
    if access_token:
        try:
            sp = spotipy.Spotify(auth=access_token)
            sp.current_user()  # Make a simple API call to check if the token is still valid
            return redirect(url_for('create_or_update_playlist'))
        except spotipy.exceptions.SpotifyException:
            # Token is invalid or expired, attempt to refresh it
            user = mongo.db.users.find_one({"access_token": access_token})
            if user:
                new_tokens = refresh_access_token(user['refresh_token'])
                if 'access_token' in new_tokens:
                    user['access_token'] = new_tokens['access_token']
                    mongo.db.users.update_one({"spotify_user_id": user['spotify_user_id']}, {"$set": {"access_token": new_tokens['access_token']}})
                    os.environ['token'] = new_tokens['access_token']
                    return redirect(url_for('create_or_update_playlist'))
            return redirect(url_for('login'))

    return render_template('index.html')

@app.route('/login')
def login():
    authentication_request_params = {
        'response_type': 'code',
        'client_id': os.getenv('SPOTIPY_CLIENT_ID'),
        'redirect_uri': os.getenv('SPOTIPY_REDIRECT_URI'),
        'scope': 'playlist-modify-public playlist-modify-private user-library-read user-top-read',
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
        print("Successfully obtained access and refresh tokens.")
        return response.json()
    else:
        print(f"Failed to obtain access token: {response.content}")
        raise Exception('Failed to obtain Access token')

@app.route('/callback')
def callback():
    code = request.args.get('code')
    credentials = get_access_token(authorization_code=code)
    
    # Store access token in environment variable
    os.environ['token'] = credentials['access_token']
    
    refresh_token = credentials.get('refresh_token')
    if refresh_token:
        os.environ['refresh_token'] = refresh_token

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
    playlist_url = None

    if playlist_id:
        playlist = sp.playlist(playlist_id)
        playlist_name = playlist['name']
        playlist_url = playlist_url = f"https://open.spotify.com/playlist/{playlist_id}"

    # Check if the user is signed up for automatic updates
    user = mongo.db.users.find_one({"spotify_user_id": spotify_user_id})
    signed_up_for_auto_update = user is not None

    return render_template('options.html', playlist_exists=bool(playlist_id), playlist_name=playlist_name,playlist_url=playlist_url, signed_up_for_auto_update=signed_up_for_auto_update)

@app.route('/create_playlist')
def create_playlist():
    access_token = os.getenv('token')
    if not access_token:
        return redirect(url_for('login'))

    sp = spotipy.Spotify(auth=access_token)
    
    # Fetch the user's Spotify ID
    user_profile = sp.current_user()
    spotify_user_id = user_profile['id']

    playlist_name = f"My Monthly Top Tracks"
    playlist_description = "This playlist was created automatically - https://spotify-top-monthly-playlist.onrender.com/."

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

    return render_template('created_playlist.html', message=message, playlist_exists=True, playlist_url=playlist_url)

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
    playlist_name = f"My Monthly Top Tracks"
    playlist_description = "This playlist was created automatically - https://spotify-top-monthly-playlist.onrender.com/."

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

    return render_template('deleted_playlist.html', message=message, playlist_exists=False)

@app.route('/logout')
def logout():
    # Clear the token from the environment variable (optional)
    os.environ.pop('token', None)
    return redirect(url_for('index'))

@app.route('/signup_auto_update')
def signup_auto_update():
    access_token = os.getenv('token')
    refresh_token = os.getenv('refresh_token')
    if not access_token:
        return redirect(url_for('login'))
    
    sp = spotipy.Spotify(auth=access_token)
    user_profile = sp.current_user()
    spotify_user_id = user_profile['id']

    # Check if the user is already signed up
    user = mongo.db.users.find_one({"spotify_user_id": spotify_user_id})

    if user:
        mongo.db.users.update_one(
            {"spotify_user_id": spotify_user_id},
            {"$set": {"access_token": access_token, "refresh_token": refresh_token}}
        )
        message = "You have already signed up for the automatic updates."
    else:
        new_user = User(
            spotify_user_id=spotify_user_id,
            access_token=access_token,
            refresh_token=refresh_token
        )
        mongo.db.users.insert_one(new_user.to_dict())
        message = "You have successfully signed up for automatic updates."

    now = datetime.datetime.now()
    last_month = now - relativedelta(months=1)
    playlist_name = f"My Monthly Top Tracks - {last_month.strftime('%B %Y')}"
    playlist_description = "This playlist was created automatically - https://spotify-top-monthly-playlist.onrender.com/."

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

    return render_template('signed_up_auto_update.html', message=message, playlist_url=playlist_url)


@app.route('/opt_out_auto_update')
def opt_out_auto_update():
    access_token = os.getenv('token')
    if not access_token:
        return redirect(url_for('login'))

    sp = spotipy.Spotify(auth=access_token)

    # Fetch the user's Spotify ID
    user_profile = sp.current_user()
    spotify_user_id = user_profile['id']

    # Delete the user from the MongoDB collection
    result = mongo.db.users.delete_one({"spotify_user_id": spotify_user_id})

    if result.deleted_count > 0:
        message = "You have successfully opted out of automatic updates."
    else:
        message = "No record found to delete or you have already opted out."

    return render_template('opt_out.html', message=message)

# For debugging and testing purposes
@app.route('/show_users')
def show_users():
    # Fetch all users from the MongoDB collection
    users = mongo.db.users.find()  # This returns a cursor

    # Convert the cursor to a list of user dictionaries
    user_list = [user for user in users]

    # Render the list of users in an HTML template
    return render_template('show_users.html', users=user_list)

def refresh_access_token(refresh_token):
    spotify_request_access_token_url = 'https://accounts.spotify.com/api/token'
    body = {
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token,
        'client_id': os.getenv('SPOTIPY_CLIENT_ID'),
        'client_secret': os.getenv('SPOTIPY_CLIENT_SECRET')
    }
    response = requests.post(spotify_request_access_token_url, data=body)
    if response.status_code == 200:
        return response.json()
    else:
        raise Exception('Failed to refresh Access token')

def get_playlist_id(sp, user_id, playlist_prefix='My Monthly Top Tracks'):
    playlists = sp.user_playlists(user_id, limit=50)
    for playlist in playlists['items']:
        if playlist['name'].startswith(playlist_prefix):
            return playlist['id']
    return None

@app.route('/run_monthly_update')
def run_monthly_update():
    users = mongo.db.users.find()
    successful_updates = []

    for user_data in users:
        user = User.from_dict(user_data)

        try:
            # Refresh the access token if needed
            new_tokens = refresh_access_token(user.refresh_token)
            access_token = new_tokens.get('access_token', user.access_token)
            if access_token != user.access_token:
                mongo.db.users.update_one({"spotify_user_id": user.spotify_user_id}, {"$set": {"access_token": access_token}})
            sp = spotipy.Spotify(auth=access_token)
            update_user_playlist(sp, user.spotify_user_id)
            successful_updates.append(user.spotify_user_id)
        except Exception as e:
            print(f"Failed to update playlist for {user.spotify_user_id}: {e}")

    return jsonify({
        "message": "Monthly update completed",
        "successful_user_ids": successful_updates
    }), 200

def update_user_playlist(sp, spotify_user_id):
    results = sp.current_user_top_tracks(time_range='short_term', limit=50)
    top_tracks = [track['uri'] for track in results['items']]

    now = datetime.datetime.now()
    last_month = now - relativedelta(months=1)
    playlist_name = f"My Monthly Top Tracks - {last_month.strftime('%B %Y')}"
    playlist_description = "This playlist was created automatically - https://spotify-top-monthly-playlist.onrender.com/."

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

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
