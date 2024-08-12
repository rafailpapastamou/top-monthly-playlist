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
    # Fetch the spotify_user_id from request arguments
    spotify_user_id = request.args.get('spotify_user_id')

    if not spotify_user_id:
        return redirect(url_for('login'))

    # Fetch the access token from the database
    access_token = get_access_token_from_db(spotify_user_id)
    
    if access_token:
        try:
            sp = spotipy.Spotify(auth=access_token)
            sp.current_user()  # Make a simple API call to check if the token is still valid
            return redirect(url_for('create_or_update_playlist', spotify_user_id=spotify_user_id))
        except spotipy.exceptions.SpotifyException:
            # Token is invalid or expired, attempt to refresh it
            user = mongo.db.users.find_one({"spotify_user_id": spotify_user_id})
            if user:
                new_access_token = refresh_access_token(user)
                if new_access_token:
                    return redirect(url_for('create_or_update_playlist', spotify_user_id=spotify_user_id))
            return redirect(url_for('login'))

    return render_template('index.html')

@app.route('/login')
def login():
    state = str(uuid.uuid4())
    # Store the state in MongoDB for CSRF protection
    mongo.db.auth_state.insert_one({'state': state})
    
    authentication_request_params = {
        'response_type': 'code',
        'client_id': os.getenv('SPOTIPY_CLIENT_ID'),
        'redirect_uri': os.getenv('SPOTIPY_REDIRECT_URI'),
        'scope': 'playlist-modify-public playlist-modify-private user-library-read user-top-read',
        'state': state,
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
    state = request.args.get('state')

    # Verify state to prevent CSRF attacks
    valid_state = mongo.db.auth_state.find_one({'state': state})
    if not valid_state:
        return "Invalid state parameter", 400

    credentials = get_access_token(authorization_code=code)
    access_token = credentials['access_token']
    refresh_token = credentials.get('refresh_token')

    # Fetch user information
    sp = spotipy.Spotify(auth=access_token)
    user_profile = sp.current_user()
    spotify_user_id = user_profile['id']

    # Check if the user is already in the database
    user = mongo.db.users.find_one({"spotify_user_id": spotify_user_id})

    if user:
        # Update the access token and refresh token
        mongo.db.users.update_one(
            {"spotify_user_id": spotify_user_id},
            {"$set": {"access_token": access_token, "refresh_token": refresh_token}}
        )
    else:
        # Insert a new user
        new_user = User(
            spotify_user_id=spotify_user_id,
            access_token=access_token,
            refresh_token=refresh_token
        )
        mongo.db.users.insert_one(new_user.to_dict())

    return redirect(url_for('create_or_update_playlist', spotify_user_id=spotify_user_id))

def get_access_token_from_db(spotify_user_id):
    user = mongo.db.users.find_one({"spotify_user_id": spotify_user_id})
    if user:
        return user.get('access_token')
    return None

@app.route('/create_or_update_playlist')
def create_or_update_playlist():
    spotify_user_id = request.args.get('spotify_user_id')
    access_token = get_access_token_from_db(spotify_user_id)
    
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
    spotify_user_id = request.args.get('spotify_user_id')
    access_token = get_access_token_from_db(spotify_user_id)

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
    spotify_user_id = request.args.get('spotify_user_id')
    access_token = get_access_token_from_db(spotify_user_id)

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
    spotify_user_id = request.args.get('spotify_user_id')
    access_token = get_access_token_from_db(spotify_user_id)

    if not access_token:
        return redirect(url_for('login'))

    sp = spotipy.Spotify(auth=access_token)
    
    # Fetch the user's Spotify ID
    user_profile = sp.current_user()
    spotify_user_id = user_profile['id']

    playlist_name = f"My Monthly Top Tracks"
    playlist_id = get_playlist_id(sp, spotify_user_id, playlist_prefix=playlist_name)

    if playlist_id:
        sp.current_user_unfollow_playlist(playlist_id)
        message = f"Playlist '{playlist_name}' deleted successfully."
    else:
        message = "No playlist found to delete."

    return render_template('options.html', message=message, playlist_exists=False)

@app.route('/signup_auto_update', methods=['POST'])
def signup_auto_update():
    spotify_user_id = request.args.get('spotify_user_id')
    access_token = get_access_token_from_db(spotify_user_id)

    if not access_token:
        return redirect(url_for('login'))

    # Find the user in the database
    user = mongo.db.users.find_one({"spotify_user_id": spotify_user_id})

    if user:
        # Update the user's signup status for automatic updates
        mongo.db.users.update_one(
            {"spotify_user_id": spotify_user_id},
            {"$set": {"signed_up_for_auto_update": True}}
        )
        message = "You have successfully signed up for automatic updates."
    else:
        message = "User not found. Please login again."

    return render_template('options.html', message=message)

@app.route('/remove_auto_update', methods=['POST'])
def remove_auto_update():
    spotify_user_id = request.args.get('spotify_user_id')
    access_token = get_access_token_from_db(spotify_user_id)

    if not access_token:
        return redirect(url_for('login'))

    # Find the user in the database
    user = mongo.db.users.find_one({"spotify_user_id": spotify_user_id})

    if user:
        # Update the user's signup status for automatic updates
        mongo.db.users.update_one(
            {"spotify_user_id": spotify_user_id},
            {"$set": {"signed_up_for_auto_update": False}}
        )
        message = "You have successfully removed automatic updates."
    else:
        message = "User not found. Please login again."

    return render_template('options.html', message=message)

@app.route('/auto_update_playlists')
def auto_update_playlists():
    # Find all users who signed up for automatic updates
    users = mongo.db.users.find({"signed_up_for_auto_update": True})
    for user_data in users:
        user = User.from_dict(user_data)
        try:
            refresh_access_token(user)
            sp = spotipy.Spotify(auth=user.access_token)
            spotify_user_id = user.spotify_user_id
            results = sp.current_user_top_tracks(time_range='short_term', limit=50)
            top_tracks = [track['uri'] for track in results['items']]
            playlist_name = f"My Monthly Top Tracks"
            playlist_description = "This playlist was created automatically - https://spotify-top-monthly-playlist.onrender.com/."
            playlist_id = get_playlist_id(sp, spotify_user_id)
            if playlist_id:
                sp.user_playlist_change_details(spotify_user_id, playlist_id, name=playlist_name, description=playlist_description)
                sp.playlist_replace_items(playlist_id, top_tracks)
                print(f"Playlist '{playlist_name}' for user {spotify_user_id} updated successfully!")
            else:
                print(f"No existing playlist to update for user {spotify_user_id}.")
        except Exception as e:
            print(f"Failed to update playlist for user {user.spotify_user_id}: {e}")

    return jsonify({"status": "success", "message": "Playlists updated for all users signed up for auto-update."})

def refresh_access_token(user):
    spotify_request_access_token_url = 'https://accounts.spotify.com/api/token'
    body = {
        'grant_type': 'refresh_token',
        'refresh_token': user.refresh_token,
        'client_id': os.getenv('SPOTIPY_CLIENT_ID'),
        'client_secret': os.getenv('SPOTIPY_CLIENT_SECRET')
    }
    response = requests.post(spotify_request_access_token_url, data=body)
    if response.status_code == 200:
        new_tokens = response.json()
        access_token = new_tokens['access_token']
        
        # Update the database with the new access token
        mongo.db.users.update_one(
            {"spotify_user_id": user.spotify_user_id},
            {"$set": {"access_token": access_token}}
        )
        
        return access_token
    else:
        raise Exception('Failed to refresh Access token')

def get_playlist_id(sp, user_id, playlist_prefix='My Monthly Top Tracks'):
    playlists = sp.current_user_playlists()
    for playlist in playlists['items']:
        if playlist['owner']['id'] == user_id and playlist['name'].startswith(playlist_prefix):
            return playlist['id']
    return None

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)