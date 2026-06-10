"""
main.py — VibeLyrics Entry Point

Wires together all components:
    - OverlayWindow (lyrics display)
    - SettingsPanel (configuration)
    - MediaHandler (song detection)
    - LyricsFetcher (LRCLIB API)
    - SyncEngine (lyrics timing)
    - System tray icon
    - Global keyboard shortcuts

Run:
    python main.py
"""

import sys
import os
import threading


def resource_path(relative_path: str) -> str:
    """Get absolute path to resource, works for dev and PyInstaller."""
    if getattr(sys, 'frozen', False):
        # Running as compiled exe — resources are in sys._MEIPASS
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QIcon, QPixmap, QImage, QPainter, QColor, QAction, QFont, QLinearGradient, QBrush

from overlay import OverlayWindow
from settings import SettingsPanel, SettingsManager
from spotify_handler import MediaHandler, MediaInfo
from lyrics_fetcher import LyricsFetcher, LyricsResult
from lrc_parser import SyncEngine, parse_lrc, parse_plain_lyrics


# ──────────────────────────────────────────────────────────────
# Generate App Icon (programmatic — no external file needed)
# ──────────────────────────────────────────────────────────────

def create_app_icon() -> QIcon:
    """
    Create a simple music-note icon programmatically.
    This avoids requiring an external icon file.
    """
    size = 64
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(0, 0, 0, 0))  # Transparent

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Background circle with gradient
    gradient = QLinearGradient(0, 0, size, size)
    gradient.setColorAt(0.0, QColor(124, 58, 237))    # Purple
    gradient.setColorAt(1.0, QColor(79, 70, 229))     # Indigo
    painter.setBrush(QBrush(gradient))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(2, 2, size - 4, size - 4)

    # Music note symbol
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(255, 255, 255))

    # Note head (filled ellipse)
    painter.drawEllipse(14, 36, 16, 12)
    painter.drawEllipse(34, 32, 16, 12)

    # Note stems
    painter.setBrush(QColor(255, 255, 255))
    painter.drawRect(28, 14, 3, 30)
    painter.drawRect(48, 10, 3, 30)

    # Beam connecting stems
    painter.drawRect(28, 12, 23, 4)

    painter.end()
    return QIcon(pixmap)


# ──────────────────────────────────────────────────────────────
# Dark Theme Palette
# ──────────────────────────────────────────────────────────────

def apply_dark_theme(app: QApplication):
    """Apply a dark color palette to the entire application."""
    from PyQt6.QtGui import QPalette
    palette = QPalette()

    # Dark background colors
    palette.setColor(QPalette.ColorRole.Window, QColor(18, 18, 28))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(220, 220, 220))
    palette.setColor(QPalette.ColorRole.Base, QColor(25, 25, 38))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(30, 30, 45))
    palette.setColor(QPalette.ColorRole.Text, QColor(220, 220, 220))
    palette.setColor(QPalette.ColorRole.Button, QColor(30, 30, 45))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(220, 220, 220))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(124, 58, 237))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))

    app.setPalette(palette)


# ──────────────────────────────────────────────────────────────
# Keyboard Shortcuts (global, via keyboard library)
# ──────────────────────────────────────────────────────────────

class GlobalShortcuts:
    """
    Registers global keyboard shortcuts using the `keyboard` library.
    Runs the listener in a background thread.
    
    Shortcuts:
        Ctrl+Shift+H — Toggle overlay visibility
        Ctrl+Shift+Up — Increase font size
        Ctrl+Shift+Down — Decrease font size
        Ctrl+Shift+L — Open settings
        Ctrl+Shift+M — Toggle mini mode
        Ctrl+Shift+T — Toggle click-through
    """

    def __init__(self, app_controller: 'VibeLyricsApp'):
        self._app = app_controller
        self._registered = False

    def register(self):
        """Register all global keyboard shortcuts."""
        try:
            import keyboard as kb

            kb.add_hotkey('ctrl+shift+h', self._app.toggle_overlay)
            kb.add_hotkey('ctrl+shift+up', self._app.increase_font)
            kb.add_hotkey('ctrl+shift+down', self._app.decrease_font)
            kb.add_hotkey('ctrl+alt+page down', self._app.decrease_offset)
            kb.add_hotkey('ctrl+alt+page up', self._app.increase_offset)
            kb.add_hotkey('ctrl+shift+l', self._app.show_settings)
            kb.add_hotkey('ctrl+shift+m', self._app.toggle_mini_mode)
            kb.add_hotkey('ctrl+shift+t', self._app.toggle_click_through)

            self._registered = True
            print("[Shortcuts] Global shortcuts registered")
        except ImportError:
            print("[Shortcuts] keyboard library not available - shortcuts disabled")
        except Exception as e:
            print(f"[Shortcuts] Error registering shortcuts: {e}")
            print("[Shortcuts] Try running as Administrator for global hotkeys")

    def unregister(self):
        """Unregister all shortcuts."""
        if self._registered:
            try:
                import keyboard as kb
                kb.unhook_all()
            except Exception:
                pass


# ──────────────────────────────────────────────────────────────
# System Tray Icon
# ──────────────────────────────────────────────────────────────

class SystemTray:
    """
    System tray icon with context menu.
    
    Menu:
        - Show/Hide Overlay
        - Open Settings
        - Mini Mode
        - About
        - Quit
    """

    def __init__(self, app_controller: 'VibeLyricsApp', icon: QIcon):
        self._app = app_controller

        self._tray = QSystemTrayIcon(icon)
        self._tray.setToolTip("VibeLyrics — Floating Lyrics Overlay")

        # Context menu
        menu = QMenu()
        menu.setStyleSheet("""
            QMenu {
                background: rgb(25, 25, 40);
                color: #E0E0E0;
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 8px;
                padding: 5px;
            }
            QMenu::item {
                padding: 6px 20px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background: rgba(124, 58, 237, 0.4);
            }
        """)

        show_action = QAction("👁  Show/Hide Overlay", menu)
        show_action.triggered.connect(self._app.toggle_overlay)
        menu.addAction(show_action)

        settings_action = QAction("⚙  Settings", menu)
        settings_action.triggered.connect(self._app.show_settings)
        menu.addAction(settings_action)

        mini_action = QAction("📏  Mini Mode", menu)
        mini_action.triggered.connect(self._app.toggle_mini_mode)
        menu.addAction(mini_action)

        menu.addSeparator()

        about_action = QAction("ℹ  About VibeLyrics", menu)
        about_action.triggered.connect(self._show_about)
        menu.addAction(about_action)

        menu.addSeparator()

        quit_action = QAction("✕  Quit", menu)
        quit_action.triggered.connect(self._app.quit)
        menu.addAction(quit_action)

        self._tray.setContextMenu(menu)

        # Single-click or double-click tray icon → toggle overlay
        self._tray.activated.connect(self._on_activated)

    def show(self):
        self._tray.show()

    def show_startup_notification(self):
        """Show a brief notification when the app starts in the tray."""
        self._tray.showMessage(
            "VibeLyrics is running ♫",
            "Lyrics will appear automatically when you play music.\n"
            "Right-click this icon for options.\n"
            "Ctrl+Shift+H to toggle overlay.",
            QSystemTrayIcon.MessageIcon.Information,
            3000,
        )

    def _on_activated(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.DoubleClick,
                      QSystemTrayIcon.ActivationReason.Trigger):
            self._app.toggle_overlay()

    def _show_about(self):
        self._tray.showMessage(
            "VibeLyrics v1.0",
            "Floating lyrics overlay for any media player.\n"
            "Powered by LRCLIB API.\n\n"
            "Shortcuts:\n"
            "  Ctrl+Shift+H — Show/Hide\n"
            "  Ctrl+Shift+L — Settings",
            QSystemTrayIcon.MessageIcon.Information,
            5000,
        )

    def set_tooltip(self, text: str):
        self._tray.setToolTip(text)


# ──────────────────────────────────────────────────────────────
# Main Application Controller
# ──────────────────────────────────────────────────────────────

class VibeLyricsApp:
    """
    Main application controller that wires all components together.
    
    Flow:
        1. MediaHandler detects song → emits song_changed
        2. LyricsFetcher fetches lyrics from LRCLIB → emits lyrics_ready
        3. SyncEngine parses lyrics and tracks position
        4. QTimer updates OverlayWindow every 50ms with current lyric context
    """

    def __init__(self):
        # ── Settings ──
        self._settings_manager = SettingsManager()

        # ── Core components ──
        self._overlay = OverlayWindow()
        self._settings_panel = SettingsPanel(self._settings_manager)
        # ── Backend ──
        self._media_handler = MediaHandler(poll_interval_ms=500)
        self._lyrics_fetcher = LyricsFetcher()
        self._sync_engine = SyncEngine()

        # ── State ──
        self._current_track = None   # Current MediaInfo
        self._current_track_key = None # Used for saving track-specific offsets
        self._click_through = False

        # ── App icon ──
        self._icon = create_app_icon()

        # ── System tray ──
        self._tray = SystemTray(self, self._icon)

        # ── Keyboard shortcuts ──
        self._shortcuts = GlobalShortcuts(self)

        # ── Sync timer: updates lyrics on the overlay every 50ms ──
        self._sync_timer = QTimer()
        self._sync_timer.setInterval(50)
        self._sync_timer.timeout.connect(self._sync_tick)

        # ── Wire up signals ──
        self._connect_signals()

        # ── Apply initial settings ──
        self._apply_settings(self._settings_manager.all)

    def _connect_signals(self):
        """Connect all component signals to their handlers."""

        # Media detection → lyrics fetch
        self._media_handler.song_changed.connect(self._on_song_changed)
        self._media_handler.playback_changed.connect(self._on_playback_changed)
        self._media_handler.status_message.connect(self._overlay.set_status)

        # Lyrics fetcher → sync engine
        self._lyrics_fetcher.lyrics_ready.connect(self._on_lyrics_ready)
        self._lyrics_fetcher.error_occurred.connect(self._on_lyrics_error)

        # Settings panel → apply settings
        self._settings_panel.settings_changed.connect(self._apply_settings)
        self._settings_panel.manual_search.connect(self._on_manual_search)

        # Overlay → settings panel
        self._overlay.settings_requested.connect(self.show_settings)

    def start(self):
        """Start the application — launches silently in system tray."""
        print("=" * 50)
        print("  VibeLyrics v1.0")
        print("  Floating Lyrics Overlay")
        print("=" * 50)
        print(f"  Detection: {self._media_handler.get_detection_status()}")
        print(f"  Settings: {os.path.abspath(SettingsManager()._filepath)}")
        print("  Mode: Starting minimized to system tray")
        print("=" * 50)

        # DON'T show overlay on startup — it lives in the tray
        # Overlay will auto-appear when music starts playing
        self._overlay.show_idle()

        # Start system tray and show startup notification
        self._tray.show()
        self._tray.show_startup_notification()

        # Start media detection
        self._media_handler.start()

        # Start sync timer
        self._sync_timer.start()

        # Register keyboard shortcuts
        self._shortcuts.register()

        # Ensure Windows startup registry is in sync with setting
        if self._settings_manager.get("start_with_windows", False):
            self._settings_panel._set_windows_startup(True)
            print("  [Startup] Registered in Windows startup")

    # ──────────────────────────────────────────────────────────
    # Signal Handlers
    # ──────────────────────────────────────────────────────────

    def _on_song_changed(self, media_info: MediaInfo):
        """Called when the media handler detects a new song."""
        print(f"[App] Song changed: {media_info.artist} - {media_info.title}")

        self._current_track = media_info
        
        # Generate a unique key for the song to store its offset
        self._current_track_key = f"{media_info.artist} - {media_info.title}" if media_info.artist else media_info.title
        self._settings_panel.set_current_track(self._current_track_key)

        # Clear old lyrics
        self._sync_engine.clear()
        self._overlay.update_lyrics(self._sync_engine.get_context(0))

        # Dynamic cover art theming
        if self._settings_manager.get("dynamic_theme", True) and hasattr(media_info, 'thumbnail_bytes') and media_info.thumbnail_bytes:
            image = QImage()
            if image.loadFromData(media_info.thumbnail_bytes):
                self._apply_dynamic_theme(image)
            else:
                self._overlay.reset_theme_colors()
        else:
            self._overlay.reset_theme_colors()

        # Auto-show overlay when a song is detected
        if not self._overlay.isVisible():
            self._overlay.show()

        # Fetch new lyrics
        self._lyrics_fetcher.fetch_lyrics_direct(
            title=media_info.title,
            artist=media_info.artist,
            album=media_info.album,
            duration=media_info.duration_ms / 1000.0 if media_info.duration_ms else 0,
        )

        # Update tray tooltip
        self._tray.set_tooltip(f"VibeLyrics — {media_info.artist} – {media_info.title}")

    def _apply_dynamic_theme(self, image: QImage):
        """Extract dominant colors from album art and apply to overlay."""
        if image.isNull():
            self._overlay.reset_theme_colors()
            return

        # Scale down to 8x8 to extract average and dominant colors quickly
        small = image.scaled(8, 8, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.FastTransformation)
        
        vibrant_color = None
        max_sat = -1
        
        r_sum, g_sum, b_sum = 0, 0, 0
        for x in range(8):
            for y in range(8):
                c = QColor(small.pixelColor(x, y))
                r_sum += c.red()
                g_sum += c.green()
                b_sum += c.blue()
                
                # Extract HSV to find the most vibrant color
                h, s, v, a = c.getHsv()
                if s > max_sat and v > 50: # Avoid near-black or grey colors
                    max_sat = s
                    vibrant_color = c
                    
        avg_color = QColor(r_sum // 64, g_sum // 64, b_sum // 64)
        
        if vibrant_color is None or max_sat < 30:
            # Fallback to average color or default purple if very dark/grey
            vibrant_color = avg_color if avg_color.value() > 50 else QColor("#7C3AED")
            
        h, s, v, a = vibrant_color.getHsv()
        # Enforce vibrance and brightness for text highlight
        vibrant_color = QColor.fromHsv(h, max(s, 150), max(v, 200))
        
        # Glow background: dark version of the dominant color
        bg_glow = QColor.fromHsv(h, max(s, 100), 30)
        
        self._overlay.set_dynamic_theme_colors(vibrant_color, bg_glow)

    def _on_playback_changed(self, is_playing: bool):
        """Called when play/pause state changes."""
        if not is_playing:
            self._overlay.set_status("⏸ Paused")
            # Auto-hide overlay after a short delay when paused
            self._overlay.auto_hide_idle()
        else:
            if self._current_track:
                self._overlay.set_status(
                    f"♫ {self._current_track.artist} — {self._current_track.title}"
                )
                # Auto-show overlay when playback resumes
                if not self._overlay.isVisible():
                    self._overlay.show()

    def _on_lyrics_ready(self, result: LyricsResult):
        """Called when lyrics are fetched from LRCLIB."""
        print(f"[App] Lyrics ready: synced={result.is_synced}")

        if result.is_synced and result.synced_lyrics:
            lines = parse_lrc(result.synced_lyrics)
            # Map translations if present
            if getattr(result, "translations", None):
                for line in lines:
                    line_s = line.text.strip()
                    if line_s in result.translations:
                        line.translation = result.translations[line_s]
            self._sync_engine.load_lyrics(lines, is_synced=True)
        elif result.plain_lyrics:
            lines = parse_plain_lyrics(result.plain_lyrics)
            # Map translations if present
            if getattr(result, "translations", None):
                for line in lines:
                    line_s = line.text.strip()
                    if line_s in result.translations:
                        line.translation = result.translations[line_s]
            self._sync_engine.load_lyrics(lines, is_synced=False)
            self._overlay.show_plain_lyrics_message()
        else:
            self._overlay.show_no_lyrics(result.title, result.artist)

    def _on_lyrics_error(self, error: str):
        """Called when lyrics fetch fails."""
        print(f"[App] Lyrics error: {error}")
        if self._current_track:
            self._overlay.show_no_lyrics(
                self._current_track.title, self._current_track.artist
            )
        self._overlay.set_status(f"⚠ {error}")

    def _on_manual_search(self, title: str, artist: str):
        """Handle manual search from settings panel."""
        print(f"[App] Manual search: {artist} - {title}")

        # Set manual mode on media handler
        self._media_handler.set_manual_song(title, artist)

        # Fetch lyrics
        self._sync_engine.clear()
        self._lyrics_fetcher.fetch_lyrics_direct(title=title, artist=artist)

    # ──────────────────────────────────────────────────────────
    # Sync Timer (50ms tick)
    # ──────────────────────────────────────────────────────────

    def _sync_tick(self):
        """
        Called every 50ms to update the lyric display.
        
        Gets the estimated playback position from MediaHandler,
        queries the SyncEngine for the current lyric context,
        and updates the overlay if the line has changed.
        """
        if not self._sync_engine.has_lyrics:
            return

        if not self._sync_engine.is_synced:
            # For plain lyrics, just show the first few lines
            context = self._sync_engine.get_context(0)
            self._overlay.update_lyrics(context)
            return

        # Get estimated position (interpolated between polls)
        # We rely on position_updated signal, but also read it here
        if self._current_track and self._media_handler._is_playing:
            import time
            elapsed = (time.time() - self._media_handler._last_position_time) * 1000
            position_ms = int(self._media_handler._last_position_ms + elapsed)

            # Apply hybrid sync offset
            global_offset = self._settings_manager.get("global_offset_ms", 0)
            track_offsets = self._settings_manager.get("song_offsets", {})
            track_offset = track_offsets.get(self._current_track_key, 0) if self._current_track_key else 0
            
            adjusted_position = max(0, position_ms + global_offset + track_offset)

            # Check if the active line changed (to trigger animation only on change)
            if self._sync_engine.has_line_changed(adjusted_position):
                context = self._sync_engine.get_context(adjusted_position)
                self._overlay.update_lyrics(context)
            else:
                # Update karaoke progress smoothly even if line hasn't changed
                context = self._sync_engine.get_context(adjusted_position)
                self._overlay.update_karaoke_progress(context.progress)

    # ──────────────────────────────────────────────────────────
    # Settings Application
    # ──────────────────────────────────────────────────────────

    def _apply_settings(self, settings: dict):
        """Apply a settings dictionary to all components."""
        # Overlay appearance
        self._overlay.set_font_size(settings.get("font_size", 28))
        self._overlay.set_font_family(settings.get("font_family", "Segoe UI"))
        self._overlay.set_font_color(settings.get("font_color", "#FFFFFF"))
        self._overlay.set_overlay_opacity(settings.get("overlay_opacity", 0.95))
        self._overlay.set_bg_opacity(settings.get("bg_opacity", 0.55))
        self._overlay.set_alignment(settings.get("alignment", "center"))
        self._overlay.set_animations_enabled(settings.get("animations_enabled", True))
        self._overlay.set_always_on_top(settings.get("always_on_top", True))
        self._overlay.set_auto_hide(settings.get("auto_hide", True))

        # Check if translation setting changed
        old_trans = getattr(self, "_translation_enabled", None)
        new_trans = settings.get("translation_enabled", True)
        self._translation_enabled = new_trans
        self._overlay.set_translation_enabled(new_trans)

        if old_trans is not None and old_trans != new_trans:
            # Clear cache and re-fetch currently playing song's lyrics
            self._lyrics_fetcher.clear_cache()
            if self._current_track:
                print("[App] Translation setting changed. Re-fetching lyrics...")
                self._lyrics_fetcher.fetch_lyrics_direct(
                    title=self._current_track.title,
                    artist=self._current_track.artist,
                    album=self._current_track.album,
                    duration=self._current_track.duration_ms / 1000.0 if self._current_track.duration_ms else 0,
                )

        # Check dynamic theme setting
        if not settings.get("dynamic_theme", True):
            self._overlay.reset_theme_colors()
        elif self._current_track and hasattr(self._current_track, 'thumbnail_bytes') and self._current_track.thumbnail_bytes:
            image = QImage()
            if image.loadFromData(self._current_track.thumbnail_bytes):
                self._apply_dynamic_theme(image)

        # Click-through
        click_through = settings.get("click_through", False)
        if click_through != self._click_through:
            self._click_through = click_through
            self._overlay.set_click_through(click_through)

        # Force immediate visual update on settings change (e.g. alignment or offsets)
        self._sync_tick()

    # ──────────────────────────────────────────────────────────
    # Public Actions (called by shortcuts / tray / settings)
    # ──────────────────────────────────────────────────────────

    def toggle_overlay(self):
        """Toggle overlay visibility."""
        self._overlay.toggle_visibility()

    def show_settings(self):
        """Show the settings panel next to the overlay."""
        self._settings_panel.show_next_to(self._overlay.geometry())

    def increase_font(self):
        """Increase font size by 2."""
        current = self._settings_manager.get("font_size", 28)
        new_size = min(72, current + 2)
        self._settings_manager.set("font_size", new_size)
        self._overlay.set_font_size(new_size)

    def decrease_font(self):
        """Decrease font size by 2."""
        current = self._settings_manager.get("font_size", 28)
        new_size = max(12, current - 2)
        self._settings_manager.set("font_size", new_size)
        self._overlay.set_font_size(new_size)

    def increase_offset(self):
        """Advance track-specific lyrics by 500ms (+0.5s offset)."""
        if not self._current_track_key:
            return
        
        offsets = self._settings_manager.get("song_offsets", {})
        track_ms = offsets.get(self._current_track_key, 0) + 500
        offsets[self._current_track_key] = track_ms
        self._settings_manager.set("song_offsets", offsets)
        
        # Update UI slider
        self._settings_panel.set_current_track(self._current_track_key)
        self._overlay.set_status(f"⏱ Track: {track_ms / 1000:+.1f}s")
        self._sync_tick()

    def decrease_offset(self):
        """Delay track-specific lyrics by 500ms (-0.5s offset)."""
        if not self._current_track_key:
            return
            
        offsets = self._settings_manager.get("song_offsets", {})
        track_ms = offsets.get(self._current_track_key, 0) - 500
        offsets[self._current_track_key] = track_ms
        self._settings_manager.set("song_offsets", offsets)
        
        # Update UI slider
        self._settings_panel.set_current_track(self._current_track_key)
        self._overlay.set_status(f"⏱ Track: {track_ms / 1000:+.1f}s")
        self._sync_tick()

    def toggle_mini_mode(self):
        """Toggle mini mode on the overlay."""
        self._overlay.toggle_mini_mode()

    def toggle_click_through(self):
        """Toggle click-through mode."""
        self._click_through = not self._click_through
        self._overlay.set_click_through(self._click_through)
        self._settings_manager.set("click_through", self._click_through)

    def quit(self):
        """Clean up and quit the application."""
        print("[App] Shutting down...")
        self._sync_timer.stop()
        self._media_handler.cleanup()
        self._lyrics_fetcher.cleanup()
        self._shortcuts.unregister()
        QApplication.quit()


# ──────────────────────────────────────────────────────────────
# Entry Point
# ──────────────────────────────────────────────────────────────

def main():
    """Application entry point."""
    # When running as frozen exe, set working directory to exe location
    if getattr(sys, 'frozen', False):
        os.chdir(os.path.dirname(sys.executable))

    # Create QApplication
    app = QApplication(sys.argv)
    app.setApplicationName("VibeLyrics")
    app.setApplicationDisplayName("VibeLyrics")
    app.setQuitOnLastWindowClosed(False)  # Keep running in tray

    # Apply dark theme
    apply_dark_theme(app)

    # Set default font
    font = QFont("Segoe UI", 10)
    app.setFont(font)

    # Create and start the app controller
    controller = VibeLyricsApp()
    controller.start()

    # Run event loop
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
