import os
import requests
import json
import firebase_admin
from firebase_admin import credentials, db, messaging
import string
import re

# Firebase + API Config
FCM_TOPIC = "/topics/free_games"



# Load Firebase credentials from GitHub Secrets
firebase_credentials_json = os.getenv("FIREBASE_CREDENTIALS_JSON")
DATABASE_URL = os.getenv("DATABASE_URL")

if firebase_credentials_json:
    cred_dict = json.loads(firebase_credentials_json)
    cred = credentials.Certificate(cred_dict)
    firebase_admin.initialize_app(cred, {
        'databaseURL': DATABASE_URL
    })
else:
    raise ValueError("Firebase credentials not found in environment variables.")

def normalize_title(title):
    """
    Normalize a game title for comparison:
    - Lowercase
    - Remove punctuation
    - Collapse multiple spaces
    """
    title = title.lower()
    title = re.sub(rf"[{re.escape(string.punctuation)}]", "", title)  # Remove punctuation
    title = re.sub(r"\s+", " ", title)  # Collapse multiple spaces
    return title.strip()


def fetch_free_games_from_api():
    GAMERPOWER_API = "https://www.gamerpower.com/api/filter?platform=epic-games-store.steam.gog.origin&type=game&sort-by=date"
    try:
        response = requests.get(GAMERPOWER_API)
        if response.status_code == 200:
            offers = response.json()
            free_games = {}
            for offer in offers:
                raw_title = offer['title'].strip()

                # ❌ Skip key giveaways
                if "Key Giveaway" in raw_title:
                    continue

                # Extract clean title
                clean_title = re.sub(r'\s*\(.*?\)', '', raw_title)
                clean_title = re.sub(r'\s*Giveaway', '', clean_title)
                clean_title = clean_title.strip()

                # Extract store name: either from brackets in title or platforms field
                store = "Unknown"
                match = re.search(r'\((.*?)\)', raw_title)
                if match:
                    store = match.group(1).strip()
                else:
                    platforms = offer.get('platforms', '')
                    if "Steam" in platforms:
                        store = "Steam"
                    elif "Epic Games" in platforms:
                        store = "Epic Games Store"
                    elif "GoG" in platforms:
                        store = "GoG"
                    elif "Origin" in platforms:
                        store = "Origin"

                if store not in {"Steam", "Epic Games Store", "GoG", "Origin"}:
                    continue

                worth = offer.get('worth', '$0.00').replace('$', '').strip()
                if not worth:
                    worth = "0.00"

                free_games[clean_title] = {
                    'title': clean_title,
                    'normalPrice': worth,
                    'store': store,
                }

            return free_games
        else:
            print(f"API error: {response.status_code}")
            return {}
    except Exception as e:
        print(f"Exception: {e}")
        return {}

def send_fcm_notification(game):
    message = messaging.Message(
        topic="free_games",
        notification=messaging.Notification(
            title="FREE GAME ALERT 🎮",
            body=f"{game['title']} is now FREE on {game['store']}!"
        ),
        data={
            "game_name": game['title'],
            "normal_price": game['normalPrice'],
            "store": game['store'],
            "click_action": "OPEN_GAME_PAGE"
        }
    )
    try:
        response = messaging.send(message)
        print(f"📣 Notification sent: {game['title']} (Message ID: {response})")
    except Exception as e:
        print(f"❌ Notification failed: {e}")


def main():
    api_games = fetch_free_games_from_api()
    if api_games:
        sync_with_firebase(api_games)
    else:
        print("⚠ No valid free games found.")


if __name__ == "__main__":
    main()
