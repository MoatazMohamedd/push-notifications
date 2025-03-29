import os
import requests
import json
from bs4 import BeautifulSoup
import firebase_admin
from firebase_admin import credentials, db

# Firebase Config
FCM_SERVER_KEY = os.getenv("FCM_SERVER_KEY")  # Load from GitHub Secrets
FCM_TOPIC = "/topics/free_games"
FREE_GAMES_URL = "https://gg.deals/deals/?dealsExpiryDate=within2Weeks&maxPrice=0&minRating=0&sort=title&store=4,5,10,38,57&type=1,3"

# Save Firebase credentials from environment variable
firebase_json = os.getenv("FIREBASE_CREDENTIALS_JSON")
if firebase_json:
    with open("firebase_credentials.json", "w") as f:
        f.write(firebase_json)

# Initialize Firebase
if not firebase_admin._apps:
    cred = credentials.Certificate("firebase_credentials.json")
    firebase_admin.initialize_app(cred, {
        'databaseURL': 'https://testing-push-notificatio-3a0b4-default-rtdb.europe-west1.firebasedatabase.app'
    })

def fetch_latest_game():
    response = requests.get(FREE_GAMES_URL)
    if response.status_code == 200:
        soup = BeautifulSoup(response.content, 'html.parser')
        free_games = soup.find_all(class_='game-info-title-wrapper')
        game_titles = [game.get_text(strip=True) for game in free_games]
        return game_titles if game_titles else []
    return []

def insert_game_titles_to_firebase(game_titles):
    ref = db.reference('games')
    for title in game_titles:
        ref.push(title)
    print("Game titles inserted into Firebase Realtime Database.")

def main():
    game_titles = fetch_latest_game()
    if game_titles:
        insert_game_titles_to_firebase(game_titles)
    else:
        print("No new free games found.")

if __name__ == "__main__":
    main()
