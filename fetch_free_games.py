import os
import requests
import json
import firebase_admin
from firebase_admin import credentials, db, messaging

# Firebase + API Config
FCM_TOPIC = "/topics/free_games"
CHEAPSHARK_API = "https://www.cheapshark.com/api/1.0/deals?upperPrice=0"

# Hardcoded Store IDs you're interested in
STORE_ID_NAME_MAP = {
    "1": "Steam",
    "2": "GamersGate",
    "3": "GreenManGaming",
    "4": "Amazon",
    "5": "GameStop",
    "6": "Direct2Drive",
    "7": "GoG",
    "8": "Origin",
    "9": "Get Games",
    "10": "ShinyLoot",
    "11": "Humble Store",
    "12": "Desura",
    "13": "Uplay",
    "14": "IndieGameStand",
    "15": "Fanatical",
    "16": "Gamesrocket",
    "17": "Games Republic",
    "18": "SilaGames",
    "19": "Playfield",
    "20": "ImperialGames",
    "21": "WinGameStore",
    "22": "FunStockDigital",
    "23": "GameBillet",
    "24": "Voidu",
    "25": "Epic Games Store"
}

# Only keep games from these store IDs
ALLOWED_STORE_IDS = {"1", "7", "8", "13", "25"}  # Steam, GoG, Origin, Uplay, Epic Games Store


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


def fetch_free_games_from_api():
    try:
        response = requests.get(CHEAPSHARK_API)
        if response.status_code == 200:
            deals = response.json()
            free_games = {}
            for deal in deals:
                store_id = deal['storeID']
                if store_id in ALLOWED_STORE_IDS and float(deal['normalPrice']) > 0 and float(deal['salePrice']) == 0:
                    title = deal['title'].strip()
                    free_games[title] = {
                        'title': title,
                        'normalPrice': deal['normalPrice'],
                        'store': STORE_ID_NAME_MAP[store_id],
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
                existing_titles_map[value['title'].strip().lower()] = key  # Convert to lowercase

    # Also lowercase API titles for matching
    api_titles_lower_map = {title.strip().lower(): title for title in api_games_dict.keys()}
    api_titles_lower = set(api_titles_lower_map.keys())
    firebase_titles_lower = set(existing_titles_map.keys())

    # Titles to add
    new_titles_lower = api_titles_lower - firebase_titles_lower
    for lower_title in new_titles_lower:
        original_title = api_titles_lower_map[lower_title]
        game = api_games_dict[original_title]
        ref.push(game)
        send_fcm_notification(game)
        print(f"✅ Added: {game['title']} ({game['store']})")
        changes["added"] += 1

    # Titles to remove
    expired_titles_lower = firebase_titles_lower - api_titles_lower
    for lower_title in expired_titles_lower:
        key_to_delete = existing_titles_map[lower_title]
        ref.child(key_to_delete).delete()
        print(f"❌ Removed: {lower_title}")
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


def main():
    api_games = fetch_free_games_from_api()
    if api_games:
        sync_with_firebase(api_games)
    else:
        print("⚠ No valid free games found.")


if __name__ == "__main__":
    main()
