from spotipy.oauth2 import SpotifyOAuth
from spotipy.cache_handler import CacheHandler





# Custom DB Cache
class DBTokenCache(CacheHandler):
    def __init__(self, user, db):
        self.user = user
        self.db = db

    def get_cached_token(self):
        if self.user.spotify_acc_tok and self.user.spotify_ref_tok:
            return {
                "access_token": self.user.spotify_acc_tok,
                "refresh_token": self.user.spotify_ref_tok
            }
        return None

    def save_token_to_cache(self, token_info):
        self.user.spotify_acc_tok = token_info['access_token']
        self.user.spotify_ref_tok = token_info.get('refresh_token')
        self.db.session.commit()