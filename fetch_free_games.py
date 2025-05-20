import os
import requests
import json
from bs4 import BeautifulSoup
from datetime import datetime, timezone
import firebase_admin
from firebase_admin import credentials, db, messaging

# Firebase Config
FCM_TOPIC = "/topics/free_games"
FREE_GAMES_URL = "https://gg.deals/deals/?maxPrice=0&minDiscount=100&minRating=0&sort=title&store=4,5,10,38,54,57,109,1169&type=1,3"

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

def fetch_latest_games():
    response = requests.get(FREE_GAMES_URL)
    if response.status_code == 200:
        soup = BeautifulSoup(response.content, 'html.parser')
        game_elements = soup.find_all(class_='game-info-title-wrapper')

        games = []
        for game_el in game_elements:
            title = game_el.get_text(strip=True)

            wrapper = game_el.find_parent('div', class_='game-info-row')
            expiry_timestamp = None

            # Look for expiration only inside the correct tag
            if wrapper:
                expiry_container = wrapper.find('div', class_='time-tag tag')
                if expiry_container:
                    time_tag = expiry_container.find('time')
                    if time_tag and time_tag.has_attr('data-timestamp'):
                        expiry_timestamp = int(time_tag['data-timestamp'])

            games.append({
                'title': title,
                'expires_at': expiry_timestamp
            })

        return games
    return []


def compare_and_notify(games):
    ref = db.reference('games')
    last_chance_ref = db.reference('last_chance_sent')

    existing_games = ref.get()
    existing_titles = set(existing_games.values()) if existing_games else set()

    now_ts = int(datetime.now(timezone.utc).timestamp())
    new_titles = set()

    for game in games:
        title = game['title']
        expires_at = game['expires_at']

        # Handle new games
        if title not in existing_titles:
            ref.push(title)
           # send_fcm_notification(title)
            new_titles.add(title)
            print("Expires at {expires_at}")

        # Handle "last chance" alert
        if expires_at:
            hours_left = (expires_at - now_ts) / 3600
            if hours_left <= 48:
                already_notified = last_chance_ref.child(title).get()
                send_last_chance_notification(title, int(hours_left))

           

    if new_titles:
        print(f"✅ Added {len(new_titles)} new game(s) to Firebase.")
    else:
        print("ℹ️ No new games to update.")

def send_fcm_notification(game_name):
    message = messaging.Message(
        topic="free_games",
        notification=messaging.Notification(
            title="FREE GAME ALERT 🎮",
            body=f"{game_name} is FREE right now, grab it before the deal disappears!"
        ),
        data={
            "game_name": game_name,
            "click_action": "OPEN_GAME_PAGE"
        }
    )
    response = messaging.send(message)
    print(f"🚀 Notification sent: {game_name} (Message ID: {response})")

def send_last_chance_notification(game_name, hours_left):
    message = messaging.Message(
        topic="free_games",
        notification=messaging.Notification(
            title="⏰ Last Chance!",
            body=f"Only {int(hours_left)} hour(s) left to claim {game_name} for FREE!"
        ),
        data={
            "game_name": game_name,
            "click_action": "OPEN_GAME_PAGE",
            "alert_type": "last_chance"
        }
    )
    response = messaging.send(message)
    print(f"⚠️ Last chance notification sent: {game_name} (Message ID: {response})")

def main():
    games = fetch_latest_games()
    if games:
        compare_and_notify(games)
    else:
        print("No free games found.")

if __name__ == "__main__":
    main()
