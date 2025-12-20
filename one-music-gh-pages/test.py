
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
        yield {"type": "failed", "message": "No valid Spotify token"}
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
                yield {"type": "sent", "message": f"🎵 Sent: {title} by {artist}"}

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
                yield {"type": "failed", "message": f"❌ Not found: {title} by {artist}"}
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
            yield {"type": "sent", "message": f"✅ Added {len(song_uris[i:i + 50])} songs to Spotify"}
        except Exception as e:
            print(f"🚨 Failed to upload batch {i // 50 + 1}: {e}")
            yield {"type": "failed", "message": f"🚨 Failed batch upload: {e}"}
            time.sleep(10)  # Wait before retrying or proceeding
