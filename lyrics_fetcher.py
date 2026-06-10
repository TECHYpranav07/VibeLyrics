"""
lyrics_fetcher.py — LRCLIB API Client

Fetches synced (.lrc) and plain lyrics from the free LRCLIB API.
Runs network requests in a background QThread to prevent UI freezing.

API Base URL: https://lrclib.net/api
No API key required.
"""

import requests
from PyQt6.QtCore import QObject, QThread, pyqtSignal, pyqtSlot


# ──────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────

API_BASE = "https://lrclib.net/api"
USER_AGENT = "VibeLyrics/1.0 (https://github.com/vibelyrics)"
REQUEST_TIMEOUT = 15  # seconds (increased for slower connections)


# ──────────────────────────────────────────────────────────────
# Data container for fetched lyrics
# ──────────────────────────────────────────────────────────────

class LyricsResult:
    """Holds the result of a lyrics fetch operation."""

    def __init__(self):
        self.title: str = ""
        self.artist: str = ""
        self.album: str = ""
        self.duration: float = 0.0
        self.synced_lyrics: str = ""     # Raw LRC text (if available)
        self.plain_lyrics: str = ""      # Plain text fallback
        self.is_synced: bool = False     # Whether synced lyrics were found
        self.found: bool = False         # Whether any lyrics were found
        self.error: str = ""             # Error message if fetch failed
        self.translations: dict = {}     # original text -> English translation
        self.source_lang: str = "en"     # Detected source language

    def __repr__(self):
        return (
            f"LyricsResult(title='{self.title}', artist='{self.artist}', "
            f"synced={self.is_synced}, found={self.found})"
        )


# ──────────────────────────────────────────────────────────────
# Synchronous API functions (called from worker thread)
# ──────────────────────────────────────────────────────────────

def _make_headers() -> dict:
    """Standard headers for LRCLIB API requests."""
    return {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    }

# Shared session for connection pooling (reuses TCP connections)
_session: requests.Session = None

def _get_session() -> requests.Session:
    """Get or create a shared requests session with automatic retries."""
    global _session
    if _session is None:
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry

        _session = requests.Session()
        _session.headers.update(_make_headers())

        # Retry up to 3 times on connection/timeout errors with backoff
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,  # 1s, 2s, 4s delays between retries
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        _session.mount("https://", adapter)
        _session.mount("http://", adapter)
    return _session


def search_lyrics(title: str, artist: str = "") -> LyricsResult:
    """
    Search for lyrics using the LRCLIB /search endpoint.
    
    Tries to find the best match for the given title and artist.
    Prefers results that have synced lyrics.
    
    Args:
        title: Song title
        artist: Artist name (optional but recommended)
    
    Returns:
        LyricsResult with the best matching lyrics
    """
    result = LyricsResult()
    result.title = title
    result.artist = artist

    try:
        # Build search parameters
        params = {"track_name": title}
        if artist:
            params["artist_name"] = artist

        response = _get_session().get(
            f"{API_BASE}/search",
            params=params,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()

        data = response.json()

        if not data or not isinstance(data, list) or len(data) == 0:
            result.error = "No lyrics found"
            return result

        # Find the best match — prefer entries with synced lyrics
        best = None
        for entry in data:
            if entry.get("syncedLyrics"):
                best = entry
                break
        
        # Fallback to first result if no synced lyrics found
        if best is None:
            best = data[0]

        # Extract lyrics
        result.title = best.get("trackName", title)
        result.artist = best.get("artistName", artist)
        result.album = best.get("albumName", "")
        result.duration = best.get("duration", 0.0)

        if best.get("syncedLyrics"):
            result.synced_lyrics = best["syncedLyrics"]
            result.is_synced = True
            result.found = True
        elif best.get("plainLyrics"):
            result.plain_lyrics = best["plainLyrics"]
            result.is_synced = False
            result.found = True
        else:
            result.error = "Lyrics entry found but no content"

    except requests.exceptions.Timeout:
        result.error = "Request timed out"
    except requests.exceptions.ConnectionError:
        result.error = "No internet connection"
    except requests.exceptions.HTTPError as e:
        result.error = f"HTTP error: {e.response.status_code}"
    except Exception as e:
        result.error = f"Unexpected error: {str(e)}"

    return result


def get_lyrics_by_signature(
    title: str,
    artist: str,
    album: str = "",
    duration: float = 0.0,
) -> LyricsResult:
    """
    Fetch lyrics using the precise /get endpoint (track signature).
    
    This is more accurate than search when you have full metadata
    (e.g., from Spotify/media detection).
    
    Args:
        title: Song title
        artist: Artist name
        album: Album name (optional)
        duration: Song duration in seconds (optional, helps matching)
    
    Returns:
        LyricsResult with fetched lyrics
    """
    result = LyricsResult()
    result.title = title
    result.artist = artist
    result.album = album
    result.duration = duration

    try:
        params = {
            "track_name": title,
            "artist_name": artist,
        }
        if album:
            params["album_name"] = album
        if duration > 0:
            params["duration"] = int(duration)

        response = _get_session().get(
            f"{API_BASE}/get",
            params=params,
            timeout=REQUEST_TIMEOUT,
        )

        # /get returns 404 if no match — that's OK, we fallback to search
        if response.status_code == 404:
            # Fallback to search endpoint
            return search_lyrics(title, artist)

        response.raise_for_status()
        data = response.json()

        result.title = data.get("trackName", title)
        result.artist = data.get("artistName", artist)
        result.album = data.get("albumName", album)
        result.duration = data.get("duration", duration)

        if data.get("syncedLyrics"):
            result.synced_lyrics = data["syncedLyrics"]
            result.is_synced = True
            result.found = True
        elif data.get("plainLyrics"):
            result.plain_lyrics = data["plainLyrics"]
            result.is_synced = False
            result.found = True
        else:
            result.error = "Track found but no lyrics available"

    except requests.exceptions.Timeout:
        result.error = "Request timed out"
    except requests.exceptions.ConnectionError:
        result.error = "No internet connection"
    except requests.exceptions.HTTPError as e:
        result.error = f"HTTP error: {e.response.status_code}"
    except Exception as e:
        result.error = f"Unexpected error: {str(e)}"

    return result


def _process_translation(result: LyricsResult):
    """Romanize lyrics if needed, mapping original text to romanized text (Romaji, Pinyin, etc.)."""
    try:
        from settings import SettingsManager
        settings = SettingsManager()
        translation_enabled = settings.get("translation_enabled", True)
    except Exception:
        translation_enabled = True

    if not (result.found and translation_enabled):
        return

    lines_to_translate = []
    from lrc_parser import parse_lrc, parse_plain_lyrics
    
    if result.is_synced and result.synced_lyrics:
        parsed = parse_lrc(result.synced_lyrics)
        lines_to_translate = [line.text for line in parsed if line.text.strip()]
    elif result.plain_lyrics:
        parsed = parse_plain_lyrics(result.plain_lyrics)
        lines_to_translate = [line.text for line in parsed if line.text.strip()]
        
    if lines_to_translate:
        # De-duplicate lines to minimize API calls
        unique_lines = list(set([l.strip() for l in lines_to_translate if l.strip()]))
        if not unique_lines:
            return

        import concurrent.futures
        session = _get_session()
        
        translations_map = {}
        detected_languages = []

        def fetch_line(text):
            try:
                r = session.get(
                    "https://translate.googleapis.com/translate_a/single",
                    params={
                        "client": "gtx",
                        "sl": "auto",
                        "tl": "en",
                        "dt": "rm",
                        "q": text,
                    },
                    timeout=5,
                )
                if r.status_code == 200:
                    data = r.json()
                    if data and data[0] and len(data[0]) > 0:
                        last_elem = data[0][-1]
                        if len(last_elem) > 3 and last_elem[3]:
                            return text, last_elem[3].strip(), data[2]
                return text, None, "en"
            except Exception:
                return text, None, "en"

        # Fetch transliterations in parallel using connection pooling
        with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
            futures = [executor.submit(fetch_line, line) for line in unique_lines]
            for future in concurrent.futures.as_completed(futures):
                orig, translit, lang = future.result()
                if lang and lang != "en" and lang != "error":
                    detected_languages.append(lang)
                if translit and orig.lower().strip() != translit.lower().strip():
                    translations_map[orig] = translit

        # Determine dominant language
        if detected_languages:
            from collections import Counter
            result.source_lang = Counter(detected_languages).most_common(1)[0][0]
        else:
            result.source_lang = "en"

        # Apply mapped translations if the source language is non-English
        if result.source_lang != "en":
            result.translations = translations_map


# ──────────────────────────────────────────────────────────────
# QThread Worker — runs fetches in background
# ──────────────────────────────────────────────────────────────

class LyricsFetchWorker(QObject):
    """
    Background worker that fetches lyrics without blocking the UI.
    
    Signals:
        lyrics_ready: Emitted when lyrics are fetched (LyricsResult)
        error_occurred: Emitted on fetch failure (error message)
    """
    lyrics_ready = pyqtSignal(object)    # Emits LyricsResult
    error_occurred = pyqtSignal(str)     # Emits error message

    def __init__(self):
        super().__init__()
        # In-memory cache: key = "title|artist" → LyricsResult
        self._cache: dict[str, LyricsResult] = {}

    def _cache_key(self, title: str, artist: str) -> str:
        """Generate a cache key from title and artist."""
        return f"{title.lower().strip()}|{artist.lower().strip()}"

    @pyqtSlot(str, str, str, float)
    def fetch(self, title: str, artist: str, album: str = "", duration: float = 0.0):
        """
        Fetch lyrics for a song (called from the worker thread).
        
        Checks cache first, then tries /get endpoint, then /search fallback.
        
        Args:
            title: Song title
            artist: Artist name
            album: Album name
            duration: Song duration in seconds
        """
        key = self._cache_key(title, artist)

        # Check cache first
        if key in self._cache:
            self.lyrics_ready.emit(self._cache[key])
            return

        # Try precise endpoint first (better accuracy with full metadata)
        if artist:
            result = get_lyrics_by_signature(title, artist, album, duration)
        else:
            result = search_lyrics(title, artist)

        # Translate if needed
        if result.found:
            _process_translation(result)

        # Cache the result (even failures, to avoid repeated requests)
        self._cache[key] = result

        if result.found:
            self.lyrics_ready.emit(result)
        else:
            self.error_occurred.emit(result.error or "No lyrics found")

    def clear_cache(self):
        """Clear the lyrics cache."""
        self._cache.clear()


class LyricsFetcher(QObject):
    """
    High-level lyrics fetcher that manages the worker thread.
    
    Usage:
        fetcher = LyricsFetcher()
        fetcher.lyrics_ready.connect(my_handler)
        fetcher.fetch_lyrics("Bohemian Rhapsody", "Queen")
    """
    lyrics_ready = pyqtSignal(object)     # Forwards LyricsResult
    error_occurred = pyqtSignal(str)      # Forwards error message

    def __init__(self, parent=None):
        super().__init__(parent)

        # Create worker and thread
        self._worker = LyricsFetchWorker()
        self._thread = QThread()
        self._worker.moveToThread(self._thread)

        # Connect worker signals to our signals (forwarding)
        self._worker.lyrics_ready.connect(self.lyrics_ready)
        self._worker.error_occurred.connect(self.error_occurred)

        # Start the thread
        self._thread.start()

    def fetch_lyrics(self, title: str, artist: str = "", album: str = "", duration: float = 0.0):
        """
        Request lyrics fetch (non-blocking).
        
        The result will be emitted via the lyrics_ready signal.
        """
        # Use QMetaObject.invokeMethod equivalent — direct call since worker is on another thread
        # We use a signal-slot mechanism for thread safety
        from PyQt6.QtCore import QMetaObject, Qt, Q_ARG
        QMetaObject.invokeMethod(
            self._worker,
            "fetch",
            Qt.ConnectionType.QueuedConnection,
            Q_ARG(str, title),
            Q_ARG(str, artist),
            Q_ARG(str, album),
            Q_ARG(str, str(duration)),
        )

    def fetch_lyrics_direct(self, title: str, artist: str = "", album: str = "", duration: float = 0.0):
        """
        Alternative fetch method using a simpler thread approach.
        Creates a one-shot thread for each fetch request.
        Marshals results back to the main thread via signals.
        """
        import threading

        def _do_fetch():
            key = self._worker._cache_key(title, artist)
            # Check cache first (fast path)
            if key in self._worker._cache:
                result = self._worker._cache[key]
                if result.found:
                    self.lyrics_ready.emit(result)
                else:
                    self.error_occurred.emit(result.error or "No lyrics found")
                return

            import concurrent.futures

            result = None
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                futures = []
                if artist:
                    futures.append(executor.submit(get_lyrics_by_signature, title, artist, album, duration))
                futures.append(executor.submit(search_lyrics, title, artist))

                for future in concurrent.futures.as_completed(futures):
                    res = future.result()
                    if res and res.found:
                        result = res
                        # Cancel remaining (though ThreadPoolExecutor doesn't strictly cancel running threads,
                        # it stops waiting for the other ones since we break)
                        break

            if result is None:
                # If neither succeeded, just take the result of the search (even if it's an error)
                result = search_lyrics(title, artist)

            # Translate if needed
            if result.found:
                _process_translation(result)

            # Cache the result
            self._worker._cache[key] = result

            # Emit signals (they'll be delivered cross-thread via Qt's auto-connection)
            if result.found:
                self.lyrics_ready.emit(result)
            else:
                self.error_occurred.emit(result.error or "No lyrics found")

        thread = threading.Thread(target=_do_fetch, daemon=True)
        thread.start()

    def clear_cache(self):
        """Clear the lyrics cache."""
        self._worker.clear_cache()

    def cleanup(self):
        """Clean up the worker thread on shutdown."""
        self._thread.quit()
        self._thread.wait(3000)
