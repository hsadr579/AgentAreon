import pygame
import time

pygame.mixer.init()

MUSIC_PATH = r"C:\Users\ASUS\Music\Agent Areon_musics"

class MusicPlayer:
    def __init__(self, resolver=None):
        self.resolver = resolver
        self._stop_event = threading.Event()
        self._thread = None
        self._lock = threading.Lock()
        pygame.mixer.init()

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

    def _start_worker(self, tracks):
        self.stop()  # do this OUTSIDE the lock
        with self._lock:
            self._stop_event.clear()

            def worker():
                for path in tracks:
                    if self._stop_event.is_set():
                        break

                    if not os.path.exists(path):
                        print(f"File not found: {path}")
                        continue

                    try:
                        pygame.mixer.music.load(path)
                        pygame.mixer.music.play()

                        while pygame.mixer.music.get_busy():
                            if self._stop_event.is_set():
                                pygame.mixer.music.stop()
                                break
                            time.sleep(0.1)

                    except Exception as e:
                        print(f"Failed to play {path}: {e}")

            self._thread = threading.Thread(target=worker, daemon=True)
            self._thread.start()

    def play_music(self, path):
        """
        Plays one music file.
        """
        self._start_worker([path])

    def stop(self):
        """
        Stops playback immediately.
        """
        self._stop_event.set()
        pygame.mixer.music.stop()

        # Don't join if we're already on the worker thread
        if self._thread and self._thread.is_alive() and threading.current_thread() != self._thread:
            self._thread.join(timeout=1)

    def play_playlist(self, playlist):
        """
        Plays a playlist sequentially.
        Playlist can be:
        - {"name": "...", "tracks": [...]}
        - a simple list of tracks
        """
        tracks = self._normalize_tracks(playlist)
        if not tracks:
            print("Playlist is empty.")
            return

        self._start_worker(tracks)
pygame.mixer.music.load(r"C:\Users\ASUS\Music\Agent Areon_musics\Dead Rat-weird.mp3")
pygame.mixer.music.play()

while pygame.mixer.music.get_busy():
    time.sleep(0.1)

print("done")
player = MusicPlayer()

# play one song
player.play_music(r"C:\Users\ASUS\Music\Agent Areon_musics\Dead Rat-weird.mp3")
print(1)
# stop playback
# player.stop()

# play playlist
playlist = {
    "name": "Favorites",
    "tracks": [
        "music/song1.mp3",
        "music/song2.mp3",
        "music/song3.mp3"
    ]
}

