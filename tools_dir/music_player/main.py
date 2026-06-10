import os
import json
import random
import re
from difflib import SequenceMatcher

from mutagen import File as MutagenFile
import time
import threading
import pygame

def set_status(s):
    pass
def clear_status():
    pass

MUSIC_PATH = r"C:\Users\ASUS\Music\Agent Areon_musics"
CIRCLE=True
class MusicPlayer:
    def __init__(self, resolver=None):
        self.resolver = resolver
        self._stop_event = threading.Event()
        self._thread = None
        self._lock = threading.Lock()
        # pygame.mixer.init()

    def _normalize_tracks(self, playlist):
        tracks = playlist.get("tracks", []) if isinstance(playlist, dict) else playlist
        resolved = []
        for item in tracks:
            if self.resolver is not None:
                try:
                    path = self.resolver(item)
                except Exception as e:
                    print(f"Resolver failed for {item}: {e}")
                    continue
            else:
                path = os.path.join(MUSIC_PATH, str(item))
            resolved.append(os.path.normpath(str(path)))
        return resolved

    def _start_worker(self, tracks,loop=True):
       
        self.stop()  # Stop previous thread execution
        
        with self._lock:
            self._stop_event = threading.Event()
            current_stop_event = self._stop_event 

            def worker(stop_signal):
                f=1
                while (f or loop) and not stop_signal.is_set():
                    f=0
                    # CRITICAL FIX: Force the mixer to initialize inside THIS background thread
                    try:
                        pygame.mixer.quit()  # Discard old main-thread hooks
                        pygame.mixer.init()  # Bind hardware context to this worker thread
                    except Exception as e:
                        print(f"Failed to initialize mixer in background thread: {e}")
                        return

                    for path in tracks:
                        if stop_signal.is_set():
                            break

                        if not os.path.exists(path):
                            print(f"File not found: {path}")
                            continue

                        try:

                            pygame.mixer.music.load(path)
                            pygame.mixer.music.play()
                            
                            # Give the thread a brief window to catch up
                            waves="▂▃▅▆▇▆▅▃▂"
                            time.sleep(0.2)
                            song_title = extract_metadata(path)["title"]
                            prev0='▂'
                            prev1='▂'
                            
                            w_n=0
                            while pygame.mixer.music.get_busy():
                                if stop_signal.is_set():
                                    pygame.mixer.music.stop()
                                    return
                                set_status(f"{prev1}{prev0}{waves[w_n]} {song_title}")
                                prev0=prev1
                                prev1=waves[w_n]
                                time.sleep(0.13)
                                w_n+=1
                                if w_n>=len(waves):
                                    w_n=0
                            clear_status()
                        except Exception as e:
                            print(f"Failed to play {path}: {e}")

            # Remove pygame.mixer.init() from __init__ if you want, 
            # but definitely keep it here.
            self._thread = threading.Thread(target=worker, args=(current_stop_event,), daemon=True)
            self._thread.start()

    def play_music(self, path,loop):
        """Plays one music file."""
        self._start_worker([path],loop)

    def stop(self):
        """Stops playback immediately."""
        # Signal the event
        self._stop_event.set()
        try:
            pygame.mixer.music.stop()
        except Exception:
            pass

        # Safely join from external threads
        if self._thread and self._thread.is_alive() and threading.current_thread() != self._thread:
            self._thread.join(timeout=1)
        clear_status()
    def play_playlist(self, playlist):
        """Plays a playlist sequentially."""
        tracks = self._normalize_tracks(playlist)
        if not tracks:
            print("Playlist is empty.")
            return

        self._start_worker(tracks)


CONFIG_FILE = "config.json"

PLAYLISTS_FILE = "playlists.json"
PLAYLIST_EXPORT_DIR = "playlist_exports"

PREFIXES = ["mp3", "ogg", "mp4", "wav", "flac", "m4a", "aac", "wma"]

MAX_SEARCH_RESULTS = 5
PLAYLIST_SEARCH_ADD_COUNT = 3

music_list = {}   # song_id -> metadata dict
music_index = []  # ordered list of song_ids
playlists = {}    # normalized playlist name -> playlist dict

music_player=MusicPlayer()

def normalize_text(value):
    value = "" if value is None else str(value)
    value = value.lower().strip()
    value = re.sub(r"[_\-]+", " ", value)
    value = re.sub(r"[^a-z0-9\s]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def normalize_ext_list(ext_list):
    cleaned = []
    for ext in ext_list or []:
        ext = str(ext).lower().strip().lstrip(".")
        if ext:
            cleaned.append(ext)
    return cleaned


def sanitize_filename(value):
    value = str(value).strip()
    value = re.sub(r'[<>:"/\\|?*]+', "_", value)
    value = re.sub(r"\s+", "_", value)
    return value or "playlist"


def playlist_key(name):
    return normalize_text(name)


def first_non_empty(*values, default=""):
    for value in values:
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            for item in value:
                text = str(item).strip()
                if text:
                    return text
            continue
        text = str(value).strip()
        if text:
            return text
    return default


def similarity_score(a, b):
    a = normalize_text(a)
    b = normalize_text(b)
    if not a or not b:
        return 0.0

    ratio = SequenceMatcher(None, a, b).ratio()

    a_tokens = set(a.split())
    b_tokens = set(b.split())
    if a_tokens and b_tokens:
        token_overlap = len(a_tokens & b_tokens) / len(a_tokens | b_tokens)
    else:
        token_overlap = 0.0

    return (0.7 * ratio) + (0.3 * token_overlap)


def save_playlists():
    with open(PLAYLISTS_FILE, "w", encoding="utf-8") as fp:
        json.dump(playlists, fp, ensure_ascii=False, indent=2)


def load_playlists():
    global playlists
    try:
        with open(PLAYLISTS_FILE, "r", encoding="utf-8") as fp:
            playlists = json.load(fp)
        if not isinstance(playlists, dict):
            playlists = {}
    except Exception:
        playlists = {}
        with open(PLAYLISTS_FILE, "w", encoding="utf-8") as fp:
            json.dump(playlists, fp, ensure_ascii=False, indent=2)


def extract_metadata(file_path):
    base_name = os.path.splitext(os.path.basename(file_path))[0]

    title = base_name
    artist = ""
    album = ""
    genre = ""
    year = ""
    tracknumber = ""
    duration = 0.0

    try:
        audio = MutagenFile(file_path, easy=True)
        if audio is not None:
            tags = audio.tags or {}

            title = first_non_empty(tags.get("title"), base_name)
            artist = first_non_empty(tags.get("artist"))
            album = first_non_empty(tags.get("album"))
            genre = first_non_empty(tags.get("genre"))
            year = first_non_empty(tags.get("date"), tags.get("year"))
            tracknumber = first_non_empty(tags.get("tracknumber"))

            if getattr(audio, "info", None) is not None and hasattr(audio.info, "length"):
                try:
                    duration = float(audio.info.length)
                except Exception:
                    duration = 0.0
    except Exception:
        pass

    searchable_text = normalize_text(
        " ".join([title, artist, album, genre, year, tracknumber, base_name, file_path])
    )

    return {
        "title": title,
        "artist": artist,
        "album": album,
        "genre": genre,
        "year": year,
        "tracknumber": tracknumber,
        "duration": duration,
        "filename": os.path.basename(file_path),
        "searchable_text": searchable_text,
    }


def scan_music_library():
    global music_list, music_index

    music_list.clear()
    music_index.clear()

    os.makedirs(MUSIC_PATH, exist_ok=True)

    for root, _, files in os.walk(MUSIC_PATH):
        for file_name in files:
            ext = os.path.splitext(file_name)[1].lstrip(".").lower()
            if ext not in PREFIXES:
                continue

            full_path = os.path.join(root, file_name)
            relative_path = os.path.relpath(full_path, MUSIC_PATH).replace("\\", "/")
            meta = extract_metadata(full_path)

            song_id = relative_path
            meta["song_id"] = song_id
            meta["path"] = full_path

            music_list[song_id] = meta
            music_index.append(song_id)


INTERNAL_PLAYER=True
def init(args):
    global MUSIC_PATH, PREFIXES,INTERNAL_PLAYER,set_status,clear_status
    try:
        set_status=args["set_status"]
        clear_status=args["clear_status"]
    except:
        pass
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as fp:
            configs = json.load(fp).get("music_player", {})

        if "music_path" in configs:
            MUSIC_PATH = os.path.normpath(configs["music_path"])
        if "prefixes" in configs:
            PREFIXES = normalize_ext_list(configs["prefixes"])
        if "internal_player" in configs:
            INTERNAL_PLAYER = bool(configs["internal_player"])
    except Exception:
        pass

    os.makedirs(MUSIC_PATH, exist_ok=True)
    os.makedirs(PLAYLIST_EXPORT_DIR, exist_ok=True)

    load_playlists()
    scan_music_library()


def kill():
    save_playlists()


def list_musics_library(query, limit=MAX_SEARCH_RESULTS):
    query = str(query or "").strip()
    if not query:
        return []

    scored = []
    for song_id in music_index:
        song = music_list[song_id]

        title_score = similarity_score(query, song.get("title", ""))
        artist_score = similarity_score(query, song.get("artist", ""))
        album_score = similarity_score(query, song.get("album", ""))
        genre_score = similarity_score(query, song.get("genre", ""))
        file_score = similarity_score(query, song.get("filename", ""))
        blob_score = similarity_score(query, song.get("searchable_text", ""))

        score = (
            0.26 * title_score
            + 0.18 * artist_score
            + 0.12 * album_score
            + 0.12 * genre_score
            + 0.12 * file_score
            + 0.20 * blob_score
        )

        scored.append((score, song))

    scored.sort(key=lambda x: x[0], reverse=True)

    results = []
    for score, song in scored[:max(1, int(limit))]:
        if score <= 0:
            continue
        results.append({
            "title": song["title"],
            "song_id": song["song_id"],
            "artist": song["artist"],
            "album": song["album"],
            "genre": song["genre"],
                        "year": song["year"],
            "tracknumber": song["tracknumber"],
            "duration": round(song["duration"], 2),
            "score": round(float(score), 4),
        })

    return results


def get_best_music_match(query=None, song_id=None):
    if song_id and song_id in music_list:
        return music_list[song_id], 1.0

    results = list_musics_library(query or "", limit=1)
    if not results:
        return None, 0.0

    best = results[0]
    return music_list.get(best["song_id"]), best["score"]


def open_music_file(file_path,loop):
    if INTERNAL_PLAYER:
        music_player.play_music(file_path,loop)
    else:
        os.startfile(file_path)


def ensure_playlist_entry(name, description=""):
    key = playlist_key(name)
    if key not in playlists:
        playlists[key] = {
            "name": name.strip(),
            "description": description.strip(),
            "tracks": []
        }
    elif description.strip() and not playlists[key].get("description"):
        playlists[key]["description"] = description.strip()
    return key, playlists[key]


def load_playlist_by_name(name):
    key = playlist_key(name)
    return key, playlists.get(key)


def export_playlist_m3u8(playlist_name, shuffle=False):
    key, playlist = load_playlist_by_name(playlist_name)
    if not playlist:
        return None, None

    track_ids = list(playlist.get("tracks", []))
    if shuffle:
        random.shuffle(track_ids)
    
    export_name = sanitize_filename(playlist.get("name", playlist_name))
    export_path = os.path.join(PLAYLIST_EXPORT_DIR, f"{export_name}.m3u8")

    with open(export_path, "w", encoding="utf-8") as fp:
        fp.write("#EXTM3U\n")
        for song_id in track_ids:
            song = music_list.get(song_id)
            if not song:
                continue
            fp.write(f'{song["path"]}\n')

    return export_path, playlist


def play_music(args):
    query = args.get("query", "")
    song_id = args.get("song_id", "")
    loop= bool(args.get("loop", True))
    best_song, score = get_best_music_match(query=query, song_id=song_id)

    if not best_song:
        return json.dumps({
            "tool_name": "play_music",
            "result": "No matching music was found.",
            "instruction": "report the result field in plain text(do not show this json to user)"
        })

    try:
        open_music_file(best_song["path"],loop)
        return json.dumps({
            "tool_name": "play_music",
            "result": f'music "{best_song["title"]}" is being played...',
            "song": {
                "song_id": best_song["song_id"],
                "title": best_song["title"],
                "artist": best_song["artist"],
                "album": best_song["album"],
                "genre": best_song["genre"],
                                "score": round(float(score), 4)
            },
            "instruction": "report the result field in plain text(do not show this json to user)"
        })
    except Exception as e:
        return json.dumps({
            "tool_name": "play_music",
            "result": f"Failed to play music",
            "instruction": "report the result field in plain text(do not show this json to user)"
        })


def list_musics(args):
    query = args.get("query", "")
    limit = args.get("limit", MAX_SEARCH_RESULTS)

    if not str(query).strip():
        return json.dumps({
            "tool_name": "list_musics",
            "result": "Missing field query",
            "instruction": "report the result field in plain text(do not show this json to user)"
        })
    res_str="list of musics:\n"
    results = list_musics_library(query=query, limit=limit)
    for num,i in enumerate(results):
        res_str+=str(num+1)+". \n"
        
        res_str+=f"title: {i["title"]}\n"
        res_str+=f"artist: {i["artist"]}\n"
        res_str+=f"album: {i["album"]}\n"
        res_str+=f"genre: {i["genre"]}\n"
        
            

    return json.dumps({
        "tool_name": "list_musics",
        "result": res_str,
        "instruction":"report results."
    }, ensure_ascii=False)


def refresh_music_library(args):
    scan_music_library()
    return json.dumps({
        "tool_name": "refresh_music_library",
        "result": f"Music library refreshed. Found {len(music_list)} tracks.",
                "instruction": "report the result field in plain text(do not show this json to user)"
    }, ensure_ascii=False)


def create_playlist(args):
    playlist_name = args.get("playlist_name", "").strip()
    description = args.get("description", "").strip()

    if not playlist_name:
        return json.dumps({
            "tool_name": "create_playlist",
            "result": "Missing field playlist_name",
            "instruction": "report the result field in plain text(do not show this json to user)"
        })

    key, playlist = ensure_playlist_entry(playlist_name, description)
    save_playlists()

    return json.dumps({
        "tool_name": "create_playlist",
        "result": f'Playlist "{playlist["name"]}" is ready.',
        "playlist_key": key,
        "instruction": "report the result field in plain text(do not show this json to user)"
    })


def add_to_playlist(args):
    playlist_name = args.get("playlist_name", "").strip()
    query = args.get("query", "").strip()
    count = args.get("count", 1)

    if not playlist_name:
        return json.dumps({
            "tool_name": "add_to_playlist",
            "result": "Missing field playlist_name",
            "instruction": "report the result field in plain text(do not show this json to user)"
        })

    if not query:
        return json.dumps({
            "tool_name": "add_to_playlist",
            "result": "Missing field query",
            "instruction": "report the result field in plain text(do not show this json to user)"
        })

    try:
        count = max(1, int(count))
    except Exception:
        count = 1

    key, playlist = ensure_playlist_entry(playlist_name)
    results = list_musics_library(query=query, limit=max(count, PLAYLIST_SEARCH_ADD_COUNT))

    added = []
    existing = set(playlist.get("tracks", []))

    for item in results:
        if item["song_id"] in existing:
            continue
        playlist["tracks"].append(item["song_id"])
        existing.add(item["song_id"])
        added.append({
            "song_id": item["song_id"],
            "title": item["title"],
            "artist": item["artist"],
            "genre": item["genre"],
            "score": item["score"]
        })
        if len(added) >= count:
            break

    save_playlists()

    return json.dumps({
        "tool_name": "add_to_playlist",
        "result": f'Added {len(added)} track(s) to playlist "{playlist["name"]}".',
        "added": added,
        "playlist_key": key,
        "instruction": "report the result field in plain text(do not show this json to user)"
    }, ensure_ascii=False)


def remove_from_playlist(args):
    playlist_name = args.get("playlist_name", "").strip()
    query = args.get("query", "").strip()
    song_id = args.get("song_id", "").strip()

    if not playlist_name:
        return json.dumps({
            "tool_name": "remove_from_playlist",
            "result": "Missing field playlist_name",
            "instruction": "report the result field in plain text(do not show this json to user)"
        })

    key, playlist = load_playlist_by_name(playlist_name)
    if not playlist:
        return json.dumps({
            "tool_name": "remove_from_playlist",
            "result": f'Playlist "{playlist_name}" was not found.',
            "instruction": "report the result field in plain text(do not show this json to user)"
        })

    removed = []

    if song_id:
        if song_id in playlist.get("tracks", []):
            playlist["tracks"].remove(song_id)
            removed.append(song_id)
    elif query:
        results = list_musics_library(query=query, limit=10)
        candidates = {item["song_id"] for item in results}
        playlist_tracks = list(playlist.get("tracks", []))
        for track in playlist_tracks:
            if track in candidates:
                playlist["tracks"].remove(track)
                removed.append(track)
                break
    else:
        return json.dumps({
            "tool_name": "remove_from_playlist",
            "result": "Provide either query or song_id.",
            "instruction": "report the result field in plain text(do not show this json to user)"
        })

    save_playlists()

    return json.dumps({
        "tool_name": "remove_from_playlist",
        "result": f'Removed {len(removed)} track(s) from playlist "{playlist["name"]}".',
        "removed": removed,
        "instruction": "report the result field in plain text(do not show this json to user)"
    }, ensure_ascii=False)


def fetch_playlist_list(args):
    items = []
    for key, playlist in playlists.items():
        items.append({
            "playlist_name": playlist.get("name", key),
            "playlist_key": key,
            "track_count": len(playlist.get("tracks", [])),
            "description": playlist.get("description", "")
        })

    return json.dumps({
        "tool_name": "fetch_playlist_list",
        "result": items,
        "instruction": "report the result field in plain text(do not show this json to user)"
    }, ensure_ascii=False)


def fetch_playlist_tracks(args):
    playlist_name = args.get("playlist_name", "").strip()

    if not playlist_name:
        return json.dumps({
            "tool_name": "fetch_playlist_tracks",
            "result": "Missing field playlist_name",
            "instruction": "report the result field in plain text(do not show this json to user)"
        })

    key, playlist = load_playlist_by_name(playlist_name)
    if not playlist:
        return json.dumps({
            "tool_name": "fetch_playlist_tracks",
            "result": f'Playlist "{playlist_name}" was not found.',
            "instruction": "report the result field in plain text(do not show this json to user)"
        })

    tracks = []
    for song_id in playlist.get("tracks", []):
        song = music_list.get(song_id)
        if not song:
            continue
        tracks.append({
            "song_id": song_id,
            "title": song["title"],
            "artist": song["artist"],
            "album": song["album"],
            "genre": song["genre"],
                        "path": song["path"]
        })

    return json.dumps({
        "tool_name": "fetch_playlist_tracks",
        "result": {
            "playlist_name": playlist.get("name", playlist_name),
            "description": playlist.get("description", ""),
            "track_count": len(tracks),
            "tracks": tracks
        },
        "instruction": "report the result field in plain text(do not show this json to user)"
    }, ensure_ascii=False)


def play_playlist(args):
    playlist_name = args.get("playlist_name", "").strip()
    shuffle = bool(args.get("shuffle", False))

    if not playlist_name:
        return json.dumps({
            "tool_name": "play_playlist",
            "result": "Missing field playlist_name",
            "instruction": "report the result field in plain text(do not show this json to user)"
        })

    export_path, playlist = export_playlist_m3u8(playlist_name, shuffle=shuffle)
    if not playlist:
        return json.dumps({
            "tool_name": "play_playlist",
            "result": f'Playlist "{playlist_name}" was not found.',
            "instruction": "report the result field in plain text(do not show this json to user)"
        })

    if not playlist.get("tracks"):
        return json.dumps({
            "tool_name": "play_playlist",
            "result": f'Playlist "{playlist.get("name", playlist_name)}" is empty.',
            "instruction": "report the result field in plain text(do not show this json to user)"
        })

    try:
        if INTERNAL_PLAYER:
           
           
            music_player.play_playlist(playlist)
            
        else:
            os.startfile(export_path)
        return json.dumps({
            "tool_name": "play_playlist",
            "result": f'Playlist "{playlist.get("name", playlist_name)}" is being played.',
            "track_count": len(playlist.get("tracks", [])),
            "instruction": "report the result field in plain text(do not show this json to user)"
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({
            "tool_name": "play_playlist",
            "result": f"Failed to play playlist",
            "playlist_file": export_path,
            "instruction": "report the result field in plain text(do not show this json to user)"
        }, ensure_ascii=False)

def stop_music(args):
    music_player.stop()
    return json.dumps({
            "tool_name": "stop_music",
            "result": f'stopped playing music',
            "instruction": "report the result field"
        })

def add_tool(tool_dict):
    tool_dict.setdefault("list_musics", {
        "function": list_musics,
        "description": (
            "Lists music by approximate name, artist, album, genre, or any other metadata.(do not call this unless user explicitly asks you) "
           
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Approximate song name, artist, album, genre, or natural language description"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results to return"
                },
                "category": {
                    "type": "string",
                    "description": "Optional metadata category or genre hint"
                }
            },
            "required": ["query"]
        }
    })

    tool_dict.setdefault("play_music", {
        "function": play_music,
        "description": (
            "Plays a song by approximate query or by song_id. "
            "Use search-like matching internally so the exact name does not need to be known."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Approximate song name, artist, album, genre, or description"
                },
                "song_id": {
                    "type": "string",
                    "description": "Exact song identifier returned by list_musics"
                },
                "category": {
                    "type": "string",
                    "description": "Optional metadata category or genre hint"
                },
                "loop":{
                    "type":"bool",
                    "description":"plays music in loop if set true"
                }
            },
            "required": []
        }
    })

    # tool_dict.setdefault("refresh_music_library", {
    #     "function": refresh_music_library,
    #     "description": "Rescans the music folder and rebuilds the metadata index.",
    #     "parameters": {
    #         "type": "object",
    #         "properties": {},
    #         "required": []
    #     }
    # })

    tool_dict.setdefault("create_playlist", {
        "function": create_playlist,
        "description": "Creates a persistent playlist. It is okay if it already exists.",
        "parameters": {
            "type": "object",
            "properties": {
                "playlist_name": {
                    "type": "string",
                    "description": "Name of the playlist"
                },
                "description": {
                    "type": "string",
                    "description": "Optional playlist description"
                }
            },
            "required": ["playlist_name"]
        }
    })

    tool_dict.setdefault("add_to_playlist", {
        "function": add_to_playlist,
        "description": (
            "Adds one or more matching songs to a playlist by approximate search. "
            "Use query text, not enums."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "playlist_name": {
                    "type": "string",
                    "description": "Name of the playlist"
                },
                "query": {
                    "type": "string",
                    "description": "Approximate song name, artist, album, genre, or description"
                },
                "count": {
                    "type": "integer",
                    "description": "How many matches to add"
                }
            },
            "required": ["playlist_name", "query"]
        }
    })

    tool_dict.setdefault("remove_from_playlist", {
        "function": remove_from_playlist,
        "description": "Removes a song from a playlist by approximate query or song_id.",
        "parameters": {
            "type": "object",
            "properties": {
                "playlist_name": {
                    "type": "string",
                    "description": "Name of the playlist"
                },
                "query": {
                    "type": "string",
                    "description": "Approximate song name, artist, album, genre, or description"
                },
                "song_id": {
                    "type": "string",
                    "description": "Exact song identifier returned by list_musics"
                }
            },
            "required": ["playlist_name"]
        }
    })

    tool_dict.setdefault("fetch_playlist_list", {
        "function": fetch_playlist_list,
        "description": "Lists available playlists with counts and descriptions.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    })

    tool_dict.setdefault("fetch_playlist_tracks", {
        "function": fetch_playlist_tracks,
        "description": "Lists tracks inside one playlist.",
        "parameters": {
            "type": "object",
            "properties": {
                "playlist_name": {
                    "type": "string",
                    "description": "Name of the playlist"
                }
            },
            "required": ["playlist_name"]
        }
    })

    tool_dict.setdefault("play_playlist", {
        "function": play_playlist,
        "description": "Exports a playlist and opens it in the default music player.",
        "parameters": {
            "type": "object",
            "properties": {
                "playlist_name": {
                    "type": "string",
                    "description": "Name of the playlist"
                },
                "shuffle": {
                    "type": "boolean",
                    "description": "Whether to shuffle the tracks before export"
                },
                "loop":{
                    "type":"bool",
                    "description":"plays music in loop if set true"
                }
            },
            "required": ["playlist_name"]
        }
    })
    if INTERNAL_PLAYER:
        tool_dict.setdefault("stop_music", {
            "function": stop_music,
            "description": "stop music from being played",
            "parameters": {
                "type": "object",
                "properties":{},
                "required": []
            }
        })