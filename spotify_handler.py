"""
spotify_handler.py — Media Detection Module

Detects the currently playing song on Windows using two methods:

1. PRIMARY: Windows System Media Transport Controls (SMTC)
   - Works with Spotify, YouTube, VLC, and any media player
   - Uses the `winsdk` package to access WinRT APIs
   - No API keys needed

2. FALLBACK: Window title scraping
   - Reads the Spotify window title (format: "Artist - Title")
   - Used when SMTC is unavailable

Emits PyQt6 signals when the song changes or playback state updates.
"""

import asyncio
import threading
import time
from dataclasses import dataclass
from typing import Optional

from PyQt6.QtCore import QObject, QTimer, pyqtSignal, pyqtSlot


# ──────────────────────────────────────────────────────────────
# Data Classes
# ──────────────────────────────────────────────────────────────

@dataclass
class MediaInfo:
    """Holds information about the currently playing media."""
    title: str = ""
    artist: str = ""
    album: str = ""
    is_playing: bool = False
    position_ms: int = 0         # Current playback position
    duration_ms: int = 0         # Total track duration
    source: str = "unknown"      # "smtc", "window_title", "manual"

    @property
    def is_valid(self) -> bool:
        """Check if this media info has meaningful data."""
        return bool(self.title.strip())

    def same_track(self, other: 'MediaInfo') -> bool:
        """Check if two MediaInfo objects refer to the same track."""
        if other is None:
            return False
        return (
            self.title.lower().strip() == other.title.lower().strip()
            and self.artist.lower().strip() == other.artist.lower().strip()
        )


# ──────────────────────────────────────────────────────────────
# SMTC Detection (Primary Method)
# ──────────────────────────────────────────────────────────────

class SMTCDetector:
    """
    Detects currently playing media using Windows System Media 
    Transport Controls (SMTC) via the winsdk package.
    
    This works with ANY media player that registers with Windows
    media controls (Spotify, Chrome/YouTube, VLC, etc.).
    """

    def __init__(self):
        self._available = False
        self._manager = None
        self._loop = None
        self._loop_lock = threading.Lock()
        self._check_availability()

    def _check_availability(self):
        """Check if SMTC is available (requires winsdk package)."""
        try:
            from winsdk.windows.media.control import (
                GlobalSystemMediaTransportControlsSessionManager as MediaManager,
            )
            self._available = True
        except ImportError:
            self._available = False
        except Exception:
            self._available = False

    @property
    def available(self) -> bool:
        return self._available

    def get_current_media(self) -> Optional[MediaInfo]:
        """
        Get info about the currently playing media.
        
        Runs the async WinRT call in a dedicated, cached event loop
        since we're calling from a synchronous context.
        
        Returns:
            MediaInfo if media is playing, None otherwise
        """
        if not self._available:
            return None

        try:
            with self._loop_lock:
                if self._loop is None or self._loop.is_closed():
                    self._loop = asyncio.new_event_loop()
                loop = self._loop

            # Set as the current thread's event loop (required by winsdk)
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(self._async_get_media())
        except Exception as e:
            print(f"[SMTCDetector] Error: {e}")
            # Reset loop on error so it gets recreated next time
            with self._loop_lock:
                self._loop = None
            return None

    async def _async_get_media(self) -> Optional[MediaInfo]:
        """Async implementation of media detection via SMTC."""
        try:
            from winsdk.windows.media.control import (
                GlobalSystemMediaTransportControlsSessionManager as MediaManager,
            )
            from winsdk.windows.media.control import (
                GlobalSystemMediaTransportControlsSessionPlaybackStatus as PlaybackStatus,
            )

            # Request the session manager
            manager = await MediaManager.request_async()
            session = manager.get_current_session()

            if session is None:
                return None

            # Get media properties (title, artist, album)
            properties = await session.try_get_media_properties_async()

            # Get playback info (playing/paused, position)
            playback = session.get_playback_info()
            timeline = session.get_timeline_properties()

            info = MediaInfo(
                title=properties.title or "",
                artist=properties.artist or "",
                album=properties.album_title or "",
                source="smtc",
            )

            # Playback status
            if playback and playback.playback_status is not None:
                info.is_playing = (
                    playback.playback_status == PlaybackStatus.PLAYING
                )

            # Timeline (position and duration)
            if timeline:
                # Position and duration are TimeSpan objects (100-nanosecond units)
                pos = timeline.position
                dur = timeline.end_time
                # Convert to milliseconds
                info.position_ms = int(pos.total_seconds() * 1000) if pos else 0
                info.duration_ms = int(dur.total_seconds() * 1000) if dur else 0

            return info if info.is_valid else None

        except Exception as e:
            print(f"[SMTCDetector] Async error: {e}")
            return None


# ──────────────────────────────────────────────────────────────
# Window Title Detection (Fallback)
# ──────────────────────────────────────────────────────────────

class WindowTitleDetector:
    """
    Fallback: detects Spotify's currently playing song by reading
    the window title. Format is typically "Artist - Song Title".
    
    Less reliable than SMTC but works without winsdk.
    """

    def __init__(self):
        self._available = False
        self._check_availability()

    def _check_availability(self):
        """Check if pywin32 is available."""
        try:
            import win32gui  # noqa: F401
            self._available = True
        except ImportError:
            self._available = False

    @property
    def available(self) -> bool:
        return self._available

    def get_current_media(self) -> Optional[MediaInfo]:
        """
        Get currently playing Spotify track from window title.
        
        Returns:
            MediaInfo if Spotify is playing, None otherwise
        """
        if not self._available:
            return None

        try:
            import win32gui
            import win32process
            import psutil

            def callback(hwnd, results):
                """Window enumeration callback."""
                if not win32gui.IsWindowVisible(hwnd):
                    return
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                try:
                    proc = psutil.Process(pid)
                    if proc.name().lower() in ("spotify.exe",):
                        title = win32gui.GetWindowText(hwnd)
                        if title and title not in ("Spotify", "Spotify Premium", "Spotify Free", ""):
                            results.append(title)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            results = []
            win32gui.EnumWindows(callback, results)

            if results:
                # Parse "Artist - Title" format
                raw = results[0]
                if " - " in raw:
                    parts = raw.split(" - ", 1)
                    return MediaInfo(
                        artist=parts[0].strip(),
                        title=parts[1].strip(),
                        is_playing=True,
                        source="window_title",
                    )

        except Exception as e:
            print(f"[WindowTitleDetector] Error: {e}")

        return None


# ──────────────────────────────────────────────────────────────
# Main Media Handler (combines all detection methods)
# ──────────────────────────────────────────────────────────────

class MediaHandler(QObject):
    """
    Main media detection handler.
    
    Polls for currently playing media at a configurable interval.
    Uses SMTC as primary method, falls back to window title scraping.
    Also supports manual song input.
    
    Signals:
        song_changed(MediaInfo): Emitted when a new song is detected
        playback_changed(bool): Emitted when play/pause state changes
        position_updated(int): Emitted with current position in ms
        status_message(str): Emitted with status updates for the UI
    """

    song_changed = pyqtSignal(object)       # MediaInfo
    playback_changed = pyqtSignal(bool)     # is_playing
    position_updated = pyqtSignal(int)      # position_ms
    status_message = pyqtSignal(str)        # Status text

    def __init__(self, poll_interval_ms: int = 500, parent=None):
        super().__init__(parent)

        # Detection backends
        self._smtc = SMTCDetector()
        self._window = WindowTitleDetector()

        # State tracking
        self._current_media: Optional[MediaInfo] = None
        self._was_playing: bool = False
        self._manual_mode: bool = False
        self._manual_info: Optional[MediaInfo] = None
        self._poll_in_progress: bool = False
        self._pending_poll_result: Optional[MediaInfo] = None

        # Polling timer
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll)
        self._poll_interval = poll_interval_ms

        # Position tracking (separate faster timer for smooth sync)
        self._position_timer = QTimer(self)
        self._position_timer.timeout.connect(self._update_position)
        self._last_position_ms = 0
        self._last_reported_position_ms = -1
        self._last_position_time = 0.0  # time.time() when position was last read
        self._is_playing = False

        # Log which backends are available
        if self._smtc.available:
            print("[MediaHandler] SMTC backend available (primary)")
        if self._window.available:
            print("[MediaHandler] Window title backend available (fallback)")

    def start(self):
        """Start polling for media changes."""
        self._poll_timer.start(self._poll_interval)
        self._position_timer.start(50)  # 50ms for smooth position tracking
        self.status_message.emit("Listening for music...")
        self._poll()  # Immediate first poll

    def stop(self):
        """Stop polling."""
        self._poll_timer.stop()
        self._position_timer.stop()

    def set_poll_interval(self, interval_ms: int):
        """Change the polling interval."""
        self._poll_interval = interval_ms
        if self._poll_timer.isActive():
            self._poll_timer.start(interval_ms)

    def set_manual_song(self, title: str, artist: str = ""):
        """
        Set a song manually (when auto-detection isn't working).
        
        Args:
            title: Song title
            artist: Artist name
        """
        self._manual_mode = True
        self._manual_info = MediaInfo(
            title=title,
            artist=artist,
            is_playing=True,
            source="manual",
        )
        self.song_changed.emit(self._manual_info)
        self.status_message.emit(f"Manual: {artist} - {title}")

    def clear_manual(self):
        """Exit manual mode and resume auto-detection."""
        self._manual_mode = False
        self._manual_info = None
        self.status_message.emit("Listening for music...")

    def _poll(self):
        """
        Poll for currently playing media.
        
        Runs in a background thread to avoid blocking the UI,
        then marshals results back to the main thread via invokeMethod.
        """
        if self._manual_mode:
            return

        # Avoid stacking polls if a previous one hasn't finished
        if self._poll_in_progress:
            return
        self._poll_in_progress = True

        def _do_poll():
            try:
                media = None

                # Try SMTC first (works with all media players)
                if self._smtc.available:
                    media = self._smtc.get_current_media()

                # Fallback to window title scraping
                if media is None and self._window.available:
                    media = self._window.get_current_media()

                # Marshal back to the main thread for signal emission
                self._pending_poll_result = media
                from PyQt6.QtCore import QMetaObject, Qt
                QMetaObject.invokeMethod(
                    self, "_handle_poll_result", Qt.ConnectionType.QueuedConnection
                )
            except Exception as e:
                print(f"[MediaHandler] Poll error: {e}")
                self._poll_in_progress = False

        # Run in a background thread to prevent UI freezing
        thread = threading.Thread(target=_do_poll, daemon=True)
        thread.start()

    @pyqtSlot()
    def _handle_poll_result(self):
        """Handle poll result on the main thread (invoked via QMetaObject)."""
        self._poll_in_progress = False
        media = self._pending_poll_result
        self._process_poll_result(media)

    def _process_poll_result(self, media: Optional[MediaInfo]):
        """Process the polling result and emit appropriate signals."""

        if media is None:
            # No media detected
            if self._current_media is not None:
                self._current_media = None
                self._is_playing = False
                self.playback_changed.emit(False)
                self.status_message.emit("No music detected")
            return

        # Check if the song changed
        if self._current_media is None or not media.same_track(self._current_media):
            self._current_media = media
            self._is_playing = media.is_playing
            self._last_reported_position_ms = media.position_ms
            self._last_position_ms = media.position_ms
            self._last_position_time = time.time()

            self.song_changed.emit(media)
            self.status_message.emit(
                f"♫ {media.artist} — {media.title}" if media.artist
                else f"♫ {media.title}"
            )

        # Check if playback state changed
        if media.is_playing != self._was_playing:
            self._was_playing = media.is_playing
            self._is_playing = media.is_playing
            self.playback_changed.emit(media.is_playing)

            if media.is_playing:
                self._last_reported_position_ms = media.position_ms
                self._last_position_ms = media.position_ms
                self._last_position_time = time.time()

        # Update position reference if the player reported a new position (seek/skip)
        if media.position_ms >= 0 and media.position_ms != self._last_reported_position_ms:
            self._last_reported_position_ms = media.position_ms
            self._last_position_ms = media.position_ms
            self._last_position_time = time.time()

    def _update_position(self):
        """
        Estimate current playback position between polls.
        
        Uses the last known position + elapsed wall-clock time
        for smooth interpolation (since SMTC polling is slow).
        """
        if not self._is_playing or self._current_media is None:
            return

        elapsed = (time.time() - self._last_position_time) * 1000
        estimated_pos = int(self._last_position_ms + elapsed)

        self.position_updated.emit(estimated_pos)

    def get_detection_status(self) -> str:
        """Return a human-readable status of detection backends."""
        backends = []
        if self._smtc.available:
            backends.append("SMTC [OK]")
        else:
            backends.append("SMTC [N/A]")
        if self._window.available:
            backends.append("Win32 [OK]")
        else:
            backends.append("Win32 [N/A]")
        return " | ".join(backends)

    def cleanup(self):
        """Clean up timers on shutdown."""
        self.stop()
