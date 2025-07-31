import os
import requests
import json
import firebase_admin
from firebase_admin import credentials, db, messaging
import string
import re

# Firebase + API Config
FCM_TOPIC = "/topics/free_games"

# Titles you always want to skip (normalized!)
BLOCKED_TITLES = [
 
]


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

                    # ✅ Normalize for blocking check
                normalized_clean_title = normalize_title(clean_title)

                # ❌ Skip if in blocked list
                if normalized_clean_title in BLOCKED_TITLES:
                    continue

                # Extract store name: either from brackets in title or platforms field
                store = "Unknown"
                match = re.search(r'\((.*?)\)', raw_title)
                if match:
                    store = match.group(1).strip()
                    if store == "Epic Games":
                        store = "Epic Games Store"

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



def sync_with_firebase(api_games_dict):
    ref = db.reference('games')
    existing_data = ref.get()
    existing_titles_map = {}
    changes = {"added": 0, "removed": 0}

    if existing_data:
        for key, value in existing_data.items():
            if isinstance(value, dict) and 'title' in value:
                normalized_existing_title = normalize_title(value['title'])
                existing_titles_map[normalized_existing_title] = {
                    "key": key,
                    "manual": value.get("manual", False),
                    "forceExpired": value.get("forceExpired", False)
                }

    api_titles_normalized_map = {normalize_title(title): title for title in api_games_dict.keys()}
    api_titles_normalized = set(api_titles_normalized_map.keys())
    firebase_titles_lower = set(existing_titles_map.keys())

    # Add new games
    new_titles_normalized = api_titles_normalized - firebase_titles_lower
    for normalized_title in new_titles_normalized:
        original_title = api_titles_normalized_map[normalized_title]
        game = api_games_dict[original_title]
        ref.push(game)
        send_fcm_notification(game)
        print(f"✅ Added: {game['title']} ({game['store']})")
        changes["added"] += 1

    # Remove expired or forced expired
    for normalized_title in firebase_titles_lower:
        entry = existing_titles_map[normalized_title]

        # If this title has forceExpired flag ➜ always delete it
        if entry["forceExpired"]:
            ref.child(entry["key"]).delete()
            print(f"❌ Force-expired removed: {normalized_title}")
            changes["removed"] += 1
            continue

        # If the title is not in API and not manual ➜ remove
        if normalized_title not in api_titles_normalized and not entry["manual"]:
            ref.child(entry["key"]).delete()
            print(f"❌ Removed: {normalized_title}")
            changes["removed"] += 1

    print(f"\n✔ Sync completed. Added: {changes['added']} | Removed: {changes['removed']}")

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

def fetch_secret_free_games():
    SECRET_API = "https://www.gamerpower.com/api/filter?platform=drm-free&type=game"
    try:
        response = requests.get(SECRET_API)
        if response.status_code == 200:
            offers = response.json()
            secret_games = {}

            for offer in offers:
                game_id = offer.get('id')
                if not game_id:
                    continue  # Skip if no ID, just in case

                end_date = offer.get('end_date', 'N/A').strip()
                open_url = offer.get('open_giveaway_url') or offer.get('open_giveaway') or ""

                secret_games[str(game_id)] = {
                    'id': game_id,
                    'endDate': end_date,
                    'openGiveawayUrl': open_url
                }

            return secret_games
        else:
            print(f"API error: {response.status_code}")
            return {}
    except Exception as e:
        print(f"Exception: {e}")
        return {}
    
def sync_secret_freebies(api_secret_games):
    ref = db.reference('secret_freebies')
    existing_data = ref.get()
    existing_ids = set()
    changes = {"added": 0, "removed": 0}

    if existing_data:
        for key, value in existing_data.items():
            if isinstance(value, dict) and 'id' in value:
                existing_ids.add(str(value['id']))

    api_ids = set(api_secret_games.keys())

    # Add new
    new_ids = api_ids - existing_ids
    for game_id in new_ids:
        game = api_secret_games[game_id]
        ref.push(game)
        print(f"✅ Secret Added: {game['id']}")
        changes["added"] += 1

    # Remove missing
    for key, value in existing_data.items():
        if isinstance(value, dict) and 'id' in value:
            if str(value['id']) not in api_ids:
                ref.child(key).delete()
                print(f"❌ Secret Removed: {value['id']}")
                changes["removed"] += 1

    print(f"\n✔ Secret Sync completed. Added: {changes['added']} | Removed: {changes['removed']}")



def main():
    api_games = fetch_free_games_from_api()
    if api_games:
        sync_with_firebase(api_games)
    else:
        print("⚠ No valid free games found.")

    api_secret_games = fetch_secret_free_games()
    if api_secret_games:
        sync_secret_freebies(api_secret_games)
    else:
        print("⚠ No secret freebies found.")

if __name__ == "__main__":
    main()
