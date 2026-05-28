import smtplib
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from enum import unique
from logging import exception
import pytz
import feedparser
from dateutil import parser as date_parser
import requests
import time
import shutil
import threading
from bs4 import BeautifulSoup
from dominate.svg import title
from flask import Flask, abort, render_template, redirect, url_for, flash, request, session, jsonify
from flask_bootstrap import Bootstrap5
from flask_ckeditor import CKEditor
from flask_wtf import FlaskForm
from wtforms import SubmitField
from flask_ckeditor import CKEditorField
from flask_gravatar import Gravatar
from flask_login import UserMixin, login_user, LoginManager, current_user, logout_user, login_required
from flask_sqlalchemy import SQLAlchemy
from numpy.ma.core import default_fill_value
from sqlalchemy.orm import relationship, DeclarativeBase, Mapped, mapped_column
from sqlalchemy import Integer, String, Text, func, delete, DateTime, ForeignKey, BigInteger, JSON
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os, secrets
from dotenv import load_dotenv
# import cloudinary
# import cloudinary.uploader
import time
import re
import asyncio
from shazamio import Shazam
from datetime import datetime, timedelta, timezone
import spotipy
from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth, SpotifyClientCredentials
import webbrowser
import inspect ## for getting some info like current line
from concurrent.futures import ThreadPoolExecutor, as_completed

from wtforms.validators import DataRequired

from classes import DBTokenCache
import random
import requests
from flask import Response, stream_with_context
import json, time, asyncio
import html
from pprint import pprint
import billboard
# from forms import CreatePostForm, RegisterForm, LoginForm, CommentForm
# Optional: add contact me email functionality (Day 60)
# import smtplib



# Load .env file
load_dotenv()


# Get the Cloudinary credentials
cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME")
api_key = os.getenv("CLOUDINARY_API_KEY")
api_secret = os.getenv("CLOUDINARY_API_SECRET")
CLOUDINARY_URL = f"CLOUDINARY_URL=cloudinary://{api_key}:{api_secret}@{cloud_name}"

# Spotify app credentials
spotify_client_id = os.getenv("SSPIDERR_SPOTIFY_CLIENT_ID")
spotify_client_secret = os.getenv("SSPIDERR_SPOTIFY_CLIENT_SECRET")
spotify_redirect_uri = os.getenv("SSPIDERR_SPOTIFY_REDIRECT_URI")
spotify_scope = "playlist-modify-public playlist-modify-private playlist-read-private"

# Unsplash app credentials
unsplash_app_id = os.getenv("UNSPLASH_APP_ID")
unsplash_access_key = os.getenv("UNSPLASH_ACCESS_KEY")
unsplash_secret_key = os.getenv("UNSPLASH_SECRET_KEY")
unsplash_redirect_uri = os.getenv("UNSPLASH_REDIRECT_URI")

# APPLE I-TUNES API
i_tunes_end_url = "https://itunes.apple.com/search"
i_tunes_top_albums_url = "https://rss.applemarketingtools.com/api/v2/us/music/most-played/100/albums.json"
i_tunes_top_songs_url = "https://rss.applemarketingtools.com/api/v2/us/music/most-played/100/songs.json"
i_tunes_top_artists_url = "https://rss.applemarketingtools.com/api/v2/us/music/most-played/100/artists.json"
# Replace us with another country code (e.g., ng for Nigeria, gb for UK).

# LAST FM API
last_fm_api_key = os.getenv("LAST_FM_API_KEY")
last_fm_api_secret = os.getenv("LAST_FM_API_SECRET")
last_fm_redirect_url = os.getenv("LAST_FM_REDIRECT_URL")

# GOOGLE CLOUD API KEY
google_cloud_api_key = os.getenv("GOOGLE_CLOUD_API_KEY")
google_search_engine_id = os.getenv("CX")

# SPOTIFY PLAYLIST IDs
best_hits_2025_id = "5iwkYfnHAGMEFLiHFFGnP4"
this_weeks_hits_id = "37i9dQZF1DXcBWIGoYBM5M"

# AUDIOMACK ENDPOINTS
AFRO_TOP_TRACKS = "https://audiomack.com/top/songs"
AFRO_TOP_ALBUMS = "https://audiomack.com/top/albums"
AFRO_TRENDING_TRACKS = "https://audiomack.com/trending-now/songs"
AFRO_TRENDING_ALBUMS = "https://audiomack.com/trending-now/albums"
AFRO_RECENT_TRACKS = "https://audiomack.com/recent"  # High chance the tracks are not on spotify

# NEWSDATA.IO API_KEY
news_data_api_key = os.getenv("NEWS_DATA_API_KEY")



app = Flask(__name__)

app.secret_key = os.getenv("APP_SECRET_KEY")
app.config['CKEDITOR_PKG_TYPE'] = 'standard'  # or 'basic', 'full'
ckeditor = CKEditor(app)
Bootstrap5(app)



initial_time = time.time()
# Configure Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return db.get_or_404(User, user_id)

# For adding profile images to the comment section
gravatar = Gravatar(app,
                    size=100,
                    rating='g',
                    default='retro',
                    force_default=False,
                    force_lower=False,
                    use_ssl=False,
                    base_url=None)

# CREATE DATABASE
class Base(DeclarativeBase):
    pass

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///my_songs.db'
db = SQLAlchemy(model_class=Base)
db.init_app(app)

class BlogPost(db.Model):
    __tablename__ = "blog_posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(250), unique=False, nullable=False, index=True)
    subtitle: Mapped[str] = mapped_column(String(250), nullable=True)
    # Use DateTime for the post date; store timezone-naive UTC or timezone-aware depending on your policy
    date: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, server_default=func.now())
    body: Mapped[str] = mapped_column(Text, nullable=False)
    img_url: Mapped[str] = mapped_column(String(250), nullable=True)
    source: Mapped[str] = mapped_column(String(250), nullable=True)  # e.g. Billboard, NewsData, etc.
    news_link: Mapped[str] = mapped_column(String(1000), nullable=True)
    created_id: Mapped[int] = mapped_column(Integer, unique=True)
    day: Mapped[int] = mapped_column(Integer, unique=False)
    month: Mapped[int] = mapped_column(Integer, unique=False)
    year: Mapped[int] = mapped_column(Integer, unique=False)
    # This line is critical 👇
    author_id = db.Column(db.Integer, db.ForeignKey("sspiderr_users.id"), nullable=True)
    # Relationship back to user
    author = relationship("User", back_populates="posts")
    # Parent relationship to comments
    comments: Mapped[list["Comment"]] = relationship("Comment", back_populates="parent_post", cascade="all, delete-orphan")


# -----------------------
# Comment
# -----------------------
class Comment(db.Model):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, server_default=func.now())

    author_id: Mapped[int] = mapped_column(Integer, ForeignKey("sspiderr_users.id", ondelete="SET NULL"), nullable=True)
    comment_author: Mapped["User"] = relationship("User", back_populates="comments")

    post_id: Mapped[int] = mapped_column(Integer, ForeignKey("blog_posts.id", ondelete="CASCADE"), nullable=False)
    parent_post: Mapped["BlogPost"] = relationship("BlogPost", back_populates="comments")

class ReviewComment(db.Model):
    __tablename__ = "review_comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, server_default=func.now())

    author_id: Mapped[int] = mapped_column(Integer, ForeignKey("sspiderr_users.id", ondelete="SET NULL"), nullable=True)
    review_author: Mapped["User"] = relationship("User", back_populates="review_comments")

# Create a User table for all your registered users
class User(UserMixin, db.Model):
    __tablename__ = "sspiderr_users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(100), unique=True)
    password: Mapped[str] = mapped_column(String(100))
    spotify_acc_tok: Mapped[str] = mapped_column(Text, unique=True, nullable = True)
    spotify_ref_tok: Mapped[str] = mapped_column(Text, unique=True, nullable = True)
    spotify_user_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=True)
    # NEW relationships — these do NOT affect existing data
    posts = relationship("BlogPost", back_populates="author")
    comments = relationship("Comment", back_populates="comment_author")
    home_data = relationship("HomeData", back_populates="user", uselist=False)
    review_comments = relationship("ReviewComment", back_populates="review_author")


class Playlist(db.Model):
    __tablename__ = "user_playlist"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text)
    spotify_playlist_id: Mapped[str] = mapped_column(String(50))
    spotify_user_id: Mapped[str]= mapped_column(String(50))

class Songs(db.Model):
    __tablename__ = "songs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    track_id: Mapped[str] = mapped_column(String(), nullable=False)
    name: Mapped[str] = mapped_column(String(100))
    album: Mapped[str] = mapped_column(String(100))
    artist: Mapped[str] = mapped_column(String(100))
    duration_ms: Mapped[int] = mapped_column(Integer)
    popularity: Mapped[int] = mapped_column(Integer)
    preview_url: Mapped[str] = mapped_column(String(), nullable=True)
    external_url: Mapped[str] = mapped_column(String())
    spotify_playlist_id: Mapped[str] = mapped_column(String(50))
    spotify_user_id: Mapped[str] = mapped_column(String(50))

class RecognisedSongs(db.Model):
    __tablename__ = "recognised_songs"
    id: Mapped[int]=mapped_column(Integer, primary_key=True)
    track: Mapped[str] = mapped_column(String(500))
    spotify_playlist_id: Mapped[str] = mapped_column(String(50))
    spotify_user_id: Mapped[str] = mapped_column(String(50))

class UnrecognisedSongs(db.Model):
    __tablename__ = "unrecognised_songs"
    id: Mapped[int]=mapped_column(Integer, primary_key=True)
    track: Mapped[str] = mapped_column(String(500))
    spotify_playlist_id: Mapped[str] = mapped_column(String(50))
    spotify_user_id: Mapped[str] = mapped_column(String(50))

class SentSpotifySongs(db.Model):
    __tablename__ = "sent_spotify_songs"
    id: Mapped[int]=mapped_column(Integer, primary_key=True)
    track: Mapped[str] = mapped_column(String(500))
    spotify_playlist_id: Mapped[str] = mapped_column(String(50))
    spotify_user_id: Mapped[str] = mapped_column(String(50))

class UnsentSpotifySongs(db.Model):
    __tablename__ = "unsent_spotify_songs"
    id: Mapped[int]=mapped_column(Integer, primary_key=True)
    track: Mapped[str] = mapped_column(String(500))
    spotify_playlist_id: Mapped[str] = mapped_column(String(50))
    spotify_user_id: Mapped[str] = mapped_column(String(50))

class HomeData(db.Model):
    __tablename__ = "home_data"

    id = mapped_column(Integer, primary_key=True, autoincrement=True)
    album_id = mapped_column(BigInteger, nullable=True)
    album_art = mapped_column(String(500), nullable=True)
    album_name = mapped_column(String(255), nullable=True)

    song_art = mapped_column(String(500), nullable=True)
    song_name = mapped_column(String(255), nullable=True)
    song_id = mapped_column(String(100), nullable=True)
    artist_art = mapped_column(String(500), nullable=True)
    artist_name = mapped_column(String(255), nullable=True)

    # All JSON fields must be REAL dict/list, NOT strings
    top_albums = mapped_column(JSON, nullable=True)
    feature_artists_info = mapped_column(JSON, nullable=True)
    artist_description = mapped_column(JSON, nullable=True)   # FIXED
    top_artist_album_track = mapped_column(JSON, nullable=True)
    best_2025_hits = mapped_column(JSON, nullable=True)
    this_weeks_hits = mapped_column(JSON, nullable=True)
    artist_section_dict = mapped_column(JSON, nullable=True)
    new_time_tag = db.Column(db.DateTime(timezone=True), nullable=True)

    user_id = mapped_column(Integer, db.ForeignKey("sspiderr_users.id"), nullable=True)
    user = relationship("User", back_populates="home_data")


class SchedulerStatus(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    last_run = db.Column(db.DateTime(timezone=True), nullable=False)
    session_id = db.Column(db.String, nullable=True)
    user_id = db.Column(db.String(50), nullable=True)


with app.app_context():
    # Songs.__table__.drop(db.engine)
    # HomeData.__table__.drop(db.engine)
    # SchedulerStatus.__table__.drop(db.engine) ## run this again after 24 hrs
    # BlogPost.__table__.drop(db.engine)
    # Comment.__table__.drop(db.engine)
    db.create_all() #This is where the table is created

class CommentForm(FlaskForm):
    comment_text = CKEditorField('Your Comment', validators=[DataRequired()])
    submit = SubmitField('Post Comment')

#LOGIN FUNCTIONS
@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('home'))

# If upload folder exist initially delete
EXISTING_UPLOAD_FOLDER = "./static/uploads"

def create_upload_folder():
    # Create a folder for uploaded songs
    UPLOAD_FOLDER = os.path.join("static", "uploads")
    app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    print('Upload folder created successfully')

def delete_upload_folder():
    if os.path.exists(EXISTING_UPLOAD_FOLDER):
        try:
            shutil.rmtree(EXISTING_UPLOAD_FOLDER)
            print("Folder deleted successfully!")
        except Exception as e:
            print(f"Failed to delete folder: {e}")
    else:
        print("Folder does not exist.")



import uuid

def get_session_id():
    '''This function is useful to keep track of the sessions before carrying out the scheduler. This helps in cases of multiple users'''
    if 'session_id' not in session:
        session['session_id'] = str(uuid.uuid4())
    return session['session_id']


def should_run_24h_task(current_user_id):
    now = datetime.now(timezone.utc)

    session_id = get_session_id()

    if current_user_id:
        # 🔹 Logged-in flow
        status = (
            SchedulerStatus.query
            .filter_by(user_id=current_user_id)
            .order_by(SchedulerStatus.last_run.desc())
            .first()
        )

        # 🔥 NEW: migrate session → user
        if not status:
            session_status = (
                SchedulerStatus.query
                .filter_by(session_id=session_id)
                .order_by(SchedulerStatus.last_run.desc())
                .first()
            )

            if session_status:
                status = SchedulerStatus(
                    user_id=current_user_id,
                    last_run=session_status.last_run
                )
                db.session.add(status)
                db.session.commit()
            else:
                status = SchedulerStatus(
                    user_id=current_user_id,
                    last_run=now
                )
                db.session.add(status)
                db.session.commit()
                return True

    else:
        # 🔹 Anonymous flow (session-based now)
        status = (
            SchedulerStatus.query
            .filter_by(session_id=session_id)
            .order_by(SchedulerStatus.last_run.desc())
            .first()
        )

        if not status:
            status = SchedulerStatus(
                session_id=session_id,
                last_run=now
            )
            db.session.add(status)
            db.session.commit()
            return True

    # --- shared logic ---
    last_run = status.last_run

    if last_run.tzinfo is None:
        last_run = last_run.replace(tzinfo=timezone.utc)

    if now - last_run >= timedelta(hours=24):
        status.last_run = now
        db.session.commit()
        print('Time - schedule ----True')
        return True

    print('Time - schedule ----False')
    return False


def get_artwork_url(original_url: str, size: int = 500) -> str:
    """
    Replace the artwork size in an Apple Music artwork URL.

    Args:
        original_url (str): The artworkUrl (e.g., artworkUrl100).
        size (int): Desired size in pixels (e.g., 200, 500, 1000).

    Returns:
        str: Modified URL with requested size.
    """
    if not original_url:
        return None
    # Apple URLs contain "{width}x{height}" pattern like 100x100
    return original_url.replace("100x100", f"{size}x{size}")


def get_billboard_top_artists(limit=100):
    """
    Scrape Billboard Artist 100 chart.

    Args:
        limit (int): Number of artists to return (default=100).
                     Example: pass 10 to get Top 10.

    Returns:
        list of str: List of artist names.
    """

    url = "https://www.billboard.com/charts/artist-100/"
    # response = requests.get(url, timeout=10)
    response = requests.get(url)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    # Billboard artist names are usually inside <li> under 'o-chart-results-list__item'
    artists_tags = soup.select("li.o-chart-results-list__item h3")

    artists = []
    for tag in artists_tags[:limit]:  # slice according to limit
        name = html.unescape(tag.get_text(strip=True))
        artists.append(name)

    return artists


def get_deezer_top_albums(limit=50):
    """
    Fetch top albums from Deezer Chart API.
    """
    url = f"https://api.deezer.com/chart/0/albums?limit={limit}"
    response = requests.get(url)
    data = response.json()

    if "data" not in data:
        raise Exception("Error fetching chart data:", data)

    return data["data"]


def get_deezer_album_details(album_id):
    """
    Fetch complete album information including release date.
    """
    url = f"https://api.deezer.com/album/{album_id}"
    response = requests.get(url)
    return response.json()


def build_deezer_album_dataset(limit=50):
    """
    Fetch Deezer top albums WITHOUT pagination and merge full metadata.
    """
    print(f"Fetching {limit} Deezer top albums (non-paginated)...")

    # --- SINGLE REQUEST (no pagination) ---
    url = f"https://api.deezer.com/chart/0/albums?limit={limit}"
    response = requests.get(url).json()

    if not response.get("data"):
        print("No data returned from Deezer.")
        return []

    top_albums = response["data"][:limit]

    print(f"Fetched {len(top_albums)} albums.")

    # --- BUILD FULL METADATA ---
    full_data_list = []

    for album in top_albums:
        album_id = album["id"]
        title = album["title"]

        print(f"Fetching details for: {title} (ID {album_id})")

        full_details = get_deezer_album_details(album_id)

        combined = {
            "album_id": album_id,
            "artist_id": album["artist"]["id"],
            "album_name": title,
            "artist_name": album["artist"]["name"],
            "genre": "N/A",
            "artwork_url_original": album.get("cover_xl"),
            "artwork_small": album.get("cover_small"),
            "artwork_medium": album.get("cover_medium"),
            "artwork_full": album.get("cover_big"),
            "position": album.get("position"),
            "release_date": full_details.get("release_date", "N/A"),
            "tracks_count": full_details.get("nb_tracks", 0),
            "duration": full_details.get("duration", 0),
            "fans": full_details.get("fans", 0),
        }

        full_data_list.append(combined)
    return full_data_list


DEEZER_TOP_SONGS_URL = "https://api.deezer.com/chart/0/tracks?limit=100"

def build_deezer_song_dataset(limit=100):
    # Fetch Deezer top songs
    response = requests.get(f"https://api.deezer.com/chart/0/tracks?limit={limit}")
    deezer_json = response.json()

    # Match old iTunes structure: song_contents = song_json["feed"]["results"]
    song_contents = []

    for track in deezer_json.get("data", []):
        # Convert Deezer fields → Your old iTunes fields
        item = {
            "song_name": track.get("title"),                          # iTunes "name"
            "artwork_url_original": track.get("album", {})
                               .get("cover_xl"),
            "artwork_small": track.get("album", {})
                               .get("cover_small"),
            "artwork_medium": track.get("album", {})
                                .get("cover_medium"),
            "artwork_full": track.get("album", {})
                                .get("cover_big"),
            "song_id": track.get("id"),                               # iTunes "id"
            "artist_Name": track.get("artist", {}).get("name"),   # optional but useful
        }
        song_contents.append(item)
    return song_contents


def top_albums_info():

    album_info_contents = []
    # Fetch Top Album
    album_result = requests.get(i_tunes_top_albums_url)
    if album_result:
        album_json = album_result.json()
        album_contents = album_json["feed"]["results"]

        if album_contents:
            album_top_10 = album_contents[:10]

            for albums in album_top_10:
                album_name = albums['name']
                album_artist_name = albums['artistName']
                i_tunes_album_id = albums['id']
                album_date = albums['releaseDate']
                album_genre = albums['genres'][0]['name']
                album_art_url = albums['artworkUrl100']
                album_artist_id = albums['artistId']

                # create resizes
                album_art_full = get_artwork_url(album_art_url, 1000)
                album_art_med = get_artwork_url(album_art_url, 300)
                album_art_small = get_artwork_url(album_art_url, 100)

                album_info_contents.append({
                    "album_name": album_name,
                    "artist_name": album_artist_name,
                    "album_id": i_tunes_album_id,
                    "artist_id": album_artist_id,
                    "release_date": album_date,
                    "genre": album_genre,
                    "artwork_url_original": album_art_url,
                    "artwork_small": album_art_small,
                    "artwork_medium": album_art_med,
                    "artwork_full": album_art_full
                })
                print(f"album id: {i_tunes_album_id}")
    else:
        album_info_contents = build_deezer_album_dataset(50)

    return album_info_contents

def top_artist_info(artist_name):

    required_artist_info = {}

    sp, source = get_spotify_client_for_request(current_user)
    print(f"get_spot_play_tracks:: spotify app: {sp},\n source: {source}")

    # Search for artist
    result = sp.search(q=f"artist:{artist_name}", type="artist", limit=1)

    if result["artists"]["items"]:
        artist = result["artists"]["items"][0]
        artist_id = artist["id"]

        albums = sp.artist_albums(artist_id, album_type="album", limit=10)

        # Sort albums by release date (newest first)
        sorted_albums = sorted(
            albums["items"],
            key=lambda x: x["release_date"],
            reverse=True
        )

        latest_album = sorted_albums[0] if sorted_albums else None

        if latest_album:
            required_artist_info = {
                "album_name": latest_album["name"],
                "release_date": latest_album["release_date"],
                "album_id": latest_album["id"],
                "album_cover": latest_album["images"][0]["url"],
                "spotify_link": latest_album["external_urls"]["spotify"],
                "artist_name": artist["name"],
                "genres": artist["genres"], # Dont include in database
                "followers": artist["followers"]["total"],
                "popularity": artist["popularity"],
                "artist_image": artist["images"][0]["url"]
            }
    return required_artist_info


apple_top_albums = []
apple_top_songs = []
apple_top_artist = []
def get_artist_image(artist_name, index=0, sp=None):
    if sp:
        # Search for the artist
        result = sp.search(q=artist_name, type="artist", limit=1)
        if result["artists"]["items"]:
            artist = result["artists"]["items"][0]

            if artist.get("images"):
                idx = min(index, len(artist["images"]) - 1)
                print("image came from spotify!")
                return artist["images"][idx]["url"]
        return None

    else:
        # Google Custom Search fallback
        search_url = "https://www.googleapis.com/customsearch/v1"
        params = {
            "q": artist_name,
            "cx": google_search_engine_id,
            "key": google_cloud_api_key,
            "searchType": "image",
            "num": 5  # request more to give room for indexing
        }
        response = requests.get(search_url, params=params).json()

        if "items" in response and len(response["items"]) > 0:
            idx = min(index, len(response["items"]) - 1) #This helps to make sure you dont get an index error
            print("image came from google!")
            return response["items"][idx]["link"]

        return None




def get_artist_description(artist_name, last_fm_api_key=None):
    # Step 1: iTunes search
    i_search_url = "https://itunes.apple.com/search"
    params = {"term": artist_name, "entity": "musicArtist", "limit": 1}
    i_response = requests.get(i_search_url, params=params).json()

    artist_desc = None

    if i_response["resultCount"] > 0:
        artist_id = i_response["results"][0]["artistId"]
        i_lookup_url = "https://itunes.apple.com/lookup"
        params = {"id": artist_id, "entity": "musicArtist"}
        response = requests.get(i_lookup_url, params=params).json()

        if response["resultCount"] > 0:
            artist = response["results"][0]
            artist_desc = artist.get("artistBio") or artist.get("longDescription") or artist.get("description")
            if artist_desc:
                return {"source": "iTunes", "description": artist_desc}

    # Step 2: Last.fm fallback
    if last_fm_api_key:
        last_fm_url = "http://ws.audioscrobbler.com/2.0/"
        params = {
            "method": "artist.getinfo",
            "artist": artist_name,
            "api_key": last_fm_api_key,
            "format": "json"
        }
        last_response = requests.get(last_fm_url, params=params).json()
        if "artist" in last_response and "bio" in last_response["artist"]:
            artist_desc = last_response["artist"]["bio"]["summary"]
            if artist_desc:
                return {"source": "Last.fm", "description": artist_desc}

    # Step 3: Nothing found
    return {"source": None, "description": "No description available."}

def get_album_tracks_sorted(album_name):

    sp, source = get_spotify_client_for_request(current_user)
    print(f"get_live_chart:: spotify app: {sp},\nsource: {source}")

    # Step 1: Search for album
    results = sp.search(q=f"album:{album_name}", type="album", limit=1)
    if not results["albums"]["items"]:
        return []

    album_id = results["albums"]["items"][0]["id"]

    # Step 2: Get all tracks from album
    tracks = sp.album_tracks(album_id)["items"]

    track_data = []
    for track in tracks:
        track_info = sp.track(track["id"])   # fetch popularity
        track_data.append({
            "name": track_info["name"],
            "id": track_info["id"],
            "popularity": track_info["popularity"],
            "preview_url": track_info["preview_url"],  # 30s sample
            "track_number": track_info["track_number"],
            "album_name": album_name
        })

    # Step 3: Sort tracks by popularity (descending)
    sorted_tracks = sorted(track_data, key=lambda x: x["popularity"], reverse=True)
    return sorted_tracks

# THE FOLLOWING FUNCTION ARE STEPS TO USE SPOTIFY SERVER ACCESS

# Simple thread-safe cache for the app-level auth manager
_app_auth_lock = threading.Lock()
_app_auth_manager = None
_app_auth_expires_at = 0

def _ensure_app_auth_manager():
    """
    Ensure we have a SpotifyClientCredentials auth manager cached until expiry.
    Spotipy's SpotifyClientCredentials handles token fetching but we also cache
    the auth_manager to avoid re-instantiating for every request.
    """
    global _app_auth_manager, _app_auth_expires_at
    with _app_auth_lock:
        now = int(time.time())
        # Refresh if not set or expires soon
        if _app_auth_manager is None or now >= _app_auth_expires_at - 30:
            mgr = SpotifyClientCredentials(client_id=spotify_client_id,
                                           client_secret=spotify_client_secret)
            # Force token fetch to determine expiry
            token_info = mgr.get_access_token(as_dict=True)
            expires_in = token_info.get("expires_in", 3600)
            _app_auth_manager = mgr
            _app_auth_expires_at = now + int(expires_in)
        return _app_auth_manager

def get_server_spotify():
    """
    Return a spotipy.Spotify client authenticated with client credentials (app token).
    """
    auth_manager = _ensure_app_auth_manager()
    return spotipy.Spotify(auth_manager=auth_manager)

def get_user_spotify(access_token):
    """
    Return a spotipy.Spotify client for a user access token string.
    access_token should be a valid token (or None).
    """
    if not access_token:
        return None
    # Spotipy accepts token string in 'auth' param for simple use
    return spotipy.Spotify(auth=access_token, requests_timeout=30)

def get_spotify_client_for_request(current_user):
    """
    Try to build a Spotify client using the user's token (if present and valid).
    Otherwise fall back to server client credentials client.
    current_user is app-specific; adapt to how you store tokens.
    """
    # Example: your get_valid_spotify_token(current_user) should return a string or None
    try:
        user_token = get_valid_spotify_token(current_user)  # you already have this
    except Exception:
        user_token = None

    if user_token:
        # Optionally validate by calling a light endpoint (or just use it and catch errors)
        sp_user = get_user_spotify(user_token)
        return sp_user, "user"
    else:
        sp_server = get_server_spotify()
        return sp_server, "app"

# Updated playlist getter that uses fallback client
def get_spotify_playlist_tracks(playlist_id):
    sp, source = get_spotify_client_for_request(current_user)
    print(f"get_spot_play_tracks:: spotify app: {sp},\n source: {source}")

    try:
        # Use playlist_items (handles pagination) — set limit as you want
        results = sp.playlist_items(playlist_id, limit=15, market="US")

    except spotipy.exceptions.SpotifyException as e:
        # If user token fails and we used user client, try server fallback
        print(e)
        if source == "user":
            try:
                # Authenticate using your app credentials
                sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
                    client_id=spotify_client_id,
                    client_secret=spotify_client_secret
                ))
                results = sp.playlist_items(playlist_id, limit=15, market="US")
            except Exception as e2:
                # return None or raise depending on your app design
                return None
        else:
            return None

    tracks = []
    for item in results.get('items', []):
        track = item.get('track')
        if not track:
            continue
        track_name = track.get('track')
        artist_name = ", ".join([a['name'] for a in track.get('artists', [])])
        # alt_track = url_for('static', filename='audio/dummy-audio.mp3') ## url_for() wont work in the threading executor
        alt_track = '/static/audio/dummy-audio.mp3'

        # Safely call your iTunes helper
        track_url = get_itunes_preview(track_name, artist_name, limit=1, country="US")

        # Use the preview URL if found, else fallback to your dummy audio
        track_itunes_url = track_url.get('itunes_url') if track_url and track_url.get(
            'itunes_url') else alt_track

        tracks.append({
            "name": track.get('name'),
            "artist": ", ".join([a['name'] for a in track.get('artists', [])]),
            "album": track.get('album', {}).get('name'),
            "image": track.get('album', {}).get('images', [{}])[-1].get('url'),
            "track_id": track.get('id'),
            "itunes_url": track_itunes_url,
            "playlist_id": playlist_id
        })
    return tracks

# SPOTIFY SERVER ACCESS ENDS HERE

# Using Last.fm live global chart
LAST_FM_BASE_URL = "http://ws.audioscrobbler.com/2.0/"
def get_live_global_top_tracks(limit=50):
    params = {
        "method": "chart.gettoptracks",
        "api_key": last_fm_api_key,
        "format": "json",
        "limit": limit
    }

    response = requests.get(LAST_FM_BASE_URL, params=params)
    data = response.json()

    sp, source = get_spotify_client_for_request(current_user)
    print(f"get_live_chart:: spotify app: {sp},\n source: {source}")

    tracks = []
    def data_extraction(item,sp):
        track_name = item["name"]
        artist_name = item["artist"]["name"]

        # Search Spotify for this track to get its Spotify ID
        spotify_id = None
        try:
            results = sp.search(q=f"track:{track_name} artist:{artist_name}", type="track", limit=1)
            items = results["tracks"]["items"]
            if items:
                spotify_id = items[0]["id"]
        except Exception as e:
            print(f"Error searching Spotify for {track_name}: {e}")

        img_url = get_artist_image(artist_name, 5, sp=sp) ## This needs to be quicker. Figure it out
        # alt_track = url_for('static', filename='audio/dummy-audio.mp3') ## url_for() wont work because its inside a threading executor
        alt_track = '/static/audio/dummy-audio.mp3'

        # Safely call your iTunes helper
        track_url = get_itunes_preview(track_name, artist_name, limit=1, country="US")


        # Use the preview URL if found, else fallback to your dummy audio
        track_itunes_url = track_url.get('itunes_url') if track_url and track_url.get(
            'itunes_url') else alt_track

        track_info = {
                "name": track_name,
                "artist": artist_name,
                "url": item["url"],
                "image": img_url,
                "spotify_song_id": spotify_id,  # ✅ now you can use this in JS for add-to-playlist
                "itunes_url": track_itunes_url
            }
        return track_info, spotify_id

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(data_extraction, item, sp) for item in data["tracks"]["track"]]
        for future in as_completed(futures):
            track_information, spotify_id = future.result()
            tracks.append(track_information)
            print(f"spotify song id: {spotify_id}")
    return tracks

def get_itunes_preview(song_name, artist_name=None, limit=1, country="US"):
    base_url = "https://itunes.apple.com/search"
    query = f"{song_name} {artist_name}" if artist_name else song_name
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept": "application/json"
    }
    params = {
        "term": query,
        "media": "music",
        "entity": "song",
        "limit": limit,
        "country": country
    }

    try:
        response = requests.get(base_url, params=params, headers=headers, timeout=10)
        response.raise_for_status()  # raises HTTPError for bad responses

        # Check if the response has valid JSON
        if not response.text.strip():
            print(f"⚠️ Empty response for {query} ({country})")
            return None

        try:
            data = response.json()
        except ValueError:
            print(f"⚠️ Invalid JSON from iTunes for {query} ({country})")
            return None

        if data.get("resultCount", 0) > 0:
            song = data["results"][0]
            return {
                "track_name": song.get("trackName"),
                "artist_name": song.get("artistName"),
                "album_name": song.get("collectionName"),
                "preview_url": song.get("previewUrl"),
                "artwork_url": song.get("artworkUrl100"),
                "itunes_url": song.get("trackViewUrl")
            }
        else:
            return None

    except requests.RequestException as e:
        print(f"⚠️ Request failed for {query} ({country}): {e}")
        return None

def latest_albums(sp):
    # Collect album info
    albums_data = []
    unique_album_names = set()

    # Get new releases
    new_releases = sp.new_releases(country="US", limit=50)  # ask for more, then filter top 10

    for album in new_releases["albums"]["items"]:
        album_name = album["name"]

        # Skip duplicates by name
        if album_name in unique_album_names:
            continue

        artist_name = ", ".join(artist["name"] for artist in album["artists"])
        main_artist = album['artists'][0]['name']
        album_info = {
            "album_id": album["id"],
            "album_name": album_name,
            "artist_name": artist_name,
            "album_image": album["images"][0]["url"] if album["images"] else get_artist_image(artist_name, 0, sp),
            "release_date": album.get("release_date"),
            "main_artist": main_artist
        }

        albums_data.append(album_info)
        unique_album_names.add(album_name)

        # Stop when we have 10 unique albums
        if len(albums_data) >= 10:
            break

    # Sort by release date (newest first)
    albums_data = sorted(albums_data, key=lambda x: x["release_date"], reverse=True)
    return albums_data

# get time tag for Home Data
new_time_tag = datetime.now(timezone.utc)

# SORTING OUT THE LOADING ISSUE

loading_message = {
    "is_loading": False,
    "message": "idle"
}

@app.route('/app-status', methods=['GET','POST'])
def get_app_status():
    return jsonify(loading_message)

# def dom_initial_loader():
#     return render_template('initial_loader.html')

# import inspect ## for getting some info like current line
# from concurrent.futures import ThreadPoolExecutor, as_completed


def fetch_json(url):
    """ Fetch function for quick requests. Returns a response (not yet converted to json object)"""
    response = requests.get(url)
    response.raise_for_status()  # catches HTTP errors
    return response

def fetch_artist(artist,sp):
    img_url = get_artist_image(artist, 5, sp=sp)
    return artist, img_url

@app.route('/', methods=['GET','POST'])
def home():
    # dom_initial_loader()
    loading_message.update({
        "is_loading": True,
        "message": "Authenticating..."
    })

    delete_upload_folder() #delete upload_folder once user gets to home page
    create_upload_folder() #create a new empty folder for future use

    print(f"Is current user authenticated: {current_user.is_authenticated}, Current User Id: {current_user.id if current_user.is_authenticated else None}")
    current_user_id = current_user.id if current_user.is_authenticated else None
    # Get the latest saved home data
    home_data_exist = HomeData.query.filter_by(user_id=current_user_id).order_by(HomeData.id.desc()).first()
    # home_data_exist = HomeData.query.first()
    loading_message.update({
        "is_loading": True,
        "message": "Loading data..."
    })
    if should_run_24h_task(current_user_id) or (not home_data_exist and current_user_id is None):
        print("enter-1st if")
        # Fetch Top Album
        # print('Starting threading...')
        with ThreadPoolExecutor(max_workers=7) as executor:
            futures = {
                "i_tunes_top_albums": executor.submit(fetch_json, i_tunes_top_albums_url),
                "i_tunes_top_songs": executor.submit(fetch_json, i_tunes_top_songs_url),
                "get_billboard_top_artists": executor.submit(get_billboard_top_artists, 10),
                "get_spotify_client_for_request": executor.submit(get_spotify_client_for_request, current_user),
                "top_albums_info": executor.submit(top_albums_info),
                "best_hits_2025_id": executor.submit(get_spotify_playlist_tracks, best_hits_2025_id),
                "get_live_global_top_tracks": executor.submit(get_live_global_top_tracks,10)
            }

            # Collect results
            results = {key: future.result() for key, future in futures.items()}

        print('i-tunes album request', f' -- current line: {inspect.currentframe().f_lineno}')
        try:
            album_result = results['i_tunes_top_albums']
        except requests.exceptions.RequestException:
            album_result = None
        loading_message.update({
            "is_loading": True,
            "message": "Please hold on. This might take a few minutes..."
        })
        print('i-tunes album request completed', f' -- current line: {inspect.currentframe().f_lineno}')
        if album_result:
            album_json = album_result.json()
            print(album_json)
            album_contents=album_json["feed"]["results"]
            album_name = album_contents[0]['name']  # use [0] for #1 album
            album_art_url = album_contents[0]['artworkUrl100']
            album_art = get_artwork_url(album_art_url, 1000)
            top_album_id = album_contents[0]['id']
            print(album_art)
        else:
            album_contents = build_deezer_album_dataset(50)
            if album_contents:
                album_name = album_contents[0]['album_name']  # use [0] for #1 album
                album_art = album_contents[0]['artwork_url_original']
                top_album_id = album_contents[0]['album_id']
                print(album_art)

        # Fetch Top Song
        print('i tunes songs request', f' -- current line: {inspect.currentframe().f_lineno}')
        song_result = results['i_tunes_top_songs']
        if song_result:
            song_json = song_result.json()
            print(song_json)
            song_contents = song_json["feed"]["results"]
            if song_contents:
                song_name = song_contents[0]['name']  # use [0] for #1 song
                song_art_url = song_contents[0]['artworkUrl100']
                song_art = get_artwork_url(song_art_url, 1000)
                song_id = song_contents[0]['id']
                print(f'song id: {song_id}')
        else:
            songs = build_deezer_song_dataset(100)
            if songs:
                song_name = songs[0]["song_name"]
                song_art = songs[0]["artwork_url_original"]
                song_id = songs[0]["song_id"]
                print(song_name, song_id)
        print('i tunes song request completed', f' -- current line: {inspect.currentframe().f_lineno}')

        # Fetch Top Artist
        print('retrieve get_billboard_top_artists', f' -- current line: {inspect.currentframe().f_lineno}')
        top_artist_name = results['get_billboard_top_artists']  # Top artist this week

        top_artist_name=top_artist_name[0]
        print(top_artist_name)
        print('retrieve get_billboard_top_artists completed', f' -- current line: {inspect.currentframe().f_lineno}')

        sp, source = results['get_spotify_client_for_request']
        print(f"Home:: spotify app: {sp},\n source: {source}")

        print('retrieve get_artist_image', f' -- current line: {inspect.currentframe().f_lineno}')
        artist_art = get_artist_image(top_artist_name, 0, sp=sp)
        print(artist_art)
        print('retrieve get_artist_image completed', f' -- current line: {inspect.currentframe().f_lineno}')

        print('retrieve top_albums_info', f' -- current line: {inspect.currentframe().f_lineno}')
        top_albums = results['top_albums_info']
        print('retrieve top_albums_info completed', f' -- current line: {inspect.currentframe().f_lineno}')

        print("retrieve get_spotify_playlist_tracks", f' -- current line: {inspect.currentframe().f_lineno}')
        best_ten_hits = results['best_hits_2025_id'] ## This is where the issue is. Then implement threading for simultaneous function call
        print("retrieve get_spotify_playlist_tracks completed", f' -- current line: {inspect.currentframe().f_lineno}')

        if best_ten_hits:  # only slice if not None
            best_ten_hits_2025 = best_ten_hits[:10]
        else:
            best_ten_hits_2025 = []  # or some default/fallback

        print('retrieve get_live_global_top_tracks', f' -- current line: {inspect.currentframe().f_lineno}')
        this_weeks_10 = results['get_live_global_top_tracks']
        print('retrieve get_live_global_top_tracks completed', f' -- current line: {inspect.currentframe().f_lineno}')

        if this_weeks_10:  # only slice if not None
            this_weeks_10_hits = this_weeks_10[:10]
        else:
            this_weeks_10_hits = []  # or some default/fallback

        loading_message.update({
            "is_loading": True,
            "message": "Initializing..."
        })
        # FETCH TOP ARTISTS SECTION
        artist_section_dict = {}
        print('retrieve get_billboard_top_artists', f' -- current line: {inspect.currentframe().f_lineno}')
        top_artists_list = results['get_billboard_top_artists']
        print('retrieve get_billboard_top_artists completed', f' -- current line: {inspect.currentframe().f_lineno}')

        print('compile top_artist_list', f' -- current line: {inspect.currentframe().f_lineno}')
        # for artist in top_artists_list:
        #     img_url = get_artist_image(artist, 5, sp=sp)
        #     artist_section_dict[artist] = img_url  # assign key-value pair

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(fetch_artist, artist, sp) for artist in top_artists_list]
            for future in as_completed(futures):
                artist, img_url = future.result()
                artist_section_dict[artist] = img_url

        print(artist_section_dict)
        print('compile top_artist_list completed', f' -- current line: {inspect.currentframe().f_lineno}')

        # load to database
        new_home_data = HomeData(
            album_art=album_art,
            album_name=album_name,
            song_art=song_art,
            song_name=song_name,
            song_id=song_id,
            artist_art=artist_art,
            artist_name=top_artist_name,
            top_albums=top_albums,
            best_2025_hits=best_ten_hits_2025,
            this_weeks_hits=this_weeks_10_hits,
            artist_section_dict=artist_section_dict,
            album_id=top_album_id,
            user_id=current_user.id if current_user.is_authenticated else None,
            new_time_tag=new_time_tag
        )
        db.session.add(new_home_data)
        db.session.commit()
        return render_template('index.html',
                               album_art=album_art,
                               album_name=album_name,
                               song_art=song_art,
                               song_name=song_name,
                               song_id=song_id,
                               artist_art=artist_art,
                               artist_name=top_artist_name,
                               top_albums=top_albums,
                               best_2025_hits=best_ten_hits_2025,
                               this_weeks_hits=this_weeks_10_hits,
                               artist_section_dict=artist_section_dict,
                               album_id=top_album_id
                               )
    else:
        print("enter-1st else")
        # latest_data = HomeData.query.filter_by(user_id=current_user_id).order_by(HomeData.id.desc()).first()
        latest_data = HomeData.query.filter_by(new_time_tag=new_time_tag).order_by(HomeData.id.desc()).first()
        if current_user_id and latest_data and latest_data.user_id is None:
           # update the latest data
           latest_data.user_id = current_user_id
           db.session.commit()

        # Get the latest saved home data
        if not latest_data:
            data = HomeData.query.order_by(HomeData.id.desc()).first() # Testing, remove if not ok
        else:
            data = HomeData.query.filter_by(user_id=current_user_id).order_by(HomeData.id.desc()).first()

        # Convert JSON fields back to Python lists/dicts
        import json
        ## its already stored as Json in the Database
        top_albums = data.top_albums
        best_ten_hits_2025 = data.best_2025_hits
        this_weeks_10_hits = data.this_weeks_hits
        artist_section_dict = data.artist_section_dict

        # Rebuild EXACT SAME VARIABLES your template expects
        album_art = data.album_art
        album_name = data.album_name
        song_art = data.song_art
        song_name = data.song_name
        song_id = data.song_id
        artist_art = data.artist_art
        top_artist_name = data.artist_name
        top_album_id = data.album_id

        # LOGGED IN SECTION
        if current_user.is_authenticated:
            print("enter-1st else 1st if")

            # data = HomeData.query.order_by(HomeData.id.desc()).first()
            if not data.feature_artists_info:
                print('generating feature_artists_info', f' -- current line: {inspect.currentframe().f_lineno}')
                print("enter-1st else 1st if 1st if")
                print(f"You have reached if current_user.is_authenticated. Artist name {top_artist_name}")
                # For modal playlist
                access_token = get_valid_spotify_token(current_user)
                if not access_token:
                    return None  # User not logged in or no valid token
                sp = spotipy.Spotify(auth=access_token)

                ## Start important threads
                with ThreadPoolExecutor(max_workers=3) as executor:
                    futures = {
                        "get_user_playlists": executor.submit(get_user_playlists,current_user, sp, 1, "playlist", "small"),
                        "top_artist_info": executor.submit(top_artist_info,top_artist_name),
                        "get_artist_description": executor.submit(get_artist_description,top_artist_name, last_fm_api_key),
                    }

                    # Collect results
                    results = {key: future.result() for key, future in futures.items()}

                print('retrieve get_user_playlists', f' -- current line: {inspect.currentframe().f_lineno}')
                playlist_list = results['get_user_playlists']
                print('retrieve get_user_playlists completed', f' -- current line: {inspect.currentframe().f_lineno}')

                print('retrieve top_artist_info', f' -- current line: {inspect.currentframe().f_lineno}')
                feature_artists_info = results['top_artist_info']
                print('retrieve top_artist_info completed', f' -- current line: {inspect.currentframe().f_lineno}')

                print('retrieve get_artist_description', f' -- current line: {inspect.currentframe().f_lineno}')
                artist_description = results['get_artist_description']
                print('retrieve get_artist_description completed', f' -- current line: {inspect.currentframe().f_lineno}')
                print(artist_description)
                print('retrieve get_album_tracks_sorted', f' -- current line: {inspect.currentframe().f_lineno}')
                top_artist_album_track = get_album_tracks_sorted(feature_artists_info['album_name'])
                print('retrieve get_album_tracks_sorted completed', f' -- current line: {inspect.currentframe().f_lineno}')

                print(f"Playlist List: {playlist_list}")
                print(f"artist description: {artist_description}")
                # Delete initial home data

                new_home_data = HomeData(
                    album_art=album_art,
                    album_name=album_name,
                    song_art=song_art,
                    song_name=song_name,
                    song_id=song_id,
                    artist_art=artist_art,
                    artist_name=top_artist_name,
                    top_albums=top_albums,
                    feature_artists_info=feature_artists_info,
                    artist_description=artist_description,
                    top_artist_album_track=top_artist_album_track,
                    best_2025_hits=best_ten_hits_2025,
                    this_weeks_hits=this_weeks_10_hits,
                    artist_section_dict=artist_section_dict,
                    album_id=top_album_id,
                    user_id=current_user.id if current_user.is_authenticated else None,
                    new_time_tag=new_time_tag
                )
                db.session.add(new_home_data)
                db.session.commit()

            else:
                print('feature_artists_info exists in data', f' -- current line: {inspect.currentframe().f_lineno}')
                print("enter-1st else 1st if 1st else")
                access_token = get_valid_spotify_token(current_user)
                if not access_token:
                    return None  # User not logged in or no valid token
                sp = spotipy.Spotify(auth=access_token)

                import json
                # 5️⃣ Convert JSON fields back to Python objects (we will do it directly because our JSON data is not text. It is already stored as a list
                feature_artists_info = data.feature_artists_info
                artist_description = data.artist_description  # string, no conversion needed
                top_artist_album_track = data.top_artist_album_track
                # The spotify playlist data has to be gotten live, not from the database
                print('retrieve get_user_playlists', f' -- current line: {inspect.currentframe().f_lineno}')
                playlist_list = get_user_playlists(current_user, sp, 1, "playlist", "small")
                # 6️⃣ Reconstruct variables exactly as your template expects
                print('retrieve get_user_playlists complete', f' -- current line: {inspect.currentframe().f_lineno}')

            return render_template('index.html', playlist_list=playlist_list,
                                       album_art=album_art,
                                       album_name=album_name,
                                       song_art=song_art,
                                       song_name=song_name,
                                       song_id=song_id,
                                       artist_art=artist_art,
                                       artist_name=top_artist_name,
                                       top_albums=top_albums,
                                       feature_artists_info=feature_artists_info,
                                       artist_description=artist_description,
                                       top_artist_album_track=top_artist_album_track,
                                       best_2025_hits=best_ten_hits_2025,
                                       this_weeks_hits=this_weeks_10_hits,
                                       artist_section_dict=artist_section_dict,
                                       album_id=top_album_id
                                       )

        return render_template('index.html',
                               album_art=album_art,
                               album_name=album_name,
                               song_art=song_art,
                               song_name=song_name,
                               song_id=song_id,
                               artist_art=artist_art,
                               artist_name=top_artist_name,
                               top_albums=top_albums,
                               best_2025_hits=best_ten_hits_2025,
                               this_weeks_hits=this_weeks_10_hits,
                               artist_section_dict=artist_section_dict,
                               album_id=top_album_id
        )

@app.route('/add_to_playlist', methods=['POST'])
def add_to_playlist():
    if not current_user.is_authenticated:
        return jsonify({'error': 'User not logged in'}), 401

    data = request.get_json()
    playlist_id = data.get('playlist_id')
    track_id = data.get('track_id')

    if not playlist_id or not track_id:
        return jsonify({'error': 'Missing playlist_id or track_id'}), 400

    # Get authenticated Spotify client
    sp, source = get_spotify_client_for_request(current_user)

    if not sp:
        return jsonify({'error': 'Unable to connect to Spotify API'}), 500

    try:
        sp.playlist_add_items(playlist_id, [f"spotify:track:{track_id}"])
        return jsonify({'success': True, 'message': 'Song added successfully!'})
    except Exception as e:
        print("Error adding song:", e)
        return jsonify({'error': 'Failed to add song to playlist'}), 500


@app.route('/playlist')
def playlist():
    access_token = get_valid_spotify_token(current_user)
    if not access_token:
        return None  # User not logged in or no valid token
    sp = spotipy.Spotify(auth=access_token)

    playlist_list = get_user_playlists(current_user, sp, 1,"playlist", "small")
    refresh_user_library(current_user, sp, playlist_list)

    new_album = latest_albums(sp)


    return render_template('albums-store.html',
                           playlist_list=playlist_list,
                           latest_albums=new_album)

@app.route('/playlist-page/<playlist_id>', methods=["GET", "POST"])
@login_required
def playlist_page(playlist_id):
    access_token = get_valid_spotify_token(current_user)
    if not access_token:
        return None  # User not logged in or no valid token
    sp = spotipy.Spotify(auth=access_token)

    playlist1 = sp.playlist(playlist_id)
    playlist_tracks = get_playlist_tracks(current_user, sp, playlist_id)
    playlist_image = get_playlist_image(current_user, sp, playlist_id, 0, "playlist", "full")
    playlist_list = get_user_playlists(current_user, sp, 1, "playlist", "small")
    # Query DB for stats
    stats = db.session.query(
        func.avg(Songs.popularity).label("avg_popularity"),
        func.sum(Songs.duration_ms).label("total_duration_ms")
    ).filter(Songs.spotify_playlist_id == playlist_id).first()

    avg_popularity = int(stats.avg_popularity) if stats.avg_popularity else 0
    total_duration_ms = stats.total_duration_ms or 0
    total_duration = int(total_duration_ms/3600000) # total duration rundown in hours

    # Convert duration from ms → hours:minutes:seconds
    # seconds = total_duration_ms // 1000
    # minutes, seconds = divmod(seconds, 60)
    # hours, minutes = divmod(minutes, 60)
    # total_duration_str = f"{hours}h {minutes}m {seconds}s"

    return render_template('playlist_page.html',
                           playlist1=playlist1,
                           playlist_tracks=playlist_tracks,
                           avg_popularity = avg_popularity,
                           total_duration = total_duration,
                           playlist_image=playlist_image,
                           playlist_list=playlist_list
                           )


def extract_main_artist(full_artist):
    if not full_artist:
        return None

    # Remove anything in parentheses e.g. (feat. ...)
    cleaned = re.sub(r'\(.*?\)', '', full_artist)

    # Split on 'and', '&', ',', or 'feat.' variations
    parts = re.split(r'\s*(?:,|&|and|feat\.?|featuring)\s*', cleaned, flags=re.IGNORECASE)

    # Take the first non-empty artist name
    main_artist = parts[0].strip() if parts else None

    return main_artist


def audio_mack_scrape(url, sp, limit=10):
    global AFRO_TOP_TRACKS, AFRO_RECENT_TRACKS, AFRO_TRENDING_TRACKS, AFRO_TRENDING_ALBUMS, AFRO_TOP_ALBUMS

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }

    response = requests.get(url, headers=headers)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    song_blocks = soup.find_all("div", class_="ChartsItem-content")
    song_blocks=song_blocks[:limit]

    songs_or_album = []
    default_id = 111111111
    for block in song_blocks:
        data_div = block.find("div", class_="ChartsItem-data")

        if not data_div:
            continue

        # Artist and song title (as before)
        artist_tag = data_div.find("h2", class_="ChartsItem-artist")
        title_tag = data_div.find("h2", class_="ChartsItem-title")

        artist = artist_tag.get_text(strip=True) if artist_tag else "Unknown Artist"
        title = title_tag.get_text(strip=True) if title_tag else "Unknown Title"

        if url in [AFRO_TOP_TRACKS, AFRO_TRENDING_TRACKS, AFRO_RECENT_TRACKS]:
            spotify_song_id = None  # initialize before checking results
            spotify_image_url = None

            result = sp.search(q=f"track:{title} artist:{artist}", type="track", limit=1)

            if result and result.get("tracks", {}).get("items"):
                track_info = result["tracks"]["items"][0]
                spotify_song_id = track_info["id"]
                # Extract the album image (usually 640px, 300px, 64px)
                images = track_info.get("album", {}).get("images", [])
                if images:
                    spotify_image_url = images[0]["url"]  # largest image

            main_artist = extract_main_artist(artist)
            songs_or_album.append({
                "artist": artist,
                "title": title,
                "main_artist": main_artist,  # new field added
                "spotify_song_id": spotify_song_id if spotify_song_id else default_id,
                "artist_image": spotify_image_url if spotify_image_url else get_artist_image(main_artist,4,sp)
            })

        else:

            spotify_album_id = None
            spotify_album_image = None

            result = sp.search(q=f"album:{title} artist:{artist}", type="album", limit=1)

            if result and result.get("albums", {}).get("items"):
                album_info = result["albums"]["items"][0]
                spotify_album_id = album_info["id"]

                # Extract the album cover image (usually 640px, 300px, 64px)
                images = album_info.get("images", [])
                if images:
                    spotify_album_image = images[0]["url"]  # largest image

            main_artist = extract_main_artist(artist)
            songs_or_album.append({
                "artist": artist,
                "title": title,
                "main_artist": main_artist,  # new field added
                "spotify_album_id": spotify_album_id if spotify_album_id else default_id,  # fixed name for clarity
                "album_image": spotify_album_image if spotify_album_image else get_artist_image(main_artist,4,sp)
            })
    return songs_or_album



@app.route('/afro-beats')
def afro_beats():
    sp, source = get_spotify_client_for_request(current_user)
    print(f"get_live_chart:: spotify app: {sp},\nsource: {source}")

    top_tracks = audio_mack_scrape(AFRO_TOP_TRACKS, sp,10)
    trending_tracks = audio_mack_scrape(AFRO_TRENDING_TRACKS, sp,10)
    recent_tracks = audio_mack_scrape(AFRO_RECENT_TRACKS, sp,10)
    top_albums = audio_mack_scrape(AFRO_TOP_ALBUMS, sp,10)
    trending_albums = audio_mack_scrape(AFRO_TRENDING_ALBUMS, sp,10)

    top_afro_artist = top_albums[0]['main_artist']
    top_afro_artist_img = get_artist_image(top_afro_artist,0,sp)

    top_afro_artist_album = top_albums[0]['title']
    top_afro_album_song = get_album_tracks_sorted(top_afro_artist_album)


    top_afro_artist_info = top_artist_info(top_afro_artist)

    if current_user.is_authenticated:
        # For modal playlist
        access_token = get_valid_spotify_token(current_user)
        if not access_token:
            return None  # User not logged in or no valid token
        sp = spotipy.Spotify(auth=access_token)

        playlist_list = get_user_playlists(current_user, sp, 1, "playlist", "small")
        return render_template('afro-beats.html', playlist_list=playlist_list,
                               top_tracks=top_tracks,
                               trending_tracks=trending_tracks,
                               recent_tracks=recent_tracks,
                               top_albums=top_albums,
                               trending_albums=trending_albums,
                               top_afro_artist_img=top_afro_artist_img,
                               top_afro_album_song=top_afro_album_song,
                               top_afro_artist_info=top_afro_artist_info
                               )
    return render_template('afro-beats.html',
                           top_tracks=top_tracks,
                           trending_tracks=trending_tracks,
                           recent_tracks=recent_tracks,
                           top_albums=top_albums,
                           trending_albums=trending_albums,
                           top_afro_artist_img=top_afro_artist_img,
                           top_afro_album_song=top_afro_album_song,
                           top_afro_artist_info=top_afro_artist_info
                           )





@app.route('/about-us', defaults={'name': None}, methods=["GET", "POST"])
@app.route('/about-us/<name>', methods=["GET", "POST"])
def about_us(name):

    # 1. Handle POST FIRST so it doesn't get skipped
    if request.method == "POST":
        review_comment = request.form.get("search")

        new_review_comment = ReviewComment(
            text=review_comment,
            author_id=current_user.id
        )
        db.session.add(new_review_comment)
        db.session.commit()
        flash("Your review has been saved.", 'success')

        return redirect(url_for('about_us'))

    # 2. Now handle GET page routing
    if name is None:
        review_data = ReviewComment.query.order_by(ReviewComment.created_at).all()
        return render_template('event.html', sorted_data=review_data)

    if name == "overview":
        return render_template('about_overview.html')

    if name == "discover":
        return render_template('about_discover.html')

    if name == "new_releases":
        return render_template('about_new_releases.html')

    if name == "newsroom":
        return render_template('about_newsroom.html')

    if name == "local_spotify":
        return render_template('about_local_spotify.html')

    if name == "playlist_hub":
        return render_template('about_playlist_hub.html')

    # 3. Any other invalid section fallback
    return redirect(url_for('about_us'))



# @app.route('/overview')
# def about_overview_page():
#     return render_template('about_overview.html')

DEFAULT_IMAGE = '/static/img/music_blog_def_image.jpeg'

def fetch_newsdata_news():
    url = f"https://newsdata.io/api/1/news?apikey={news_data_api_key}&q=music&language=en"
    response = requests.get(url)
    articles = []

    if response.status_code == 200:
        data = response.json()
        for item in data.get("results", []):
            pub_Date = item.get("pubDate", "")
            pub_date = date_parser.parse(pub_Date) if pub_Date else None

            if pub_date:
                formatted_date = pub_date.isoformat()
                db_date = pub_date
                year = pub_date.year
                month = pub_date.strftime('%b')  # abbreviated month name (e.g. Oct)
                day = pub_date.day
            else:
                formatted_date = ""
                year = ""
                month = ""
                day = ""

            articles.append({
                "source": item.get("source_id", "NewsData.io"),
                "title": item.get("title", "No title"),
                "description": item.get("description", "No description available"),
                "content": item.get("content", "No content"),
                "link": item.get("link", "#"),
                "pubDate": formatted_date,
                "dbDate": db_date,
                "image_url": item.get("image_url") if item.get("image_url") else DEFAULT_IMAGE,
                "year": year,
                "month": month,
                "day": day
            })
    return articles



def fetch_billboard_news():
    feed_url = "https://www.billboard.com/feed/"
    feed = feedparser.parse(feed_url)
    articles = []

    for entry in feed.entries:
        # Try to find image in media_content or description
        image_url = DEFAULT_IMAGE
        if hasattr(entry, "media_content") and entry.media_content:
            image_url = entry.media_content[0].get("url", DEFAULT_IMAGE)
        elif "img" in entry.description:
            import re
            match = re.search(r'<img.*?src="(.*?)"', entry.description)
            if match:
                image_url = match.group(1)

        pub_date_raw = entry.get("published", "")
        try:
            pub_date_obj = date_parser.parse(pub_date_raw)
            db_date = pub_date_obj
            formatted_date = pub_date_obj.isoformat()
            year = pub_date_obj.year
            month = pub_date_obj.strftime("%b")  # abbreviated month (e.g. Oct)
            day = pub_date_obj.day
        except Exception:
            formatted_date = ""
            year = ""
            month = ""
            day = ""

        articles.append({
            "source": "Billboard",
            "title": entry.get("title", "No title"),
            "description": entry.get("summary", "No description available"),
            "content": entry.get("summary", "No content"),
            "link": entry.get("link", "#"),
            "pubDate": formatted_date,
            "dbDate": db_date,
            "image_url": image_url if image_url else DEFAULT_IMAGE,
            "year": year,
            "month": month,
            "day": day
        })
    return articles



def get_combined_music_news():
    newsdata_news = fetch_newsdata_news()
    billboard_news = fetch_billboard_news()
    all_news = newsdata_news + billboard_news

    latest_id = db.session.query(func.max(BlogPost.created_id)).scalar() or 0
    for i, news in enumerate(all_news, start=1):
        news['created_id'] = latest_id + i

    # Sort by most recent pubDate
    def parse_date(article):
        try:
            dt = date_parser.parse(article["pubDate"])
            if dt.tzinfo is None:
                dt = pytz.UTC.localize(dt)
            else:
                dt = dt.astimezone(pytz.UTC)
            return dt

        except Exception as e:
            print("Error parsing date:", e)
            return datetime.min.replace(tzinfo=pytz.UTC)
    all_news.sort(key=parse_date, reverse=True) # this is where the sorting happens and the 'helper function' is activated
    return all_news


def load_news_to_db():
    news_feed = get_combined_music_news()
    for feed in news_feed:
        exists = db.session.execute(
            db.select(BlogPost).filter_by(news_link=feed['link'])
        ).scalar()
        if not exists:
            new_blog_post = BlogPost(
                source=feed["source"],
                title=feed["title"],
                subtitle=feed["description"],
                body=feed["content"],
                date=feed["dbDate"],
                img_url=feed["image_url"],
                created_id=feed["created_id"],
                news_link=feed["link"],
                day=feed["day"],
                month=feed["month"],
                year=feed["year"]
            )
            db.session.add(new_blog_post)
    db.session.commit()

with app.app_context():
    load_news_to_db()

def trim_news_table():
    subquery = (
        db.session.query(BlogPost.id)
        .order_by(BlogPost.date.desc())
        .offset(100)
    )
    db.session.query(BlogPost).filter(BlogPost.id.in_(subquery)).delete(synchronize_session=False)
    db.session.commit()
    print("Old records trimmed.")


@app.route('/news-blog', methods=["GET", "POST"])
def news_blog():
    # --- Delete excess record -- #
    trim_news_table()

    # --- Get news from BlogPost --- #
    news_post = db.session.execute(
        db.select(BlogPost).order_by(BlogPost.date.desc())
    ).scalars().all()

    news_post=news_post[:75]
    # --- Pagination setup ---
    per_page = 5  # number of posts per page
    page = request.args.get('page', 1, type=int)

    # Slice data for current page
    start = (page - 1) * per_page
    end = start + per_page
    paginated_news = news_post[start:end]

    # Calculate total pages
    total_pages = (len(news_post) + per_page - 1) // per_page

    # --- Fetch posts and comment counts ---
    posts_with_counts = (
        db.session.query(
            BlogPost,
            func.count(Comment.id).label("comment_count")
        )
        .outerjoin(Comment, Comment.post_id == BlogPost.id)
        .group_by(BlogPost.id)
        .all()
    )

    # Convert to dictionary for easier Jinja access
    post_dict = {post.created_id: count for post, count in posts_with_counts}

    notice_data = HomeData.query.order_by(HomeData.id.desc()).first()
    if notice_data:
        album_name = notice_data.album_name
        album_id = notice_data.album_id
        album_art = notice_data.album_art if notice_data else "static/img/bg-img/add.gif"
        song_name = notice_data.song_name
        song_id = notice_data.song_id
        song_art = notice_data.song_art if notice_data else "static/img/bg-img/add2.gif"

    return render_template(
        'blog.html',
        news_feed=paginated_news,
        page=page,
        total_pages=total_pages,
        comment_counts=post_dict,
        album_name=album_name,
        album_id=album_id,
        album_art=album_art,
        song_name=song_name,
        song_id=song_id,
        song_art=song_art
    )


@app.route('/blog-post/<int:post_id>', methods=["GET", "POST"])
def blog_post(post_id):
    post = db.session.scalar(
        db.select(BlogPost).where(BlogPost.created_id == post_id).limit(1)
    )
    if post is None:
        abort(404)

    form = CommentForm()

    if form.validate_on_submit():
        if not current_user.is_authenticated:
            flash("You need to login or register to comment.", 'error')
            return redirect(url_for("login_page"))

        new_comment = Comment(
            text=form.comment_text.data,
            comment_author=current_user,
            parent_post=post
        )

        db.session.add(new_comment)
        db.session.commit()

        # FIXED: pass post_id correctly
        return redirect(url_for('blog_post', post_id=post_id))
    return render_template("blog_post.html", post=post, form=form)


@app.route("/delete-comment/<int:comment_id>", methods=["POST"])
@login_required  # optional, if you use Flask-Login
def delete_comment(comment_id):
    comment = db.get_or_404(Comment, comment_id)

    # Only allow deletion by the comment author or an admin
    if comment.author_id != current_user.id:
        abort(403)  # Forbidden

    db.session.delete(comment)
    db.session.commit()
    flash("Comment deleted successfully.", "info")
    return redirect(request.referrer or url_for("blog_post", post_id=comment.post_id))


@app.route('/login-page', methods=["GET","POST"])
def login_page():
    next_page = request.args.get('next')

    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        result = db.session.execute(db.select(User).where(User.email == email))
        # Note, email in db is unique so will only have one result.
        user = result.scalar()
        # Email doesn't exist
        if not user:
            flash("That email does not exist, please try again.", "error")
            return redirect(url_for('login_page'))
        # Password incorrect
        elif not check_password_hash(user.password, password):
            flash('Password incorrect, please try again.',"error")
            return redirect(url_for('login_page'))
        else:
            login_user(user)
            print(f'is current_user authenticated: {current_user.is_authenticated}')

            # Add update the login time to the scheduler to avoid  repeat long load because of Using
            now = datetime.now(timezone.utc)
            status = (
                SchedulerStatus.query
                .filter_by(user_id=current_user.id)
                .order_by(SchedulerStatus.last_run.desc())
                .first()
            )
            if status:
                status.last_run = now  #update before leaving page


            if next_page:
                return redirect(next_page)
            else:
                return redirect(url_for('home'))
    return render_template('login.html', current_user=current_user)

@app.route('/register-page', methods=["GET","POST"])
def register_page():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        verify_password = request.form.get("verify_password")

        if password != verify_password:
            flash("Passwords do not match!", "error")
            return redirect(url_for('register_page'))

        # Check if user email is already present
        result = db.session.execute(db.select(User).where(User.email == email))
        user = result.scalar()
        if user:
            flash("You've already signed up with that email, log in instead!", "success")
            return redirect(url_for('login_page'))

        hash_and_salted_password = generate_password_hash(
            password,
            method='pbkdf2:sha256',
            salt_length=8
        )
        new_user = User(
            email=email,
            password=hash_and_salted_password,
        )
        db.session.add(new_user)
        db.session.commit()

        login_user(new_user)
        return redirect(url_for("spotify_login"))  # Don't include `.html` here
    return render_template('register.html', current_user=current_user)

@app.route('/song-page/<song_id>', methods=['GET', 'POST'])
def song_page(song_id):
    sp, source = get_spotify_client_for_request(current_user)
    print(f"get_live_chart:: spotify app: {sp},\nsource: {source}")
    try:
        # 1. Get from iTunes (track lookup)
        itunes_url = f"https://itunes.apple.com/lookup?id={song_id}&entity=song"
        itunes_data = requests.get(itunes_url).json()

        if not itunes_data.get("results"):
            raise ValueError("Song not found in iTunes")

        itunes_song = itunes_data["results"][0]
        song_name = itunes_song.get("trackName")
        artist_name = itunes_song.get("artistName")
        song_genre = itunes_song.get("primaryGenreName", "")
        song_genre = song_genre.lower() if song_genre else None

    except Exception as e:
        print(f"iTunes lookup failed: {e}. Using Spotify lookup...")
        # 2. Fallback to Spotify track details
        spotify_result = sp.track(song_id)
        if spotify_result:
            song_name = spotify_result.get("name")
            artist_name = spotify_result["artists"][0]["name"] if spotify_result.get("artists") else None
            song_genre = None  # Spotify doesn’t include genre for tracks directly
        else:
            deezer_track = requests.get(f"https://api.deezer.com/track/{song_id}").json()

            song_name = deezer_track.get("title")
            artist_name = deezer_track["artist"]["name"] if deezer_track.get("artist") else None
            album_name = deezer_track["album"]["title"] if deezer_track.get("album") else None
            album_cover = deezer_track["album"]["cover_big"] if deezer_track.get("album") else None

    # 3. Spotify data (search track by name + artist)
    spotify_song_data = None
    result = sp.search(q=f"track:{song_name} artist:{artist_name}", type="track", limit=1)

    if result["tracks"]["items"]:
        spotify_song_id = result["tracks"]["items"][0]["id"]
        spotify_song_data = sp.track(spotify_song_id)

    # 3. Last.fm data (track info)
    lastfm_url = (
        f"http://ws.audioscrobbler.com/2.0/?method=track.getInfo"
        f"&api_key={last_fm_api_key}&artist={artist_name}&track={song_name}&format=json"
    )
    lastfm_song_data = requests.get(lastfm_url).json().get("track")

    # 4. Merge into one dict
    # Ensure all dicts are safe to access
    itunes_song = itunes_song if 'itunes_song' in locals() and isinstance(itunes_song, dict) else {}
    spotify_song_data = spotify_song_data if 'spotify_song_data' in locals() else {}

    song_data = {
        "song_name": song_name,
        "artist_name": artist_name,

        "itunes": {
            "artwork": get_artwork_url(itunes_song.get("artworkUrl100"), 1000) if itunes_song else spotify_song_data["album"]["images"][0]['url'],
            "release_date": itunes_song.get("releaseDate") if itunes_song else spotify_song_data["album"]["release_date"],
            "genre": itunes_song.get("primaryGenreName") if itunes_song else None,
            "itunes_url": itunes_song.get("trackViewUrl") if itunes_song else None
        },

        "spotify": {
            "id": spotify_song_data.get("id") if spotify_song_data else None,
            "url": spotify_song_data["external_urls"]["spotify"] if spotify_song_data else None,
            "popularity": spotify_song_data.get("popularity") if spotify_song_data else None,
            "duration_ms": spotify_song_data.get("duration_ms") if spotify_song_data else None,
            "preview_url": spotify_song_data.get("preview_url") if spotify_song_data else None,
            "release_date": spotify_song_data["album"][
                "release_date"] if spotify_song_data and "album" in spotify_song_data else None,

            "album": {
                "id": spotify_song_data["album"]["id"] if spotify_song_data and "album" in spotify_song_data else None,
                "name": spotify_song_data["album"]["name"] if spotify_song_data and "album" in spotify_song_data else None,
                "images": spotify_song_data["album"]["images"] if spotify_song_data and "album" in spotify_song_data else []
            },
            "artist_id": spotify_song_data["artists"][0]["id"] if spotify_song_data and spotify_song_data.get("artists") else None,
            "artist_name": spotify_song_data["artists"][0]["name"] if spotify_song_data and spotify_song_data.get("artists") else artist_name
        },

        "lastfm": {
                "url": lastfm_song_data.get("url") if lastfm_song_data else None,
                "listeners": lastfm_song_data.get("listeners") if lastfm_song_data else None,
                "playcount": lastfm_song_data.get("playcount") if lastfm_song_data else None,
                "summary": lastfm_song_data.get("wiki", {}).get("summary") if lastfm_song_data else None,
                "tags": [tag["name"] for tag in lastfm_song_data.get("toptags", {}).get("tag", [])] if lastfm_song_data else []
        }
    }

    song_album_tracks = []

    album = sp.album(song_data['spotify']['album']['id'])
    for track in album["tracks"]["items"]:
        # Priority 1: Spotify album image
        image_url = None
        if track.get("album") and track["album"].get("images"):
            image_url = track["album"]["images"][0]["url"]

        # Priority 2: Fallback to iTunes artwork
        elif itunes_song and itunes_song.get("artworkUrl100"):
            image_url = get_artwork_url(itunes_song.get("artworkUrl100"), 140)

        # Priority 3: Fallback to artist image
        else:
            image_url = get_artist_image(artist_name, 4, sp)

        # Add track data
        song_album_tracks.append({
            "id": track["id"],
            "name": track["name"],
            "artist": ", ".join([a["name"] for a in track["artists"]]),
            "image": image_url
        })

    # valid_genres = sp.recommendation_genre_seeds()
    # print(f"valid spotify genres: {valid_genres["genres"]}")

    # LETS GET SONG GENRE
    artist_info = sp.artist(song_data['spotify']['artist_id'])
    genres = artist_info["genres"]

    # recommended_tracks = []
    # recommendations = sp.recommendations(seed_tracks=[song_data['spotify']['id']],
    #                                      seed_artists=[song_data['spotify']['artist_id']],
    #                                      seed_genres=[song_genre],
    #                                      limit=10)

    # for track in recommendations['tracks']:
    #     recommended_tracks.append({
    #         "id": track['id'],
    #         "name": track['name'],
    #         "artist": ", ".join([a["name"] for a in track["artists"]]),
    #         "image": track["album"]["images"][0]["url"] if track.get("album") and track["album"].get(
    #             "images") else get_artwork_url(itunes_song.get("artworkUrl100"), 140)
    #     })
    if current_user.is_authenticated:
        # For modal playlist
        access_token = get_valid_spotify_token(current_user)
        if not access_token:
            return None  # User not logged in or no valid token
        sp = spotipy.Spotify(auth=access_token)

        playlist_list = get_user_playlists(current_user, sp, 1, "playlist", "small")
        return render_template("song.html",
                               song_data=song_data,
                               song_album_tracks=song_album_tracks,
                               # recommended_tracks=recommended_tracks,
                               playlist_list=playlist_list
                               )
    return render_template("song.html",
                           song_data=song_data,
                           song_album_tracks=song_album_tracks,
                           # recommended_tracks=recommended_tracks
                           )


from datetime import datetime, date

def _parse_release_date(release_date, precision):
    """
    Normalize Spotify release_date + precision into a date object.
    precision: 'day', 'month', 'year'
    """
    if not release_date:
        return date.min
    try:
        if precision == "day":
            return datetime.strptime(release_date, "%Y-%m-%d").date()
        if precision == "month":
            return datetime.strptime(release_date, "%Y-%m").date()
        # precision == "year"
        return datetime.strptime(release_date, "%Y").date()
    except Exception:
        return date.min

@app.route('/artist-page/<artist>', methods=['GET','POST'])
def artist_page(artist):
    loading_state = True
    sp, source = get_spotify_client_for_request(current_user)

    # 1. iTunes lookup (best-effort)
    itunes_url = f"https://itunes.apple.com/search?term={artist}&entity=musicArtist&limit=1"
    itunes_data = requests.get(itunes_url).json()
    itunes_artist = itunes_data["results"][0] if itunes_data.get("results") else {}
    artist_name = itunes_artist.get("artistName", artist)

    # 2. Spotify: find artist
    spotify_artist_data = None
    spotify_artist_id = None
    spotify_top_tracks = []
    spotify_related_artists = []
    spotify_albums = []
    latest_tracks = []

    result = sp.search(q=f"artist:{artist_name}", type="artist", limit=1)
    if result.get("artists", {}).get("items"):
        spotify_artist_id = result["artists"]["items"][0]["id"]
        spotify_artist_data = sp.artist(spotify_artist_id)

        # top tracks (country code depending on your target audience)
        try:
            top_tracks_data = sp.artist_top_tracks(spotify_artist_id, country='US')
            spotify_top_tracks = top_tracks_data.get("tracks", [])[:10]
        except Exception:
            spotify_top_tracks = []

        # related artists
        try:
            related = sp.artist_related_artists(spotify_artist_id)
            spotify_related_artists = related.get("artists", [])[:10]
        except Exception:
            spotify_related_artists = []

        # fetch albums & singles (paged)
        albums = []
        offset = 0
        page_limit = 50
        while True:
            try:
                page = sp.artist_albums(spotify_artist_id,
                                        album_type='album,single',
                                        limit=page_limit,
                                        offset=offset)
            except Exception:
                break
            items = page.get("items", [])
            if not items:
                break
            albums.extend(items)
            if len(items) < page_limit:
                break
            offset += page_limit

        # dedupe albums by album id (Spotify can return duplicates for different markets)
        albums_by_id = {}
        for a in albums:
            albums_by_id[a["id"]] = a
        spotify_albums = list(albums_by_id.values())
        print(f"loading_state:{loading_state}")
        # collect tracks from those albums, avoiding duplicates
        seen_track_ids = set()
        collected_tracks = []
        for album in spotify_albums:
            album_id = album.get("id")
            album_name = album.get("name")
            album_images = album.get("images", [])
            album_release = album.get("release_date")
            album_precision = album.get("release_date_precision", "day")
            parsed_date = _parse_release_date(album_release, album_precision)

            # fetch tracks for the album (one call per album)
            try:
                album_tracks_page = sp.album_tracks(album_id)
            except Exception:
                continue
            for t in album_tracks_page.get("items", []):
                tid = t.get("id")
                if not tid or tid in seen_track_ids:
                    continue
                seen_track_ids.add(tid)

                # Build track entry. Note: preview_url may be null; duration_ms available.
                track_entry = {
                    "id": tid,
                    "name": t.get("name"),
                    "artists": ", ".join([a["name"] for a in t.get("artists", [])]),
                    "album_id": album_id,
                    "album_name": album_name,
                    "album_images": album_images,
                    "release_date": album_release,
                    "release_date_precision": album_precision,
                    "release_date_parsed": parsed_date,    # date object to sort by
                    "preview_url": t.get("preview_url"),
                    "duration_ms": t.get("duration_ms"),
                    'track_image': album_images[-1]['url'] if album_images else url_for('static', filename='img/core-img/insertion-140x140-05.jpg')
                }
                collected_tracks.append(track_entry)

        # sort newest -> oldest and keep top N
        collected_tracks.sort(key=lambda x: x["release_date_parsed"], reverse=True)
        latest_tracks = collected_tracks[:10]   # tune N as you need

    # 3. Last.fm data (artist)
    lastfm_url = (
        f"http://ws.audioscrobbler.com/2.0/?method=artist.getInfo"
        f"&artist={artist_name}&api_key={last_fm_api_key}&format=json"
    )
    lastfm_artist_data = requests.get(lastfm_url).json().get("artist")

    # Getting artist latest album info/tracks
    artist_info = top_artist_info(artist_name)
    artist_latest_album = artist_info['album_name']
    artist_latest_album_id = artist_info['album_id']
    # Fetch album tracks
    album_tracks_data = sp.album_tracks(artist_latest_album_id)

    # Get all track items
    album_tracks = album_tracks_data.get("items", [])

    artist_latest_album_info = []

    for track in album_tracks:
        # Extract track artists
        track_artists = [artist["name"] for artist in track.get("artists", [])]
        track_artist_names = ", ".join(track_artists)

        # Append track details
        artist_latest_album_info.append({
            'track_name': track.get("name"),
            'track_id': track.get("id"),
            'track_artists': track_artist_names,
            'track_image': get_artist_image(artist_name, 4, sp)
        })


    # 4. Merge
    artist_data = {
        "artist_name": artist_name,
        "itunes": {
            "artist_id": itunes_artist.get("artistId"),
            "itunes_url": itunes_artist.get("artistLinkUrl")
        },
        "spotify": {
            "id": spotify_artist_id,
            "url": spotify_artist_data.get("external_urls", {}).get("spotify") if spotify_artist_data else None,
            "followers": spotify_artist_data.get("followers", {}).get("total") if spotify_artist_data else None,
            "genres": spotify_artist_data.get("genres") if spotify_artist_data else [],
            "popularity": spotify_artist_data.get("popularity") if spotify_artist_data else None,
            "top_tracks": spotify_top_tracks,
            "albums": spotify_albums,
            "related_artists": spotify_related_artists,
            "latest_tracks": latest_tracks,
            "artist_art": get_artist_image(artist_name, 0, sp=sp),
            "artist_latest_album": artist_latest_album,
            "artist_latest_album_id": artist_latest_album_id
        },
        "lastfm": {
            "url": lastfm_artist_data.get("url") if lastfm_artist_data else None,
            "listeners": lastfm_artist_data.get("stats", {}).get("listeners") if lastfm_artist_data else None,
            "playcount": lastfm_artist_data.get("stats", {}).get("playcount") if lastfm_artist_data else None,
            "summary": lastfm_artist_data.get("bio", {}).get("summary") if lastfm_artist_data else None
        }
    }

    artist_top_tracks = []
    for track in artist_data['spotify']['top_tracks']:
        track_name = track.get("name")
        track_id = track.get("id")
        track_artist_name = ", ".join([artist["name"] for artist in track.get("artists", [])])
        # Join multiple artist names into one string

        artist_top_tracks.append({
            "track_name": track_name,
            "track_id": track_id,
            "artist_names": track_artist_name ,
            "track_image": get_artist_image(artist_name, 4, sp)
        })

    related_artists_data = []

    for artist in artist_data['spotify']['related_artists']:
        r_artist_id = artist.get("id", "N/A")
        r_artist_name = artist.get("name", "Unknown Artist")
        r_artist_image = get_artist_image(r_artist_name,4, sp)

        related_artists_data.append({
            "id": r_artist_id,
            "name": r_artist_name,
            "image": r_artist_image,
            "latest_album": top_artist_info(r_artist_name)
        })
    # convert date objects to ISO strings for easy template consumption
    for t in artist_data["spotify"]["latest_tracks"]:
        if isinstance(t.get("release_date_parsed"), date):
            t["release_date_iso"] = t["release_date_parsed"].isoformat()
        else:
            t["release_date_iso"] = None

    album_results = sp.artist_albums(artist_id=spotify_artist_id, album_type='album', limit=20)

    # Extract album info
    artist_albums = []
    for album in album_results['items']:
        artist_albums.append({
            "name": album['name'],
            "id": album['id'],
            "release_date": album['release_date'],
            "total_tracks": album['total_tracks'],
            "url": album['external_urls']['spotify'],
            "image": album['images'][-1]['url'] if album['images'] else url_for('static', filename='img/core-img/insertion-140x140-05.jpg')
        })
    loading_state=False
    print(f"loading_state:{loading_state}")
    if current_user.is_authenticated:
        # For modal playlist
        access_token = get_valid_spotify_token(current_user)
        if not access_token:
            return None  # User not logged in or no valid token
        sp = spotipy.Spotify(auth=access_token)

        playlist_list = get_user_playlists(current_user, sp, 1, "playlist", "small")
        return render_template("artist.html",
                               artist_data=artist_data,
                               playlist_list=playlist_list,
                               artist_top_tracks=artist_top_tracks,
                               related_artists_data=related_artists_data,
                               artist_albums=artist_albums,
                               artist_latest_album_info=artist_latest_album_info,
                               loading_state=loading_state)#CONTINUE FROM HERE: RENDER IN ARTIST PAGE
    return render_template("artist.html",
                           artist_data=artist_data,
                           artist_top_tracks=artist_top_tracks,
                           related_artists_data=related_artists_data,
                           artist_albums=artist_albums,
                           artist_latest_album_info=artist_latest_album_info,
                           loading_state=loading_state)




@app.route('/album-page/<album_id>', methods=['GET', 'POST'])
def album_page(album_id):
    sp, source = get_spotify_client_for_request(current_user)
    print(f"album_page:: spotify app: {sp}, source: {source}")

    # Heuristic: iTunes IDs are numeric, Spotify IDs are alphanumeric
    is_numeric_id = album_id.isdigit()
    print(f"is_itunes_id: {is_numeric_id}")
    itunes_album = None
    spotify_album_data = None
    album_name = None
    artist_name = None

    try:
        if is_numeric_id:
            # --- iTunes lookup ---
            itunes_url = f"https://itunes.apple.com/lookup?id={album_id}&entity=album"
            itunes_data = requests.get(itunes_url).json()
            if itunes_data.get("resultCount", 0) > 0:
                if not itunes_data.get("results"):
                    raise ValueError("Album not found in iTunes")

                itunes_album = itunes_data["results"][0]
                album_name = itunes_album.get("collectionName")
                artist_name = itunes_album.get("artistName")

                result = sp.search(q=f"album:{album_name} artist:{artist_name}", type="album", limit=1)
                if result["albums"]["items"]:
                    spotify_album_data = result["albums"]["items"][0]
                    spot_album_id = spotify_album_data.get('id')
                    tracks_data = sp.album_tracks(spot_album_id)
                    spot_album_data = sp.album(spot_album_id)
            else:
                url = f"https://api.deezer.com/album/{album_id}"
                data = requests.get(url).json()

                if data.get("error"):
                    print("Error:", data["error"])
                    return None

                album_name = data.get("title")
                artist_name = data["artist"]["name"] if data.get("artist") else None
                album_image = data.get("cover_xl")

                result = sp.search(q=f"album:{album_name} artist:{artist_name}", type="album", limit=1)
                if result["albums"]["items"]:
                    spotify_album_data = result["albums"]["items"][0]
                    spot_album_id = spotify_album_data.get('id')
                    tracks_data = sp.album_tracks(spot_album_id)
                    spot_album_data = sp.album(spot_album_id)

        else:
            # --- Spotify lookup ---
            spotify_album_data = sp.album(album_id)

            album_name = spotify_album_data.get("name")
            artist_name = (
                spotify_album_data["artists"][0]["name"] if spotify_album_data.get("artists") else None
            )
            tracks_data = sp.album_tracks(album_id)
            spot_album_data = sp.album(album_id)

    except Exception as e:
        print(f"Album lookup failed: {e}. Attempting fallback search...")
        # --- fallback search (cross-platform) ---
        if not is_numeric_id:
            # Spotify failed → try iTunes
            itunes_url = f"https://itunes.apple.com/search?term={album_id}&entity=album&limit=1"
            itunes_data = requests.get(itunes_url).json()
            if itunes_data.get("results"):
                itunes_album = itunes_data["results"][0]
                album_name = itunes_album.get("collectionName")
                artist_name = itunes_album.get("artistName")

                result = sp.search(q=f"album:{album_name} artist:{artist_name}", type="album", limit=1)
                if result["albums"]["items"]:
                    spotify_album_data = result["albums"]["items"][0]
                    spot_album_id = spotify_album_data.get('id')
                    tracks_data = sp.album_tracks(spot_album_id)
        else:
            # iTunes failed → try Spotify
            result = sp.search(q=f"album:{album_id}", type="album", limit=1)
            if result["albums"]["items"]:
                spotify_album_data = sp.album(result["albums"]["items"][0]["id"])
                spotify_album_data = spotify_album_data["albums"]["items"][0]
                print(f"album data: {spotify_album_data}")
                album_name = spotify_album_data.get("name")
                artist_name = (
                    spotify_album_data["artists"][0]["name"]
                    if spotify_album_data.get("artists")
                    else None
                )
                tracks_data = sp.album_tracks(album_id)
                spot_album_data = sp.album(album_id)


    # 3. Last.fm data
    lastfm_url = (
        f"http://ws.audioscrobbler.com/2.0/?method=album.getInfo"
        f"&api_key={last_fm_api_key}&artist={artist_name}&album={album_name}&format=json"
    )
    lastfm_album_data = requests.get(lastfm_url).json().get("album")

    try:
        # First try iTunes artwork
        artwork = get_artwork_url(itunes_album["artworkUrl100"], 1000)
    except Exception:
        # If iTunes fails → fallback to Spotify
        try:
            artwork = spotify_album_data["images"][0]["url"]
        except Exception:
            artwork = album_image


    # 4. Merge into one dict
    album_data = {
        "album_name": album_name,
        "artist_name": artist_name,
        "itunes": {
            "artwork": artwork,
            "release_date": itunes_album.get("releaseDate") if itunes_album else spotify_album_data["release_date"],
            # "genre": itunes_album.get("primaryGenreName"),
            # "itunes_url": itunes_album.get("collectionViewUrl")
        },
        "spotify": {
            "id": spotify_album_data.get("id") if spotify_album_data else None,
            "url": spotify_album_data["external_urls"]["spotify"] if spotify_album_data else None,
            "release_date": spotify_album_data["release_date"] if spotify_album_data else None,
            "popularity": spot_album_data["popularity"] if spot_album_data else None,
            "tracks": tracks_data if tracks_data else []
        },
        "lastfm": {
            "url": lastfm_album_data.get("url") if lastfm_album_data else None,
            "listeners": lastfm_album_data.get("listeners") if lastfm_album_data else None,
            "playcount": lastfm_album_data.get("playcount") if lastfm_album_data else None,
            # "tags": [tag["name"] for tag in
            #          lastfm_album_data.get("tags", {}).get("tag", [])] if lastfm_album_data else [],
            "summary": lastfm_album_data.get("wiki", {}).get("summary") if lastfm_album_data else None
        }
    }
    default_album_image = url_for('static', filename='img/insertion-140x140-04.jpg')
    album_tracks = []
    for track in tracks_data['items']:
        album_info = track.get("album")

        # Priority 1: Spotify album image (if album_info is a dict with images)
        if isinstance(album_info, dict) and album_info.get("images"):
            image_url = album_info["images"][0]["url"]

        # Priority 2: Fallback to iTunes artwork
        elif itunes_album and itunes_album.get("artworkUrl100"):
            image_url = get_artwork_url(itunes_album.get("artworkUrl100"), 140)

        # Priority 3: Fallback to artist image
        else:
            image_url = get_artist_image(artist_name, 4, sp)

        album_tracks.append({
            "id": track.get("id"),
            "name": track.get("name"),
            "artist": ", ".join([a["name"] for a in track.get("artists", [])]),
            "image": image_url
        })

    if current_user.is_authenticated:
        # For modal playlist
        access_token = get_valid_spotify_token(current_user)
        if not access_token:
            return None  # User not logged in or no valid token
        sp = spotipy.Spotify(auth=access_token)

        playlist_list = get_user_playlists(current_user, sp, 1, "playlist", "small")
        return render_template('album.html',
                               album_data=album_data,
                               album_tracks=album_tracks,
                               playlist_list=playlist_list
                               )
    # 5. Render template
    return render_template('album.html',
                           album_data=album_data,
                           album_tracks=album_tracks,
                           )

# VALIDATE THE TOKEN
def get_valid_spotify_token(user):

    """Return a valid Spotify access token for the given user, refreshing if expired."""
    sp_oauth = SpotifyOAuth(
        client_id=spotify_client_id,
        client_secret=spotify_client_secret,
        redirect_uri=spotify_redirect_uri,
        scope=spotify_scope,
        cache_handler = DBTokenCache(current_user, db)  # 👈 use DB cache
    )
    # if not user.is_authenticated:
    #     return None  # or redirect to login

    access_token = user.spotify_acc_tok
    refresh_token = user.spotify_ref_tok

    # If no token at all → go to login


    if not access_token:
        return None

    # Check token validity
    try:
        sp = spotipy.Spotify(auth=access_token)
        sp.current_user()  # If this fails, token is probably expired
        return access_token
    except spotipy.exceptions.SpotifyException as e:
        if e.http_status == 401 and refresh_token:
            # Token expired → refresh
            token_info = sp_oauth.refresh_access_token(refresh_token)
            new_access_token = token_info['access_token']

            # Update DB
            user.spotify_acc_tok = new_access_token
            db.session.commit()

            return new_access_token
        else:
            # Other Spotify error
            raise

# EXTRACT USER PLAYLIST
def get_user_playlists(user, sp, image_size, ph_query, ph_size):  # ph_query, ph_size is for the placeholder image
    """Fetch all playlists for the given Spotify user."""
    if not sp:
        access_token = get_valid_spotify_token(user)
        if not access_token:
            return None  # User not logged in or no valid token
        sp = spotipy.Spotify(auth=access_token, requests_timeout=30)

    playlists = []

    results = sp.current_user_playlists(limit=50)

    while results:
        for item in results['items']:
            playlists.append({
                "id": item['id'],
                "name": item['name'],
                "owner": item['owner']['display_name'],
                "tracks": item['tracks']['total'],
                "image": get_playlist_image(user, sp, item["id"], image_size, ph_query, ph_size),
                "description": item['description'],
                "public": item['public'],  # ✅ (optional) whether playlist is public/private
                "num_tracks": len(get_playlist_tracks(current_user, sp, item['id']))
            })
        # Pagination: check if there’s another page
        if results['next']:
            results = sp.next(results)
        else:
            results = None
    return playlists




def get_placeholder_image(query="music", size="regular"):
    url = f"https://api.unsplash.com/photos/random?query={query}&client_id={unsplash_access_key}"
    response = requests.get(url).json()
    return response["urls"][size]



def get_playlist_image(user, sp, playlist_id, image_size, ph_query, ph_size):
    if not sp:
        access_token = get_valid_spotify_token(user)
        if not access_token:
            return None
        sp = spotipy.Spotify(auth=access_token)

    playlist = sp.playlist(playlist_id)
    images = playlist.get("images", [])

    if images:
        # Return the image at the requested index (0=largest, 1=medium, 2=small)
        if image_size < len(images):
            return images[image_size]["url"]
        else:
            return images[0]["url"]  # fallback to first available
    else:
        # No playlist image -> fallback to first track image or Unsplash
        tracks = get_playlist_tracks(user, sp, playlist_id)
        if tracks and tracks[0]["image"]:
            if image_size < len(tracks[0]["image"]):
                return tracks[0]["image"][image_size]['url']
            return tracks[0]["image"][0]['url']
        else:
            return get_placeholder_image(ph_query, ph_size)



def get_playlist_tracks(user, sp, playlist_id):
    """Fetch all tracks from a playlist with pagination."""
    if not sp:
        access_token = get_valid_spotify_token(user)
        if not access_token:
            return None  # No valid token

        sp = spotipy.Spotify(auth=access_token)

    tracks = []

    results = sp.playlist_items(playlist_id)
    tracks.extend(results['items'])

    while results['next']:
        results = sp.next(results)
        tracks.extend(results['items'])

    track_data = []
    for t in tracks:
        track = t['track']
        if not track:   # sometimes a track may be null (removed/unavailable)
            continue
        song_data = {
            "id": track['id'],
            "name": track['name'],
            "album": track['album']['name'],
            "image": track['album']['images'][0]['url'],
            "artist": format_artists(track),
            "duration_ms": track['duration_ms'],
            "popularity": track['popularity'],
            "preview_url": track['preview_url'],
            "external_url": track['external_urls']['spotify']
        }
        track_data.append(song_data)

    return track_data

# We need to format how the artist name comes out
def format_artists(track):
    """Format artist names as 'Main Artist ft. Others'."""
    artists = [artist['name'] for artist in track['artists']]

    if len(artists) == 1:
        return artists[0]  # just one artist

    # First artist is usually the main one
    main_artist = artists[0]
    featured = artists[1:]

    return f"{main_artist} ft. {', '.join(featured)}"


def refresh_user_library(user, sp, playlists):

    # Step 2.1: Clear the user playlist record (so db stays in sync)
    db.session.query(Playlist).filter_by(spotify_user_id=user.spotify_user_id).delete()

    # Step 2.2: Clear this user’s old songs (so DB stays in sync)
    db.session.query(Songs).filter_by(spotify_user_id=user.spotify_user_id).delete()

    # Step 3: Insert fresh songs
    for playlist in playlists:

        playlist_update = Playlist(
            name = playlist["name"],
            description = playlist["description"],
            spotify_playlist_id = playlist['id'],
            spotify_user_id = user.spotify_user_id

        )
        db.session.add(playlist_update)

        tracks = get_playlist_tracks(user, sp, playlist['id'])
        for track in tracks:
            song = Songs(
                track_id=track['id'],
                name=track['name'],
                album=track['album'],
                artist=track['artist'],
                duration_ms=track['duration_ms'],
                popularity=track['popularity'],
                preview_url=track['preview_url'],
                external_url=track['external_url'],
                spotify_playlist_id=playlist['id'],
                spotify_user_id=user.spotify_user_id
            )
            db.session.add(song)
    db.session.commit()
    return True


# Route: User clicks "Create Playlist"
@app.route('/create-playlist', methods=['GET', 'POST'])
@login_required
def create_playlist():
    # store the page you came from by getting it from the url
    next_page = request.args.get('next')
    print('callback_url: ', next_page)
    # Get a valid token or redirect if none
    access_token = get_valid_spotify_token(current_user)
    if not access_token:
        return redirect(url_for('spotify_login'))

    current_spotify_user = current_user.spotify_user_id

    if request.method == "POST":
        name_of_playlist = request.form.get("name")
        des_of_playlist = request.form.get("description")

        # Check if a playlist with same name already exists for this Spotify user
        existing_playlist = db.session.execute(
            db.select(Playlist).where(
                Playlist.name == name_of_playlist,
                Playlist.spotify_user_id == current_spotify_user
            )
        ).scalar_one_or_none()

        if existing_playlist:   # ✅ No .name, just check directly
            flash("The Playlist name already exists! Try a different name.", "error")
            return redirect(url_for('create_playlist'))

        # Token exists → Use it
        sp = spotipy.Spotify(auth=access_token)
        me = sp.current_user()
        spotify_user_id2 = me["id"]

        # Create playlist on Spotify
        new_playlist_in_spotify = sp.user_playlist_create(
            user=spotify_user_id2,
            name=name_of_playlist,
            description=des_of_playlist
        )
        spotify_playlist_id = new_playlist_in_spotify["id"]

        # Save playlist in DB, make sure to store spotify_user_id too!
        new_playlist_data = Playlist(
            name=name_of_playlist,
            description=des_of_playlist,
            spotify_playlist_id=spotify_playlist_id,
            spotify_user_id=current_spotify_user   # ✅ store ownership
        )

        db.session.add(new_playlist_data)
        db.session.commit()

        if next_page:
            return redirect(next_page)
        else:
            return redirect(url_for('playlist'))
    return render_template('create-playlist.html')


# Route: Start Spotify login
@app.route('/spotify-login')
# @login_required
def spotify_login():
    sp_oauth = SpotifyOAuth(
        client_id=spotify_client_id,
        client_secret=spotify_client_secret,
        redirect_uri=spotify_redirect_uri,
        scope= spotify_scope,
        cache_handler = DBTokenCache(current_user,db)  # 👈 use DB cache
    )
    # Create a CSRF 'state' token and remember it in the session
    state = secrets.token_urlsafe(16)
    session['spotify_oauth_state'] = state   #NOTE:  Make sure you uncomment after testing

    # Build the authorize URL with the same state
    auth_url = sp_oauth.get_authorize_url(state=state) # state=state put this inside the parameter after testing

    # webbrowser.get(r'"C:\Program Files\Google\Chrome\Application\chrome.exe" --incognito %s').open(auth_url)
    return redirect(auth_url)

    # # ✅ Return something valid so Flask is happy
    # return "Spotify login opened in a new incognito browser window. Please continue there."

# Route: Spotify callback with authorization code
@app.route('/callback')
# @login_required
def spotify_callback():
    sp_oauth = SpotifyOAuth(
        client_id=spotify_client_id,
        client_secret=spotify_client_secret,
        redirect_uri=spotify_redirect_uri,
        scope= spotify_scope,
        cache_handler = DBTokenCache(current_user, db)  # 👈 use DB cache
    )

    # Spotify sends ?code=...&state=... (or ?error=...)
    error = request.args.get('error')
    if error:
        # The user may have denied access or an error occurred
        abort(400, f"Spotify authorization error: {error}")

    returned_state = request.args.get('state')
    if not returned_state or returned_state != session.get('spotify_oauth_state'):
        abort(400, "State mismatch. Possible CSRF or stale session.")  #NOTE: Make sure you uncomment after development

    code = request.args.get('code')
    if not code:
        abort(400, "Missing authorization code.")


    token_info = sp_oauth.get_access_token(code)

    # Fetch and store the Spotify user id once
    sp = spotipy.Spotify(auth=token_info['access_token'])
    spotify_user_id = sp.me()['id']

    access_token = token_info['access_token']
    refresh_token = token_info['refresh_token']

    # Store tokens in your DB for the current user
    current_user.spotify_acc_tok = access_token
    current_user.spotify_ref_tok = refresh_token
    current_user.spotify_user_id = spotify_user_id
    db.session.commit()

    return redirect(url_for('create_playlist'))




# SUGGESTED PLACES TO PICK SONGS FOR PLAYLIST
@app.route('/US-top-40-songs')
def US_top_40_songs():
    return render_template('US_top_40.html')

@app.route('/top-hits-time-travel')
def time_travel_hits():
    return render_template('time_travel_hits.html')

@app.route('/suggested-songs')
def AI_suggested_songs():
    return render_template('AI_suggestions.html')

@app.route('/award-winning-songs')
def award_winning_songs():
    return render_template('award_winning_songs.html')

MAIL_ADDRESS = os.environ.get("EMAIL_KEY")
MAIL_APP_PW = os.environ.get("PASSWORD_KEY")

@app.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        data = request.form
        send_email(data["name"], data["email"], data["subject"], data["message"])
        flash("Message sent successfully! Thank you for the feedback.", "success")
        return redirect(url_for('contact'))
    return render_template("contact.html", msg_sent=False)


def send_email(name, email, subject, message):
    # Create MIME message
    msg = MIMEMultipart()
    msg['From'] = MAIL_ADDRESS
    msg['To'] = "donatusudeani@outlook.com"
    msg['Subject'] = f"***SSPIDERR*** {name}: {subject}"

    message_to_send = (f"{message}\n\n\nSender: {email}")
    # Attach message content
    msg.attach(MIMEText(message_to_send, 'plain', 'utf-8'))

    # Send email
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as connection:
        # connection.starttls()
        connection.login(user=MAIL_ADDRESS, password=MAIL_APP_PW)
        connection.sendmail(from_addr=MAIL_ADDRESS, to_addrs="donatusudeani@outlook.com", msg=msg.as_string())



def billboard_scraper(endpoint="hot-100", selected_date=None):
    # ensure endpoint always has a valid value
    if not endpoint:
        endpoint = "hot-100"

    URL = (
        f"https://www.billboard.com/charts/{endpoint}/{selected_date}"
        if selected_date
        else f"https://www.billboard.com/charts/{endpoint}"
    )

    endpoint_char = endpoint.split('-')

    if any(word in endpoint_char for word in ['album', 'albums']):
        endpoint_type = 'albums'
    elif any(word in endpoint_char for word in ['artist', 'artists']):
        endpoint_type = 'artists'
    else:
        endpoint_type = 'songs'

    response = requests.get(URL, timeout=10)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    name_tags = soup.select("li.o-chart-results-list__item h3")
    artist_tags = soup.select("li.o-chart-results-list__item span.c-label.a-no-trucate")

    results = []

    for name_tag, artist_tag in zip(name_tags[:10], artist_tags[:10]):
        song_name = html.unescape(name_tag.get_text(strip=True))
        artist_raw = html.unescape(artist_tag.get_text(strip=True))

        # 1) Normalize whitespace
        s = artist_raw.strip()

        # 2) Replace common connectors with a comma using word boundaries where appropriate.
        #    Use case-insensitive matching and make sure we don't accidentally match inside words.
        s = re.sub(r"(?i)\b(?:feat\.?|featuring)\b", ",", s)   # feat or featuring -> comma
        s = re.sub(r"[&xX\+]", ",", s)                         # &, x, + -> comma

        # 3) If words were concatenated (e.g. "DJ SnakeFeaturingSelena"), try to insert a space
        #    only where there's a lowercase followed by an uppercase letter and the uppercase is
        #    the start of a typical name (Upper followed by lowercase).
        s = re.sub(r"(?<=[a-z])(?=[A-Z][a-z])", " ", s)

        # 4) Normalize commas/spaces: replace any sequence of commas/spaces with a single comma + space
        s = re.sub(r"\s*,\s*", ", ", s)
        s = re.sub(r"\s+", " ", s).strip()
        s = re.sub(r"(,\s*){2,}", ", ", s)  # collapse repeated commas

        # 5) Final clean-up: remove leading/trailing commas/spaces
        s = s.strip(" ,")

        # 6) Extract main artist = first segment before the first comma
        main_artist = re.split(r",|\bfeaturing\b|\bfeat\.?\b", s, flags=re.IGNORECASE)[0].strip() if s else ""

        results.append({
            "song": song_name,
            "artist": s,
            "main_artist": main_artist
        })

        print(f"name: {song_name}, artist: {s}, main_artist: {main_artist}")

    return results,endpoint_type

@app.route("/see-whats-new")
def see_whats_new():
    # LOGGED IN SECTION
    if current_user.is_authenticated:
        # For modal playlist
        access_token = get_valid_spotify_token(current_user)
        if not access_token:
            return None  # User not logged in or no valid token
        sp = spotipy.Spotify(auth=access_token)

        playlist_list = get_user_playlists(current_user, sp, 1, "playlist", "small")
        return render_template("see_whats_new.html", playlist_list=playlist_list)
    return render_template("see_whats_new.html")

@app.route('/see-whats-new-results', methods=['GET'] )
def see_whats_new_results():
    sp, source = get_spotify_client_for_request(current_user)
    print(f"album_page:: spotify app: {sp}, source: {source}")

    chart_option = request.args.get("keyword", "hot-100")
    date_str = request.args.get("release-date")  # e.g. "10/20/2025"

    formatted_date = None
    if date_str:
        try:
            # Convert from mm/dd/yyyy → datetime object
            date_obj = datetime.strptime(date_str, "%m/%d/%Y")

            # Format to yyyy-mm-dd (Billboard format)
            formatted_date = date_obj.strftime("%Y-%m-%d")

        except ValueError:
            formatted_date = None  # handle invalid date format safely

    chart_result,endpoint_type = billboard_scraper(chart_option,date_str)

    full_chart_info = []
    if endpoint_type == 'albums':
        for album in chart_result[:10]:
            album_name = album['song']
            album_main_artist = album['main_artist']
            album_artist = album['artist']

            # Search Spotify for the album
            query = f"album:{album_name} artist:{album_main_artist}"
            result = sp.search(q=query, type="album", limit=1)
            if result['albums']['items']:
                album = result['albums']['items'][0]
                album_id = album['id']
                album_image = album['images'][0]['url'] if album['images'] else get_artist_image(album_main_artist,0,sp)

            lastfm_url = (
                f"http://ws.audioscrobbler.com/2.0/?method=album.getInfo"
                f"&api_key={last_fm_api_key}&artist={album_main_artist}&album={album_name}&format=json"
            )
            lastfm_album_data = requests.get(lastfm_url).json().get("album")

            description = lastfm_album_data.get("wiki", {}).get("summary") if lastfm_album_data else None
            if description:
                short_description = description[:250] + "..." if len(description) > 250 else description
            else:
                short_description = "No Description Currently Available!"

            full_chart_info.append({
                'album_name': album_name,
                'album_artist': album_artist,
                'album_main_artist': album_main_artist,
                'spotify_album_id': album_id,
                'image': album_image,
                'description': short_description
            })

    elif endpoint_type=='artists':
        for artist in chart_result[:10]:
            artist_name = artist['song'] #song is what we used to capture all the h3
            artist_image = get_artist_image(artist_name,0, sp)
            artist_description_obj = get_artist_description(artist_name,last_fm_api_key)
            artist_description = artist_description_obj['description']
            short_description = artist_description[:250] + "..." if len(artist_description) > 250 else artist_description
            full_chart_info.append({
                'artist_name': artist_name,
                'artist_image': artist_image,
                'artist_description': short_description
            })

    else:
        for song in chart_result[:10]:
            song_name = song['song']
            song_main_artist = song['main_artist']
            song_artist = song['artist']

            # Search Spotify for the song
            query = f"track:{song_name} artist:{song_main_artist}"
            result = sp.search(q=query, type="track", limit=1)

            if result['tracks']['items']:
                track = result['tracks']['items'][0]

                track_id = track['id']
                album_image = track['album']['images'][0]['url'] if track['album']['images'] else get_artist_image(song_main_artist,4,sp)

            artist_description = get_artist_description(song_main_artist, last_fm_api_key)
            full_chart_info.append({
                'track_name':song_name,
                'track_artist':song_artist,
                'track_main_artist':song_main_artist,
                'spotify_track_id': track_id,
                'image':album_image,
            })

    if current_user.is_authenticated:
        # For modal playlist
        access_token = get_valid_spotify_token(current_user)
        if not access_token:
            return None  # User not logged in or no valid token
        sp = spotipy.Spotify(auth=access_token)

        playlist_list = get_user_playlists(current_user, sp, 1, "playlist", "small")

        return render_template('partials/section_results.html',
                               playlist_list=playlist_list,
                               full_chart_info=full_chart_info,
                               endpoint_type=endpoint_type
                               )
    return render_template('partials/section_results.html',
                           full_chart_info=full_chart_info,
                           endpoint_type=endpoint_type)

# The 'elements' page should be removed after everything
@app.route('/elements')
def elements():
    return render_template('elements.html')


@app.route('/loader-page')
def loader_page():
    access_token = get_valid_spotify_token(current_user)
    if not access_token:
        return None  # User not logged in or no valid token
    sp = spotipy.Spotify(auth=access_token)

    playlist_list = get_user_playlists(current_user, sp, 1, "playlist", "small")

    return render_template('loader-page.html', playlist_list=playlist_list)  # Loads templates/index.html


# Create a folder for uploaded songs
UPLOAD_FOLDER = os.path.join("static", "uploads")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# Allowed music formats
ALLOWED_EXTENSIONS = {".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a"}


def allowed_file(filename):
    ext = os.path.splitext(filename)[1].lower()
    return ext in ALLOWED_EXTENSIONS

@app.route("/upload-song", methods=["POST"])
def file_upload():
    file = request.files.get("file")  # Dropzone sends each file here

    if not file:
        return {"success": False, "message": "No file uploaded!"}, 400

    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)

    if filename.lower().endswith(".zip"):
        return {
            "success": False,
            "message": "ZIP files are not allowed. Upload only music files."
        }, 400

    if not allowed_file(filename):
        return {
            "success": False,
            "message": f"File {filename} is not a supported music format."
        }, 400

    try:
        file.save(filepath)
        return {
            "success": True,
            "filename": filename
        }
    except Exception as e:
        return {
            "success": False,
            "message": str(e)
        }, 500

    # return redirect(url_for('display_uploads'))



# EVERYTHING FOR RECOGNITION

# Directory containing music files
MUSIC_FOLDER = "./Python Music"
MUSIC_FOLDER_2 = "./Music44spotify"

# Output logs
SUCCESS_LOG = "recognized_songs_2.txt"
FAILED_LOG = "failed_songs_2.txt"

# Supported audio formats
AUDIO_EXTS = (".mp3", ".wav", ".m4a")

def clean_title(text):
    return re.sub(r"\(feat.*?\)", "", text, flags=re.IGNORECASE).strip()

# 1. Normal route to render the HTML template
@app.route("/song-processing/<playlist_id>")
def show_song_processing(playlist_id):
    return render_template("song_processing.html", playlist_id=playlist_id)


# These functions are newly introduced to reduce the weight on the generate() function (INITIAL)
STATUS = {
    "recognized": None,
    "not_recognized": None,
    "sent_to_spotify": None,
    "not_sent_to_spotify": None,
    "completed": False,
    "message": None
}

@app.route("/status")
def get_status():
    return jsonify(STATUS)


# 2. SSE stream route (the one I gave you)
@app.route("/song-processing-stream/<playlist_id>")
def song_processing_stream(playlist_id):
    async def recognize_song(file_path, shazam):
        try:
            result = await shazam.recognize(file_path)

            track = result.get("track")
            matches = result.get("matches") or []

            if not track and not matches:
                # No recognition result
                return None, None, None, f"❌ Could not recognize {os.path.basename(file_path)}"

            # Otherwise, recognition succeeded
            title = (track or {}).get("title", "Unknown")
            artist = (track or {}).get("subtitle", "Unknown")
            return title, artist, f"✅ {os.path.basename(file_path)} recognized successfully", None

        except Exception as e:
            return None, None, None, f"⚠️ Failed to recognize {os.path.basename(file_path)}: {e}"

    async def batch_recognize(folder_path):
        # Check if folder exists
        if not os.path.isdir(folder_path):
            print("Folder does not exist")
            return None  # or return [], or raise an error

        shazam = Shazam()
        files = [f for f in os.listdir(folder_path) if f.endswith(AUDIO_EXTS)]

        if not files:
            STATUS.update({
                "recognized": None,
                "not_recognized": None,
                "sent_to_spotify": None,
                "not_sent_to_spotify": None,
                "completed": False,
                "message": "No audio files found"
            })

            print('No Audio files found')
            return []

        STATUS.update({
            "recognized": None,
            "not_recognized": None,
            "sent_to_spotify": None,
            "not_sent_to_spotify": None,
            "completed": False,
            "message": "Recognizing..."
        })
        # print(f"🎧 Found {len(files)} audio files.")
        recognized = []
        failed = []

        song_fraction = len(files)  # This is needed incase we want to limit the songs that can be uploaded
        batch_fraction = 10

        for i, file in enumerate(files, 1):
            full_path = os.path.join(folder_path, file)
            print(f"\n🔍 [{i}/{song_fraction}] Recognizing: {file}")

            STATUS.update({
                "recognized": None,
                "not_recognized": None,
                "sent_to_spotify": None,
                "not_sent_to_spotify": None,
                "completed": False,
                "message": f"\n [{i}/{song_fraction}] Recognizing: {file}"
            })

            title, artist, good_comment, bad_comment = await recognize_song(full_path, shazam)
            if good_comment:
                result_line = f"{file}::{title}::{artist}"
                print(f"✅ {result_line}")
                recognized.append(result_line)

                STATUS.update({
                    "recognized": f"{good_comment}"[:35],
                    "not_recognized": None,
                    "sent_to_spotify": None,
                    "not_sent_to_spotify": None,
                    "completed": False,
                    "message": f"Recognition successful"
                })
            elif bad_comment:  # be careful here you might just need else block
                print(f"❌ Could not recognize: {file}")
                failed.append(file)
                STATUS.update({
                    "recognized": None,
                    "not_recognized": f"{bad_comment}"[:35],
                    "sent_to_spotify": None,
                    "not_sent_to_spotify": None,
                    "completed": False,
                    "message": f"Recognition failed"
                })

            await asyncio.sleep(3)  # Delay to prevent rate-limiting

            if i % batch_fraction == 0:
                print(f"⏸️ Batch {i // batch_fraction} complete. Pausing briefly...\n")
                STATUS.update({
                    "recognized": None,
                    "not_recognized": None,
                    "sent_to_spotify": None,
                    "not_sent_to_spotify": None,
                    "completed": False,
                    "message": f"Batch {i // batch_fraction} complete. Pausing briefly..."
                })
                await asyncio.sleep(5)

        # Remove previous logs
        recognised_stmt = delete(RecognisedSongs).where(
            RecognisedSongs.spotify_user_id == current_user.spotify_user_id
        )

        db.session.execute(recognised_stmt)

        unrecognised_stmt = delete(UnrecognisedSongs).where(
            UnrecognisedSongs.spotify_user_id == current_user.spotify_user_id
        )

        db.session.execute(unrecognised_stmt)

        # Remove previous logged songs
        sent_recognised_stmt = delete(SentSpotifySongs).where(
            SentSpotifySongs.spotify_user_id == current_user.spotify_user_id
        )
        db.session.execute(sent_recognised_stmt)

        unsent_recognised_stmt = delete(UnsentSpotifySongs).where(
            UnsentSpotifySongs.spotify_user_id == current_user.spotify_user_id
        )
        db.session.execute(unsent_recognised_stmt)

        for rec in recognized:
            recognised_song = RecognisedSongs(
                track=rec,
                spotify_playlist_id=playlist_id,
                spotify_user_id=current_user.spotify_user_id
            )
            db.session.add(recognised_song)

        for fail in failed:
            unrecognised_song = UnrecognisedSongs(
                track=fail,
                spotify_playlist_id=playlist_id,
                spotify_user_id=current_user.spotify_user_id
            )
            db.session.add(unrecognised_song)
        db.session.commit()

        print("\n📦 Finished batch processing.")
        print(f"✅ Recognized: {len(recognized)}")
        print(f"❌ Failed: {len(failed)}")

        STATUS.update({
            "recognized": None,
            "not_recognized": None,
            "sent_to_spotify": None,
            "not_sent_to_spotify": None,
            "completed": False,
            "message": f"Finished batch processing.\nRecognized: {len(recognized)} \nFailed: {len(failed)}"
        })

    asyncio.run(batch_recognize(UPLOAD_FOLDER))

    tracks_dict = {}

    stmt = db.select(RecognisedSongs.track).where(
        RecognisedSongs.spotify_playlist_id == playlist_id
    )
    result = db.session.execute(stmt).scalars().all()

    for i, line in enumerate(result, 1):
        parts = line.strip().split("::")
        needed_tracks = [parts[1], parts[2]]  # get second and third items
        tracks_dict[f"Track {i}"] = needed_tracks

    # NOW LET US ADD TRACKS TO SPOTIFY

    access_token = get_valid_spotify_token(current_user)
    if not access_token:
        STATUS.update({
            "recognized": None,
            "not_recognized": None,
            "sent_to_spotify": None,
            "not_sent_to_spotify": None,
            "completed": False,
            "message": "Spotify access failed"
        })
        # yield {"type": "failed", "message": "No valid Spotify token"}
        return None  # User not logged in or no valid token
    sp = spotipy.Spotify(auth=access_token)

    song_uris = []
    index = 1
    # Search for each track on Spotify and collect URIs
    for track_key, value in tracks_dict.items():
        title = value[0]
        artist = value[1]
        try:
            query = f"track:{title} artist:{artist}"
            query2 = f"{title} {artist}"

            result = sp.search(q=query, type="track", limit=3)
            result2 = sp.search(q=query2, type="track", limit=3)

            if result["tracks"]["items"]:
                uri = result["tracks"]["items"][0]["uri"]
                song_uris.append(uri)
                print(f"🎵 Found and added: {title} by {artist}")
                log = f"{title} by {artist}"
                new_log = SentSpotifySongs(
                    track=log,
                    spotify_playlist_id=playlist_id,
                    spotify_user_id=current_user.spotify_user_id
                )
                db.session.add(new_log)
                # STATUS["sent_to_spotify"] = True
                # STATUS["message"] = f"🎵 Sent: {title} by {artist}"

                STATUS.update({
                    "recognized": None,
                    "not_recognized": None,
                    "sent_to_spotify": f"Sent: {title}"[:35],
                    "not_sent_to_spotify": None,
                    "completed": False,
                    "message": f"{title} by {artist} sent successfully"
                })
                # yield {"type": "sent", "message": f"🎵 Sent: {title} by {artist}"}

            elif result2["tracks"]["items"]:
                uri = result2["tracks"]["items"][0]["uri"]
                song_uris.append(uri)
                print(f"🎵 Found and added: {title} by {artist}")
                successful_comment = f"Found and added: {title} by {artist}"
                log = f"{title} by {artist}"
                new_log = SentSpotifySongs(
                    track=log,
                    spotify_playlist_id=playlist_id,
                    spotify_user_id=current_user.spotify_user_id
                )
                db.session.add(new_log)
                STATUS.update({
                    "recognized": None,
                    "not_recognized": None,
                    "sent_to_spotify": successful_comment[:35],
                    "not_sent_to_spotify": None,
                    "completed": False,
                    "message": f"{title} by {artist} sent successfully"
                })
            else:
                print(f"❌ No track found for: {title} by {artist}")
                # unsuccessful_comment = f"No track found for: {title} by {artist}"
                log = f"{title} by {artist}"
                new_log = UnsentSpotifySongs(
                    track=log,
                    spotify_playlist_id=playlist_id,
                    spotify_user_id=current_user.spotify_user_id
                )
                db.session.add(new_log)
                # STATUS["not_sent_to_spotify"] = True
                # STATUS["message"] = f"❌ Not found: {title} by {artist}"
                STATUS.update({
                    "recognized": None,
                    "not_recognized": None,
                    "sent_to_spotify": None,
                    "not_sent_to_spotify": f"Not found: {title} by {artist}"[:35],
                    "completed": False,
                    "message": f"{title} by {artist} not found, sending to playlist failed "
                })
                # yield {"type": "failed", "message": f"❌ Not found: {title} by {artist}"}
            db.session.commit()
        except Exception as e:
            print(f"🚨 Error processing '{title}' by '{artist}': {e}")
            STATUS.update({
                "recognized": None,
                "not_recognized": None,
                "sent_to_spotify": None,
                "not_sent_to_spotify": f"Error: {title} by {artist}"[:35],
                "completed": False,
                "message": f"Error processing '{title}' by '{artist}': {e}"
            })
            time.sleep(5)  # Give Spotify some breathing room before continuing
        time.sleep(0.3)  # Respect rate limits

        if len(song_uris) % 100 == 0:
            print(f"{len(song_uris)} song search complete. Wait briefly...")
            time.sleep(2)

    for i in range(0, len(song_uris), 50):
        batch = song_uris[i:i + 50]
        try:
            sp.playlist_add_items(playlist_id=playlist_id, items=batch)
            print(f"✅ Added batch {i // 50 + 1} of {len(batch)} songs to playlist.")
            STATUS.update({
                "recognized": None,
                "not_recognized": None,
                "sent_to_spotify": None,
                "not_sent_to_spotify": None,
                "completed": False,
                "message": f"Added batch {i // 50 + 1} of {len(batch)} songs to playlist."
            })
            # yield {"type": "sent", "message": f"✅ Added {len(song_uris[i:i + 50])} songs to Spotify"}
        except Exception as e:
            print(f"🚨 Failed to upload batch {i // 50 + 1}: {e}")
            STATUS.update({
                "recognized": None,
                "not_recognized": None,
                "sent_to_spotify": None,
                "not_sent_to_spotify": None,
                "completed": False,
                "message": f"Failed to upload batch {i // 50 + 1}: {e}"
            })
            # yield {"type": "failed", "message": f"🚨 Failed batch upload: {e}"}
            time.sleep(10)  # Wait before retrying or proceeding

    STATUS.update({
        "recognized": None,
        "not_recognized": None,
        "sent_to_spotify": None,
        "not_sent_to_spotify": None,
        "completed": True,
        "message": "Song processing complete! Click circle objects to view status"
    })

    delete_upload_folder()

    create_upload_folder() #creates a new upload folder
    return redirect(url_for('show_song_processing', playlist_id=playlist_id))


@app.route("/display-uploads")
def display_uploads():
    files = [f for f in os.listdir(UPLOAD_FOLDER) if f.endswith(AUDIO_EXTS)]

    # For modal playlist
    access_token = get_valid_spotify_token(current_user)
    if not access_token:
        return None  # User not logged in or no valid token
    sp = spotipy.Spotify(auth=access_token)

    playlist_list = get_user_playlists(current_user, sp, 1, "playlist", "small")
    return render_template("display_uploads.html", playlist_list=playlist_list, files=files)



if __name__ == '__main__':
    app.run(debug=True)

