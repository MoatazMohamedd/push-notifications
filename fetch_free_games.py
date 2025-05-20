import os
import requests
import json
from bs4 import BeautifulSoup
import firebase_admin
from firebase_admin import credentials, db, messaging

# Firebase Config
FCM_TOPIC = "/topics/free_games"
FREE_GAMES_URL = "https://gg.deals/deals/?maxPrice=0&minDiscount=100&minRating=0&sort=title&store=4,5,10,38,54,57,109,1169&type=1,3"

# Load Firebase credentials from GitHub Secrets
firebase_credentials_json = os.getenv("FIREBASE_CREDENTIALS_JSON")
DATABASE_URL = os.getenv("DATABASE_URL")

if firebase_credentials_json:
    cred_dict = json.loads(firebase_credentials_json)
    cred = credentials.Certificate(cred_dict)
    firebase_admin.initialize_app(cred, {
        'databaseURL': DATABASE_URL  # Replace with your database URL
    })
else:
    raise ValueError("Firebase credentials not found in environment variables.")

def fetch_latest_game():
    response = requests.get(FREE_GAMES_URL)
    if response.status_code == 200:
        soup = BeautifulSoup(response.content, 'html.parser')
        free_games = soup.find_all(class_='game-info-title-wrapper')
        game_titles = [game.get_text(strip=True) for game in free_games]
        return game_titles if game_titles else []
    return []

def compare_free_games(game_titles):
    ref = db.reference('games')

    existing_games = ref.get()
    existing_games_set = set(existing_games.values()) if existing_games else set()
    new_games_set = set(game_titles)

    new_games_to_push = new_games_set - existing_games_set

    if new_games_to_push:
        for title in new_games_to_push:
            ref.push(title)
            send_fcm_notification(title)
        print(f"Added {len(new_games_to_push)} new game(s) to Firebase.")
    else:
        print("No new games to update.")

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
    print(f"✅ Notification sent: {game_name} (Message ID: {response})")

def main():
    game_titles = fetch_latest_game()
    if game_titles:
        compare_free_games(game_titles)
    else:
        print("No new free games found.")

if __name__ == "__main__":
    main()
