
import requests
import re
from bs4 import BeautifulSoup
from pprint import pprint
import html

ad_url="https://audiomack.com/top/songs"

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

def audio_mack_scrape(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }

    response = requests.get(url, headers=headers)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    song_blocks = soup.find_all("div", class_="ChartsItem-content")
    pprint(song_blocks)
    songs = []

    for block in song_blocks:
        data_div = block.find("div", class_="ChartsItem-data")

        if not data_div:
            continue

        # Artist and song title (as before)
        artist_tag = data_div.find("h2", class_="ChartsItem-artist")
        title_tag = data_div.find("h2", class_="ChartsItem-title")

        artist = artist_tag.get_text(strip=True) if artist_tag else "Unknown Artist"
        title = title_tag.get_text(strip=True) if title_tag else "Unknown Title"


        songs.append({
            "artist": artist,
            "title": title,
            "main_artist": extract_main_artist(artist)  # new field added
        })

    # Print results
    for idx, s in enumerate(songs, start=1):
        print(f"{idx}. {s['main_artist']} — {s['title']}  (Full Artist: {s['artist']})")


def billboard_scraper(endpoint, selected_date):
    URL = f"https://www.billboard.com/charts/{endpoint}/{selected_date}"
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

    return results

billboard_scraper("billboard-argentina-hot-100", "2025-01-12")


STATUS = {
    "recognized": False,
    "not_recognized": False,
    "sent_to_spotify": False,
    "not_sent_to_spotify": False,
    "message": "Idle"
}

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
    shazam = Shazam()
    files = [f for f in os.listdir(folder_path) if f.endswith(AUDIO_EXTS)]

    # print(f"🎧 Found {len(files)} audio files.")
    recognized = []
    failed = []

    song_fraction = len(files)  # This is needed incase we want to limit the songs that can be uploaded
    batch_fraction = 10

    for i, file in enumerate(files, 1):
        full_path = os.path.join(folder_path, file)
        print(f"\n🔍 [{i}/{song_fraction}] Recognizing: {file}")
        STATUS.update({
            "recognized": False,
            "not_recognized": False,
            "message": f"Recognizing {file}"
        })

        title, artist, good_comment, bad_comment = await recognize_song(full_path, shazam)
        if good_comment:
            result_line = f"{file}::{title}::{artist}"
            print(f"✅ {result_line}")
            recognized.append(result_line)
            STATUS["recognized"] = True
            STATUS["message"] = f"{good_comment}"
        elif bad_comment: #be careful here you might just need else block
            print(f"❌ Could not recognize: {file}")
            failed.append(file)
            STATUS["not_recognized"] = True
            STATUS["message"] = f"Failed to recognize {file}"

        await asyncio.sleep(3)  # Delay to prevent rate-limiting

        if i % batch_fraction == 0:
            print(f"⏸️ Batch {i // batch_fraction} complete. Pausing briefly...\n")
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
        "sent_to_spotify": False,
        "not_sent_to_spotify": False,
        "message": f"Spotify access failed"
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
            STATUS["sent_to_spotify"] = True
            STATUS["message"] = f"🎵 Sent: {title} by {artist}"
            # yield {"type": "sent", "message": f"🎵 Sent: {title} by {artist}"}

        elif result2["tracks"]["items"]:
            uri = result2["tracks"]["items"][0]["uri"]
            song_uris.append(uri)
            print(f"🎵 Found and added: {title} by {artist}")
            successful_comment = f"🎵 Found and added: {title} by {artist}"
            log = f"{title} by {artist}"
            new_log = SentSpotifySongs(
                track=log,
                spotify_playlist_id=playlist_id,
                spotify_user_id=current_user.spotify_user_id
            )
            db.session.add(new_log)
            STATUS["sent_to_spotify"] = True
            STATUS["message"] = f"🎵 Sent: {title} by {artist}"
        else:
            print(f"❌ No track found for: {title} by {artist}")
            unsuccessful_comment = f"❌ No track found for: {title} by {artist}"
            log = f"{title} by {artist}"
            new_log = UnsentSpotifySongs(
                track=log,
                spotify_playlist_id=playlist_id,
                spotify_user_id=current_user.spotify_user_id
            )
            db.session.add(new_log)
            STATUS["not_sent_to_spotify"] = True
            STATUS["message"] = f"❌ Not found: {title} by {artist}"
            # yield {"type": "failed", "message": f"❌ Not found: {title} by {artist}"}
        db.session.commit()
    except Exception as e:
        print(f"🚨 Error processing '{title}' by '{artist}': {e}")
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
        # yield {"type": "sent", "message": f"✅ Added {len(song_uris[i:i + 50])} songs to Spotify"}
    except Exception as e:
        print(f"🚨 Failed to upload batch {i // 50 + 1}: {e}")
        # yield {"type": "failed", "message": f"🚨 Failed batch upload: {e}"}
        time.sleep(10)  # Wait before retrying or proceeding
STATUS["message"] = "Completed"



import os
import re
import time
import asyncio
from flask import Flask, jsonify
from dotenv import load_dotenv

import spotipy
from spotipy.oauth2 import SpotifyOAuth
from shazamio import Shazam

# --------------------------------------------------
# ENV + CONFIG
# --------------------------------------------------

load_dotenv()

MUSIC_FOLDER = "music"
SUCCESS_LOG = "recognized_songs.txt"
FAILED_LOG = "failed_songs.txt"
AUDIO_EXTS = (".mp3", ".wav", ".m4a")

# --------------------------------------------------
# STATUS (frontend reads this)
# --------------------------------------------------

STATUS = {
    "recognized": False,
    "not_recognized": False,
    "sent_to_spotify": False,
    "not_sent_to_spotify": False,
    "message": "Idle"
}

# --------------------------------------------------
# FLASK APP
# --------------------------------------------------

app = Flask(__name__)

@app.route("/status")
def get_status():
    return jsonify(STATUS)

# --------------------------------------------------
# SHAZAM LOGIC
# --------------------------------------------------

async def recognize_song(file_path, shazam):
    try:
        result = await shazam.recognize_song(file_path)
        track = result.get("track", {})
        title = track.get("title")
        artist = track.get("subtitle")
        return title, artist
    except Exception:
        return None, None


async def batch_recognize(folder_path):
    shazam = Shazam()
    files = [f for f in os.listdir(folder_path) if f.endswith(AUDIO_EXTS)]

    recognized = []
    failed = []

    for file in files:
        full_path = os.path.join(folder_path, file)

        STATUS.update({
            "recognized": False,
            "not_recognized": False,
            "message": f"Recognizing {file}"
        })

        title, artist = await recognize_song(full_path, shazam)

        if title and artist:
            STATUS["recognized"] = True
            STATUS["message"] = f"Recognized {title} - {artist}"
            recognized.append(f"{file}::{title}::{artist}")
        else:
            STATUS["not_recognized"] = True
            STATUS["message"] = f"Failed to recognize {file}"
            failed.append(file)

        await asyncio.sleep(2)

    with open(SUCCESS_LOG, "w", encoding="utf-8") as f:
        f.write("\n".join(recognized))

    with open(FAILED_LOG, "w", encoding="utf-8") as f:
        f.write("\n".join(failed))

# --------------------------------------------------
# SPOTIFY LOGIC
# --------------------------------------------------

def clean_title(text):
    return re.sub(r"\(feat.*?\)", "", text, flags=re.I).strip()


def send_to_spotify():
    client_id = os.getenv("SPOTIPY_CLIENT_ID")
    client_secret = os.getenv("SPOTIPY_CLIENT_SECRET")
    redirect_uri = os.getenv("SPOTIPY_REDIRECT_URI")

    sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scope="playlist-modify-private"
    ))

    user_id = sp.me()["id"]
    playlist = sp.user_playlist_create(
        user=user_id,
        name="MY LOCAL SONGS",
        description="Local songs recognized with Shazam"
    )

    playlist_id = playlist["id"]
    song_uris = []

    with open(SUCCESS_LOG, "r", encoding="utf-8") as f:
        for line in f:
            _, title, artist = line.strip().split("::")

            title = clean_title(title)

            STATUS.update({
                "sent_to_spotify": False,
                "not_sent_to_spotify": False,
                "message": f"Searching Spotify for {title}"
            })

            result = sp.search(q=f"{title} {artist}", type="track", limit=1)

            if result["tracks"]["items"]:
                uri = result["tracks"]["items"][0]["uri"]
                song_uris.append(uri)

                STATUS["sent_to_spotify"] = True
                STATUS["message"] = f"Added {title} to Spotify"
            else:
                STATUS["not_sent_to_spotify"] = True
                STATUS["message"] = f"Spotify failed for {title}"

            time.sleep(0.4)

    for i in range(0, len(song_uris), 50):
        sp.playlist_add_items(playlist_id, song_uris[i:i+50])
        time.sleep(1)

# --------------------------------------------------
# BACKGROUND RUNNER
# --------------------------------------------------

def run_pipeline():
    asyncio.run(batch_recognize(MUSIC_FOLDER))
    send_to_spotify()
    STATUS["message"] = "Completed"

# --------------------------------------------------
# ENTRY POINT
# --------------------------------------------------

if __name__ == "__main__":
    from threading import Thread

    Thread(target=run_pipeline, daemon=True).start()
    app.run(debug=True)


# THE FORMER CODE FOR SONG REGOGNITION PROCESSING

def get_recognised_tracks(db, playlist_id):
    tracks_dict = {}

    stmt = db.select(RecognisedSongs.track).where(
        RecognisedSongs.spotify_playlist_id == playlist_id
    )
    result = db.session.execute(stmt).scalars().all()

    for i, line in enumerate(result, 1):
        parts = line.strip().split("::")
        tracks_dict[f"Track {i}"] = [parts[1], parts[2]]

    return tracks_dict

def get_spotify_client(current_user):
    access_token = get_valid_spotify_token(current_user)
    if not access_token:
        return None
    return spotipy.Spotify(auth=access_token)

def search_tracks_and_collect_uris(
    sp, tracks_dict, db, playlist_id, current_user
):
    song_uris = []

    for value in tracks_dict.values():
        title, artist = value

        try:
            query = f"track:{title} artist:{artist}"
            query2 = f"{title} {artist}"

            result = sp.search(q=query, type="track", limit=3)
            result2 = sp.search(q=query2, type="track", limit=3)

            if result["tracks"]["items"]:
                uri = result["tracks"]["items"][0]["uri"]
                song_uris.append(uri)

                db.session.add(
                    SentSpotifySongs(
                        track=f"{title} by {artist}",
                        spotify_playlist_id=playlist_id,
                        spotify_user_id=current_user.spotify_user_id
                    )
                )

                yield {"type": "sent", "message": f"🎵 Sent: {title} by {artist}"}

            elif result2["tracks"]["items"]:
                uri = result2["tracks"]["items"][0]["uri"]
                song_uris.append(uri)

                db.session.add(
                    SentSpotifySongs(
                        track=f"{title} by {artist}",
                        spotify_playlist_id=playlist_id,
                        spotify_user_id=current_user.spotify_user_id
                    )
                )

            else:
                db.session.add(
                    UnsentSpotifySongs(
                        track=f"{title} by {artist}",
                        spotify_playlist_id=playlist_id,
                        spotify_user_id=current_user.spotify_user_id
                    )
                )

                yield {"type": "failed", "message": f"❌ Not found: {title} by {artist}"}

            db.session.commit()

        except Exception as e:
            print(f"🚨 Error processing '{title}' by '{artist}': {e}")
            time.sleep(5)

        time.sleep(0.3)

        if len(song_uris) % 100 == 0:
            time.sleep(2)

    return song_uris


def upload_tracks_to_playlist(sp, playlist_id, song_uris):
    for i in range(0, len(song_uris), 50):
        batch = song_uris[i:i + 50]
        try:
            sp.playlist_add_items(playlist_id=playlist_id, items=batch)
            yield {
                "type": "sent",
                "message": f"✅ Added {len(batch)} songs to Spotify"
            }
            print(f"✅ Added {len(batch)} songs to Spotify")
        except Exception as e:
            yield {
                "type": "failed",
                "message": f"🚨 Failed batch upload: {e}"
            }
            print(f"🚨 Failed batch upload: {e}")
            time.sleep(10)

# THE ABOVE ARE OUTSIDE THE SONG_PROCESSING ROUTE,
# WHILE THE BELOW ARE INSIDE

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
        shazam = Shazam()
        files = [f for f in os.listdir(folder_path) if f.endswith(AUDIO_EXTS)]

        # print(f"🎧 Found {len(files)} audio files.")
        recognized = []
        failed = []

        song_fraction = len(files) # This is needed incase we want to limit the songs that can be uploaded
        batch_fraction = 10

        for i, file in enumerate(files, 1):
            full_path = os.path.join(folder_path, file)
            print(f"\n🔍 [{i}/{song_fraction}] Recognizing: {file}")

            title, artist, good_comment, bad_comment = await recognize_song(full_path, shazam)
            if good_comment:
                result_line = f"{file}::{title}::{artist}"
                print(f"✅ {result_line}")
                recognized.append(result_line)
                yield {"type": "recognised", "message": good_comment}
            else:
                print(f"❌ Could not recognize: {file}")
                failed.append(file)
                yield {"type": "not_recognised", "message": bad_comment}

            await asyncio.sleep(3)  # Delay to prevent rate-limiting

            if i % batch_fraction == 0:
                print(f"⏸️ Batch {i // batch_fraction} complete. Pausing briefly...\n")
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

        yield {"type": "recognised", "message": f"Finished batch. ✅ {len(recognized)} recognised"}
        yield {"type": "not_recognised", "message": f"❌ {len(failed)} failed"}

    def generate():
        loop = asyncio.new_event_loop()

        async def run_and_collect():
            async for event in batch_recognize(UPLOAD_FOLDER):
                yield event

        async_gen = run_and_collect()

        try:
            while True:
                try:
                    # Ask async generator for next item and wait for it
                    event = loop.run_until_complete(async_gen.__anext__())

                    # Send to client immediately
                    yield f"data: {event}\n\n"

                except StopAsyncIteration:
                    # Async generator finished
                    break

        except GeneratorExit:
            # Client disconnected
            pass

        finally:
            loop.close()

        tracks_dict = get_recognised_tracks(db, playlist_id)
        sp = get_spotify_client(current_user)
        gen = search_tracks_and_collect_uris(
            sp, tracks_dict, db, playlist_id, current_user
        )

        try:
            while True:
                message = next(gen)
                yield message  # stream progress to client
        except StopIteration as e:
            song_uris = e.value  # ← THIS is the returned list

        upload_gen = upload_tracks_to_playlist(sp, playlist_id, song_uris)
        for message in upload_gen:
            yield message

    def sse_wrapper(generator):
        for event in generator:
            # Ensure event is always a dict
            if isinstance(event, str):
                # maybe it was already JSON encoded → decode back
                try:
                    event = json.loads(event)
                except Exception:
                    # fallback: wrap as message
                    event = {"type": "message", "message": event}

            # Now safely yield SSE
            yield f"event: {event.get('type', 'message')}\n" \
                  f"data: {json.dumps({'message': event.get('message', '')})}\n\n"

            # ✅ after the generator is exhausted, send a final "done"
        yield "event: done\ndata: {\"message\": \"🎉 All processing complete\"}\n\n"


        # if os.path.exists(UPLOAD_FOLDER):
        #     shutil.rmtree(UPLOAD_FOLDER)
        #     print("Folder deleted successfully!")
        # else:
        #     print("Folder does not exist.")

        return redirect(url_for('show_song_processing', playlist_id=playlist_id))
        # stop execution here without freezing the rest of the program
        # threading.Event().wait() # This will help stop the looping for now till we figure something out
    return Response(stream_with_context(sse_wrapper(generate())), mimetype="text/event-stream")



