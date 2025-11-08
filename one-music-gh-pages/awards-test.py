import requests
from bs4 import BeautifulSoup
import re
import json

def parse_track_artist(text):
    """
    Parse “Track Name” – Artist Name or Track Name - Artist Name
    Returns (track, artist) or (None, text)
    """
    match = re.match(r'[“"](.+?)[”"]\s*[–-]\s*(.+)', text)
    if match:
        return match.group(1).strip(), match.group(2).strip()
    return None, text.strip()

def grammy_scrapper(selected_date):
    now_date = "2025-10-05"
    now_position = "68"
    now_date_year = now_date.split('-')[0]
    selected_year = selected_date.split('-')[0]
    year_diff = int(selected_year) - int(now_date_year)
    selected_position = str(year_diff + int(now_position))

    # Determine ordinal suffix
    if selected_position.endswith("1") and not selected_position.endswith("11"):
        endposition = "st"
    elif selected_position.endswith("2") and not selected_position.endswith("12"):
        endposition = "nd"
    elif selected_position.endswith("3") and not selected_position.endswith("13"):
        endposition = "rd"
    else:
        endposition = "th"

    grammy_url = f"https://www.grammy.com/awards/{selected_position}{endposition}-annual-grammy-awards-{selected_year}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    response = requests.get(grammy_url, headers=headers)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    all_awards = []

    # Each category is inside a <section> tag with id like 628, 629, etc.
    for section in soup.find_all("section", id=True):
        category_title = section.find("h2")
        if not category_title:
            continue

        category_name = category_title.get_text(strip=True)
        if not category_name:
            continue

        # Stop scraping when we reach "Best Musical Theater and Beyond"
        if "BEST MUSICAL THEATER AND BEYOND" in category_name.upper():
            break

        # --- Winner ---
        winner_block = section.find("span", string=re.compile("winner", re.IGNORECASE))
        winner_info = []
        if winner_block:
            winner_div = winner_block.find_parent("div", class_=re.compile("flex", re.IGNORECASE))
            if winner_div:
                winner_text = winner_div.get_text(" ", strip=True)
                winner_track, winner_artist = parse_track_artist(winner_text)
                winner_info.append({
                    "winner_name": winner_artist,
                    "winner_track": winner_track
                })

        # --- Nominees ---
        nominee_info = []
        nominee_blocks = section.find_all("input", {"class": re.compile("nominees-input")})
        for nominee in nominee_blocks:
            parent_div = nominee.find_parent("div", class_=re.compile("flex|text-left"))
            if parent_div:
                nominee_text = parent_div.get_text(" ", strip=True)
                track, artist = parse_track_artist(nominee_text)
                nominee_info.append({
                    "nominee_name": artist,
                    "nominee_track": track
                })

        all_awards.append({
            "category": category_name,
            "winner": winner_info,
            "nominees": nominee_info
        })

    return all_awards

# Example test

data = grammy_scrapper("2020-10-05")
print(json.dumps(data, indent=2, ensure_ascii=False))
