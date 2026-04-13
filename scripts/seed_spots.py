from datetime import datetime, timezone
from app.core.firestore import get_db
from dotenv import load_dotenv
load_dotenv()

db = get_db()

spots = [

    # ================= STUDY SPOTS =================
    {
        "name": "West Hall",
        "description": "Study area",
        "category": "study",
        "location": "Main Campus",
        "createdBy": "system",
        "rating": 0,
        "reviewCount": 0
    },
    {
        "name": "Saab Medical Library",
        "description": "Quiet study space",
        "category": "study",
        "location": "Main Campus",
        "createdBy": "system",
        "rating": 0,
        "reviewCount": 0
    },
    {
        "name": "BDH",
        "description": "Study building",
        "category": "study",
        "location": "Main Campus",
        "createdBy": "system",
        "rating": 0,
        "reviewCount": 0
    },
    {
        "name": "OSB Breakout Rooms",
        "description": "Group study rooms",
        "category": "study",
        "location": "Main Campus",
        "createdBy": "system",
        "rating": 0,
        "reviewCount": 0
    },
    {
        "name": "OSB Lounge",
        "description": "Casual study space",
        "category": "study",
        "location": "Main Campus",
        "createdBy": "system",
        "rating": 0,
        "reviewCount": 0
    },

    # ================= FOOD SPOTS =================
    {
        "name": "Main Cafeteria",
        "description": "Upper campus dining",
        "category": "food",
        "location": "Upper Campus",
        "createdBy": "system",
        "rating": 0,
        "reviewCount": 0
    },
    {
        "name": "OSB Cafeteria",
        "description": "Lower campus dining",
        "category": "food",
        "location": "Lower Campus",
        "createdBy": "system",
        "rating": 0,
        "reviewCount": 0
    },
    {
        "name": "Sage and Savy",
        "description": "Casual food spot",
        "category": "food",
        "location": "Lower Campus",
        "createdBy": "system",
        "rating": 0,
        "reviewCount": 0
    },
    {
        "name": "Brew Coffee by Najjar",
        "description": "Coffee spot",
        "category": "food",
        "location": "Upper Campus",
        "createdBy": "system",
        "rating": 0,
        "reviewCount": 0
    },
    {
        "name": "Spill by Najjar",
        "description": "Coffee spot",
        "category": "food",
        "location": "Lower Campus",
        "createdBy": "system",
        "rating": 0,
        "reviewCount": 0
    },
    {
        "name": "BLCK Coffee",
        "description": "Coffee shop",
        "category": "food",
        "location": "Main Campus",
        "createdBy": "system",
        "rating": 0,
        "reviewCount": 0
    },

    # Bliss Street spots
]

# Add Bliss street places dynamically
bliss_places = [
    "Malak Al Tawook", "Bakerloo", "Eatvite", "Paul Cafe", "Bartartine",
    "Roadster", "Aarouset Labneh", "Cosmic Osaj", "Pinkberry", "Mailos",
    "Chicken Way", "KFC", "Dominos", "Cheese On Top", "McDonalds",
    "Food District", "Dunkin Donuts", "Boneless 28", "Universal",
    "Makdisi", "Faycal"
]

for place in bliss_places:
    spots.append({
        "name": place,
        "description": "Bliss street food spot",
        "category": "food",
        "location": "Bliss Street",
        "createdBy": "system",
        "rating": 0,
        "reviewCount": 0
    })

# Insert into Firestore
for spot in spots:
    db.collection("spots").add({
        **spot,
        "createdAt": datetime.now(timezone.utc)
    })

print("Spots seeded successfully.")