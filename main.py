import os
import asyncio
import requests
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pyrogram import Client, filters
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

# --- CONFIG ---
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
TMDB_KEY = os.getenv("TMDB_KEY")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))

app = FastAPI()

# Enable CORS for your React Frontend (Vercel)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_methods=["*"],
    allow_headers=["*"],
)

# DB & TG Client
db_client = AsyncIOMotorClient(MONGO_URI)
db = db_client.movie_db
bot = Client("render_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- BOT LOGIC: AUTO-SCAN CHANNEL ---
@bot.on_message(filters.chat(CHANNEL_ID) & (filters.video | filters.document))
async def handle_new_movie(client, message):
    file = message.video or message.document
    raw_name = file.file_name
    
    # Clean name: "Movie.Name.2024.1080p.mp4" -> "Movie Name"
    clean_name = raw_name.split('.')[0].replace('_', ' ').replace('-', ' ')
    
    # Fetch TMDB Data
    tmdb_res = requests.get(
        f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_KEY}&query={clean_name}"
    ).json()

    if tmdb_res.get('results'):
        data = tmdb_res['results'][0]
        payload = {
            "title": data.get("title"),
            "rating": data.get("vote_average"),
            "poster": f"https://image.tmdb.org/t/p/w500{data.get('poster_path')}",
            "backdrop": f"https://image.tmdb.org/t/p/original{data.get('backdrop_path')}",
            "description": data.get("overview"),
            "file_id": file.file_id,
            "size": file.file_size
        }
        # Save to Mongo
        await db.movies.update_one({"title": payload["title"]}, {"$set": payload}, upsert=True)
        print(f"🚀 Synced: {payload['title']}")

# --- API ROUTES ---
@app.get("/")
def health_check():
    return {"status": "running", "bot": "active"}

@app.get("/movies")
async def get_all_movies():
    movies = []
    cursor = db.movies.find().sort("_id", -1)
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        movies.append(doc)
    return movies

# --- RUN BOT + SERVER TOGETHER ---
@app.on_event("startup")
async def start_up():
    asyncio.create_task(bot.start())

if __name__ == "__main__":
    import uvicorn
    # Render provides a PORT env variable automatically
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

