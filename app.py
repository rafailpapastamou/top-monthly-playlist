from flask import Flask, redirect, url_for, session, request, render_template
import http.client
import http.server
import json
import logging
import re
import urllib.parse
import urllib.request
import webbrowser
import os
import datetime
from dateutil.relativedelta import relativedelta
from dotenv import load_dotenv

load_dotenv('variables.env')

app = Flask(__name__)
app.secret_key = os.urandom(24)

class SpotifyAPI:
    def __init__(self, auth):
        self._auth = auth
    
    def get(self, url, params={}, tries=3):
        if not url.startswith('https://api.spotify.com/v1/'):
            url = 'https://api.spotify.com/v1/' + url
        if params:
            url += ('&' if '?' in url else '?') + urllib.parse.urlencode(params)
    
        for _ in range(tries):
            try:
                req = urllib.request.Request(url)
                req.add_header('Authorization', 'Bearer ' + self._auth)
                res = urllib.request.urlopen(req)
                reader = codecs.getreader('utf-8')
                return json.load(reader(res))
            except Exception as err:
                logging.info('Couldn\'t load URL: {} ({})'.format(url, err))
                time.sleep(2)
                logging.info('Trying again...')
        sys.exit(1)
    
    def list(self, url, params={}):
        last_log_time = time.time()
        response = self.get(url, params)
        items = response['items']
    
        while response['next']:
            if time.time() > last_log_time + 15:
                last_log_time = time.time()
                logging.info(f"Loaded {len(items)}/{response['total']} items")
    
            response = self.get(response['next'])
            items += response['items']
        return items
    
    @staticmethod
    def authorize(client_id, scope):
        url = 'https://accounts.spotify.com/authorize?' + urllib.parse.urlencode({
            'response_type': 'token',
            'client_id': client_id,
            'scope': scope,
            'redirect_uri': 'http://127.0.0.1:{}/redirect'.format(SpotifyAPI._SERVER_PORT)
        })
        logging.info(f'Logging in (click if it doesn\'t open automatically): {url}')
        webbrowser.open(url)
    
        server = SpotifyAPI._AuthorizationServer('127.0.0.1', SpotifyAPI._SERVER_PORT)
        try:
            while True:
                server.handle_request()
        except SpotifyAPI._Authorization as auth:
            return SpotifyAPI(auth.access_token)
    
    _SERVER_PORT = 43019
    
    class _AuthorizationServer(http.server.HTTPServer):
        def __init__(self, host, port):
            http.server.HTTPServer.__init__(self, (host, port), SpotifyAPI._AuthorizationHandler)
        
        def handle_error(self, request, client_address):
            raise
    
    class _AuthorizationHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.startswith('/redirect'):
                self.send_response(200)
                self.send_header('Content-Type', 'text/html')
                self.end_headers()
                self.wfile.write(b'<script>location.replace("token?" + location.hash.slice(1));</script>')
            
            elif self.path.startswith('/token?'):
                self.send_response(200)
                self.send_header('Content-Type', 'text/html')
                self.end_headers()
                self.wfile.write(b'<script>close()</script>Thanks! You may now close this window.')

                access_token = re.search('access_token=([^&]*)', self.path).group(1)
                logging.info(f'Received access token from Spotify: {access_token}')
                raise SpotifyAPI._Authorization(access_token)
            
            else:
                self.send_error(404)
        
        def log_message(self, format, *args):
            pass
    
    class _Authorization(Exception):
        def __init__(self, access_token):
            self.access_token = access_token

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login')
def login():
    if 'token_info' in session:
        return redirect(url_for('create_or_update_playlist'))

    sp_oauth = SpotifyAPI.authorize(client_id=os.getenv('SPOTIPY_CLIENT_ID'), 
                                    scope='playlist-modify-public playlist-modify-private user-library-read')
    return redirect(url_for('callback'))

@app.route('/redirect')
def callback():
    token = request.args.get('access_token')
    if not token:
        return redirect(url_for('login'))

    session['token_info'] = token
    return redirect(url_for('create_or_update_playlist'))

@app.route('/create_or_update_playlist')
def create_or_update_playlist():
    if 'token_info' not in session:
        return redirect(url_for('login'))
    
    token_info = session['token_info']
    sp = SpotifyAPI(auth=token_info)
    user_id = sp.get('me')['id']
    playlist_id = get_playlist_id(sp, user_id)
    playlist_name = None

    if playlist_id:
        playlist = sp.get(f'playlists/{playlist_id}')
        playlist_name = playlist['name']

    return render_template('options.html', playlist_exists=bool(playlist_id), playlist_name=playlist_name)

@app.route('/create_playlist')
def create_playlist():
    if 'token_info' not in session:
        return redirect(url_for('login'))
    
    token_info = session['token_info']
    sp = SpotifyAPI(auth=token_info)

    user_id = sp.get('me')['id']
    now = datetime.datetime.now()
    last_month = now - relativedelta(months=1)
    playlist_name = f"My Monthly Top Tracks - {last_month.strftime('%B %Y')}"
    playlist_description = "This playlist was created automatically using this: https://spotify-top-monthly-playlist.onrender.com/"

    playlist_id = get_playlist_id(sp, user_id, playlist_prefix=playlist_name)
    if playlist_id:
        message = f"Playlist '{playlist_name}' already exists."
        playlist_url = f"https://open.spotify.com/playlist/{playlist_id}"
    else:
        results = sp.list('me/top/tracks', {'time_range': 'short_term', 'limit': 50})
        top_tracks = [track['uri'] for track in results]

        playlist = sp.get(f'users/{user_id}/playlists', {'name': playlist_name, 'description': playlist_description})
        playlist_id = playlist['id']
        sp.get(f'playlists/{playlist_id}/tracks', {'uris': ','.join(top_tracks)})
        message = f"Playlist '{playlist_name}' created successfully!"
        playlist_url = f"https://open.spotify.com/playlist/{playlist_id}"

    return render_template('created_playlist.html', message=message, playlist_exists=True, playlist_name=playlist_name, playlist_url=playlist_url)

@app.route('/update_playlist')
def update_playlist():
    if 'token_info' not in session:
        return redirect(url_for('login'))
    
    token_info = session['token_info']
    sp = SpotifyAPI(auth=token_info)

    user_id = sp.get('me')['id']
    now = datetime.datetime.now()
    last_month = now - relativedelta(months=1)
    playlist_name = f"My Monthly Top Tracks - {last_month.strftime('%B %Y')}"
    playlist_description = "This playlist was created automatically using this: https://spotify-top-monthly-playlist.onrender.com/"

    playlist_id = get_playlist_id(sp, user_id)
    if playlist_id:
        sp.get(f'playlists/{playlist_id}', {'name': playlist_name, 'description': playlist_description})
        results = sp.list('me/top/tracks', {'time_range': 'short_term', 'limit': 50})
        top_tracks = [track['uri'] for track in results]
        sp.get(f'playlists/{playlist_id}/tracks', {'uris': ','.join(top_tracks)})
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
    sp = SpotifyAPI(auth=token_info)
    user_id = sp.get('me')['id']
    playlist_id = get_playlist_id(sp, user_id)

    if playlist_id:
        sp.get(f'playlists/{playlist_id}/followers')
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
    playlists = sp.list(f'users/{user_id}/playlists', {'limit': 50})
    for playlist in playlists:
        if playlist['name'].startswith(playlist_prefix):
            return playlist['id']
    return None

if __name__ == '__main__':
    app.run(debug=True)