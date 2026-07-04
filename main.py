from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from yandex_music import Client
import yt_dlp

app = FastAPI()

# Разрешаем запросы с любых сайтов (CORS), чтобы гитхаб мог стучаться к бэкенду
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Простой кэш клиентов, чтобы не авторизоваться в Яндексе с нуля при каждом клике
clients_cache = {}

def get_ym_client(token: str):
    if not token:
        raise HTTPException(status_code=401, detail="Токен не передан")
    if token not in clients_cache:
        try:
            clients_cache[token] = Client(token).init()
        except Exception:
            raise HTTPException(status_code=401, detail="Неверный токен")
    return clients_cache[token]

def get_youtube_audio_url(search_query: str) -> str:
    ydl_opts = {'format': 'bestaudio/best', 'noplaylist': True, 'quiet': True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(f"ytsearch1:{search_query} official audio", download=False)
            if 'entries' in info and len(info['entries']) > 0:
                return info['entries'][0]['url']
        except Exception:
            pass
    return ""

@app.get("/api/playlists")
def get_playlists(x_yandex_token: str = Header(None)):
    client = get_ym_client(x_yandex_token)
    try:
        result = [{"id": "liked", "title": "🤍 Мне нравится"}]
        playlists = client.users_playlists_list()
        for p in playlists:
            result.append({"id": str(p.kind), "title": p.title})
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/playlist/{playlist_id}")
def get_playlist_tracks(playlist_id: str, x_yandex_token: str = Header(None)):
    client = get_ym_client(x_yandex_token)
    try:
        if playlist_id == "liked":
            raw_tracks = client.users_likes_tracks().fetch_tracks()[:100]
        else:
            pl = client.users_playlists(int(playlist_id))
            raw_tracks = pl.fetch_tracks()[:100]

        playlist_data = []
        for t in raw_tracks:
            track_obj = getattr(t, 'track', t)
            if not track_obj or not track_obj.id:
                continue
            playlist_data.append({
                "id": track_obj.id,
                "title": track_obj.title,
                "artist": ", ".join([a.name for a in track_obj.artists]) if track_obj.artists else "Неизвестен",
                "available": track_obj.available
            })
        return playlist_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/stream/{track_id}")
def get_stream_url(track_id: str, x_yandex_token: str = Header(None)):
    client = get_ym_client(x_yandex_token)
    track = client.tracks([track_id])[0]
    
    if track.available:
        info = track.get_download_info()
        if info:
            return {"url": info[0].get_direct_link(), "source": "yandex"}
    
    search_query = f"{track.artists[0].name} - {track.title}"
    yt_url = get_youtube_audio_url(search_query)
    
    if yt_url:
        return {"url": yt_url, "source": "youtube"}
    
    raise HTTPException(status_code=404, detail="Трек не найден нигде")

@app.get("/")
def serve_frontend():
    with open("index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())