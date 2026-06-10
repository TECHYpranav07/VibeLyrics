"""
settings.py — Settings Panel & Persistence

Provides a glassmorphism-styled settings window for configuring:
    - Font size, color, and family
    - Overlay and background opacity
    - Always-on-top, animations, click-through toggles
    - Lyrics alignment
    - Auto-hide when no music
    - Startup with Windows
    - Manual song search
    - Keyboard shortcut reference

Settings are persisted to a JSON file in the app directory.
"""

import json
import os
import sys
import winreg
from pathlib import Path
from typing import Any

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider, QPushButton,
    QLineEdit, QComboBox, QCheckBox, QGroupBox, QFormLayout,
    QColorDialog, QApplication, QScrollArea, QFrame,
)
from PyQt6.QtCore import Qt, pyqtSignal, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QLinearGradient, QBrush, QPen, QFont, QIcon


# ──────────────────────────────────────────────────────────────
# Constants & Defaults
# ──────────────────────────────────────────────────────────────

def _get_settings_dir() -> str:
    """Get the settings directory. Uses %APPDATA%/VibeLyrics when frozen."""
    if getattr(sys, 'frozen', False):
        # Running as compiled exe — save settings to AppData
        appdata = os.environ.get('APPDATA', os.path.expanduser('~'))
        settings_dir = os.path.join(appdata, 'VibeLyrics')
    else:
        # Running as script — save settings next to the script
        settings_dir = os.path.dirname(os.path.abspath(__file__))
    os.makedirs(settings_dir, exist_ok=True)
    return settings_dir

SETTINGS_FILE = os.path.join(_get_settings_dir(), "settings.json")

DEFAULT_SETTINGS = {
    "font_size": 28,
    "font_color": "#FFFFFF",
    "font_family": "Segoe UI",
    "overlay_opacity": 0.95,
    "bg_opacity": 0.55,
    "always_on_top": True,
    "animations_enabled": True,
    "alignment": "center",
    "click_through": False,
    "auto_hide": True,
    "start_with_windows": False,
    "mini_mode": False,
    "global_offset_ms": 0,
    "song_offsets": {},
    "dynamic_theme": True,
    "translation_enabled": True,
}


# ──────────────────────────────────────────────────────────────
# Settings Manager (Load / Save)
# ──────────────────────────────────────────────────────────────

class SettingsManager:
    """
    Handles loading and saving settings to a JSON file.
    Provides defaults for any missing keys.
    """

    def __init__(self, filepath: str = SETTINGS_FILE):
        self._filepath = filepath
        self._settings = dict(DEFAULT_SETTINGS)
        self.load()

    def load(self):
        """Load settings from the JSON file. Missing keys get defaults."""
        try:
            if os.path.exists(self._filepath):
                with open(self._filepath, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                # Merge: saved values override defaults
                self._settings = {**DEFAULT_SETTINGS, **saved}
        except (json.JSONDecodeError, IOError) as e:
            print(f"[Settings] Error loading settings: {e}")
            self._settings = dict(DEFAULT_SETTINGS)

    def save(self):
        """Save current settings to the JSON file."""
        try:
            with open(self._filepath, "w", encoding="utf-8") as f:
                json.dump(self._settings, f, indent=2)
        except IOError as e:
            print(f"[Settings] Error saving settings: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        """Get a setting value."""
        return self._settings.get(key, default)

    def set(self, key: str, value: Any):
        """Set a setting value and save."""
        self._settings[key] = value
        self.save()

    @property
    def all(self) -> dict:
        """Return all settings as a dict."""
        return dict(self._settings)


# ──────────────────────────────────────────────────────────────
# Styled Widgets (for the glassmorphism settings panel)
# ──────────────────────────────────────────────────────────────

PANEL_STYLE = """
    QWidget#settingsPanel {
        background: transparent;
    }
    QGroupBox {
        color: #E0E0E0;
        font-size: 13px;
        font-weight: bold;
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 12px;
        margin-top: 14px;
        padding: 16px 12px 12px 12px;
        background: rgba(255, 255, 255, 0.03);
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 16px;
        padding: 0 6px;
    }
    QLabel {
        color: #C0C0C0;
        font-size: 12px;
    }
    QSlider::groove:horizontal {
        border: none;
        height: 6px;
        background: rgba(255, 255, 255, 0.1);
        border-radius: 3px;
    }
    QSlider::handle:horizontal {
        background: #7C3AED;
        border: none;
        width: 16px;
        height: 16px;
        margin: -5px 0;
        border-radius: 8px;
    }
    QSlider::sub-page:horizontal {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 #7C3AED, stop:1 #A855F7);
        border-radius: 3px;
    }
    QPushButton {
        background: rgba(124, 58, 237, 0.3);
        color: #E0E0E0;
        border: 1px solid rgba(124, 58, 237, 0.4);
        border-radius: 8px;
        padding: 8px 18px;
        font-size: 12px;
        font-weight: bold;
    }
    QPushButton:hover {
        background: rgba(124, 58, 237, 0.5);
        border-color: rgba(124, 58, 237, 0.7);
    }
    QPushButton:pressed {
        background: rgba(124, 58, 237, 0.7);
    }
    QPushButton#colorBtn {
        min-width: 40px;
        min-height: 28px;
        border-radius: 6px;
    }
    QLineEdit {
        background: rgba(255, 255, 255, 0.06);
        color: #E0E0E0;
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 8px;
        padding: 7px 12px;
        font-size: 12px;
    }
    QLineEdit:focus {
        border-color: rgba(124, 58, 237, 0.6);
    }
    QComboBox {
        background: rgba(255, 255, 255, 0.06);
        color: #E0E0E0;
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 8px;
        padding: 6px 12px;
        font-size: 12px;
    }
    QComboBox::drop-down {
        border: none;
        width: 24px;
    }
    QComboBox QAbstractItemView {
        background: rgb(30, 30, 45);
        color: #E0E0E0;
        selection-background-color: rgba(124, 58, 237, 0.4);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 8px;
    }
    QCheckBox {
        color: #C0C0C0;
        font-size: 12px;
        spacing: 8px;
    }
    QCheckBox::indicator {
        width: 18px;
        height: 18px;
        border-radius: 4px;
        border: 1px solid rgba(255, 255, 255, 0.2);
        background: rgba(255, 255, 255, 0.05);
    }
    QCheckBox::indicator:checked {
        background: rgba(124, 58, 237, 0.7);
        border-color: rgba(124, 58, 237, 0.9);
    }
    QScrollArea {
        border: none;
        background: transparent;
    }
    QScrollBar:vertical {
        background: rgba(255, 255, 255, 0.03);
        width: 8px;
        border-radius: 4px;
    }
    QScrollBar::handle:vertical {
        background: rgba(255, 255, 255, 0.15);
        border-radius: 4px;
        min-height: 30px;
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        height: 0;
    }
"""


# ──────────────────────────────────────────────────────────────
# Settings Panel Window
# ──────────────────────────────────────────────────────────────

class SettingsPanel(QWidget):
    """
    Glassmorphism-styled settings panel.
    
    Signals:
        settings_changed(dict): Emitted whenever any setting changes
        manual_search(str, str): Emitted when manual search is triggered (title, artist)
    """

    settings_changed = pyqtSignal(dict)
    manual_search = pyqtSignal(str, str)

    def __init__(self, settings_manager: SettingsManager, parent=None):
        super().__init__(parent)
        self._settings = settings_manager

        # Window setup
        self.setWindowTitle("VibeLyrics Settings")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(420, 680)
        self.setObjectName("settingsPanel")

        # For dragging
        self._dragging = False
        self._drag_position = None

        # State
        self._current_track_key = None

        # Build UI
        self._build_ui()
        self._load_values()

    def _build_ui(self):
        """Construct the settings panel layout."""
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        # Scroll area for all settings
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        content = QWidget()
        content.setObjectName("settingsPanel")
        content.setStyleSheet(PANEL_STYLE)
        layout = QVBoxLayout(content)
        layout.setSpacing(10)
        layout.setContentsMargins(18, 18, 18, 18)

        # ── Title Bar ──
        title_bar = QHBoxLayout()
        title_label = QLabel("⚙  VibeLyrics Settings")
        title_label.setStyleSheet("color: white; font-size: 16px; font-weight: bold;")
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(30, 30)
        close_btn.setStyleSheet("""
            QPushButton { 
                background: rgba(255, 80, 80, 0.3); 
                border: none; border-radius: 15px; 
                color: white; font-size: 14px; 
            }
            QPushButton:hover { background: rgba(255, 80, 80, 0.6); }
        """)
        close_btn.clicked.connect(self.hide)
        title_bar.addWidget(title_label)
        title_bar.addStretch()
        title_bar.addWidget(close_btn)
        layout.addLayout(title_bar)

        # ── Appearance Group ──
        appearance = QGroupBox("Appearance")
        form = QFormLayout()
        form.setSpacing(10)

        # Font size
        self._font_size_slider = QSlider(Qt.Orientation.Horizontal)
        self._font_size_slider.setRange(12, 72)
        self._font_size_label = QLabel("28pt")
        font_size_row = QHBoxLayout()
        font_size_row.addWidget(self._font_size_slider, stretch=3)
        font_size_row.addWidget(self._font_size_label, stretch=1)
        self._font_size_slider.valueChanged.connect(self._on_font_size)
        form.addRow("Font Size:", font_size_row)

        # Font family
        self._font_family = QComboBox()
        self._font_family.addItems([
            "Segoe UI", "Arial", "Helvetica", "Inter", "Roboto",
            "Consolas", "Calibri", "Verdana", "Outfit",
        ])
        self._font_family.currentTextChanged.connect(self._on_font_family)
        form.addRow("Font:", self._font_family)

        # Font color
        self._color_btn = QPushButton()
        self._color_btn.setObjectName("colorBtn")
        self._color_btn.setFixedSize(60, 30)
        self._color_btn.clicked.connect(self._pick_color)
        self._current_color = "#FFFFFF"
        self._update_color_btn()
        form.addRow("Color:", self._color_btn)

        # Alignment
        self._alignment = QComboBox()
        self._alignment.addItems(["center", "left", "right"])
        self._alignment.currentTextChanged.connect(self._on_alignment)
        form.addRow("Alignment:", self._alignment)

        appearance.setLayout(form)
        layout.addWidget(appearance)

        # ── Overlay Group ──
        overlay_group = QGroupBox("Overlay")
        overlay_form = QFormLayout()
        overlay_form.setSpacing(10)

        # Overlay opacity
        self._overlay_opacity = QSlider(Qt.Orientation.Horizontal)
        self._overlay_opacity.setRange(10, 100)
        self._overlay_opacity_label = QLabel("95%")
        opacity_row = QHBoxLayout()
        opacity_row.addWidget(self._overlay_opacity, stretch=3)
        opacity_row.addWidget(self._overlay_opacity_label, stretch=1)
        self._overlay_opacity.valueChanged.connect(self._on_overlay_opacity)
        overlay_form.addRow("Window Opacity:", opacity_row)

        # Background opacity
        self._bg_opacity = QSlider(Qt.Orientation.Horizontal)
        self._bg_opacity.setRange(0, 100)
        self._bg_opacity_label = QLabel("55%")
        bg_row = QHBoxLayout()
        bg_row.addWidget(self._bg_opacity, stretch=3)
        bg_row.addWidget(self._bg_opacity_label, stretch=1)
        self._bg_opacity.valueChanged.connect(self._on_bg_opacity)
        overlay_form.addRow("Background:", bg_row)

        overlay_group.setLayout(overlay_form)
        layout.addWidget(overlay_group)

        # ── Behavior Group ──
        behavior = QGroupBox("Behavior")
        beh_layout = QVBoxLayout()
        beh_layout.setSpacing(8)

        self._chk_always_top = QCheckBox("Always on top")
        self._chk_always_top.stateChanged.connect(self._on_toggle)
        beh_layout.addWidget(self._chk_always_top)

        self._chk_animations = QCheckBox("Enable animations")
        self._chk_animations.stateChanged.connect(self._on_toggle)
        beh_layout.addWidget(self._chk_animations)

        self._chk_click_through = QCheckBox("Click-through mode")
        self._chk_click_through.stateChanged.connect(self._on_toggle)
        beh_layout.addWidget(self._chk_click_through)

        self._chk_auto_hide = QCheckBox("Auto-hide when no music")
        self._chk_auto_hide.stateChanged.connect(self._on_toggle)
        beh_layout.addWidget(self._chk_auto_hide)

        self._chk_startup = QCheckBox("Start with Windows")
        self._chk_startup.stateChanged.connect(self._on_startup_toggle)
        beh_layout.addWidget(self._chk_startup)

        self._chk_dynamic_theme = QCheckBox("Dynamic theme from song art")
        self._chk_dynamic_theme.stateChanged.connect(self._on_toggle)
        beh_layout.addWidget(self._chk_dynamic_theme)

        self._chk_translation = QCheckBox("Romanize lyrics (Romaji, Pinyin, etc.)")
        self._chk_translation.stateChanged.connect(self._on_toggle)
        beh_layout.addWidget(self._chk_translation)

        # Global Offset
        global_row = QHBoxLayout()
        global_label = QLabel("Global Delay:")
        global_label.setToolTip("Applies to ALL songs (e.g., Bluetooth lag)")
        self._global_offset_slider = QSlider(Qt.Orientation.Horizontal)
        self._global_offset_slider.setRange(-100, 100) # -10.0s to 10.0s
        self._global_offset_label = QLabel("0.0s")
        self._global_offset_slider.valueChanged.connect(self._on_global_offset)
        global_row.addWidget(global_label)
        global_row.addWidget(self._global_offset_slider, stretch=2)
        global_row.addWidget(self._global_offset_label)
        beh_layout.addLayout(global_row)

        # Track Offset
        track_row = QHBoxLayout()
        self._track_label = QLabel("Track Override:")
        self._track_label.setToolTip("Applies ONLY to the current song")
        self._track_offset_slider = QSlider(Qt.Orientation.Horizontal)
        self._track_offset_slider.setRange(-100, 100)
        self._track_offset_label = QLabel("0.0s")
        self._track_offset_slider.valueChanged.connect(self._on_track_offset)
        track_row.addWidget(self._track_label)
        track_row.addWidget(self._track_offset_slider, stretch=2)
        track_row.addWidget(self._track_offset_label)
        beh_layout.addLayout(track_row)

        behavior.setLayout(beh_layout)
        layout.addWidget(behavior)

        # ── Manual Search Group ──
        search_group = QGroupBox("Manual Search")
        search_layout = QVBoxLayout()
        search_layout.setSpacing(8)

        self._search_title = QLineEdit()
        self._search_title.setPlaceholderText("Song title...")
        search_layout.addWidget(self._search_title)

        self._search_artist = QLineEdit()
        self._search_artist.setPlaceholderText("Artist name (optional)...")
        search_layout.addWidget(self._search_artist)

        search_btn = QPushButton("🔍  Search Lyrics")
        search_btn.clicked.connect(self._on_manual_search)
        search_layout.addWidget(search_btn)

        search_group.setLayout(search_layout)
        layout.addWidget(search_group)

        # ── Keyboard Shortcuts ──
        shortcuts = QGroupBox("Keyboard Shortcuts")
        sc_layout = QVBoxLayout()
        sc_layout.setSpacing(4)

        shortcuts_info = [
            ("Ctrl+Shift+H", "Show / Hide overlay"),
            ("Ctrl+Shift+Up", "Increase font size"),
            ("Ctrl+Shift+Down", "Decrease font size"),
            ("Ctrl+Alt+PgDown", "Track offset -0.5s"),
            ("Ctrl+Alt+PgUp", "Track offset +0.5s"),
            ("Ctrl+Shift+L", "Open settings"),
            ("Ctrl+Shift+M", "Toggle mini mode"),
            ("Ctrl+Shift+T", "Toggle click-through"),
        ]
        for key, desc in shortcuts_info:
            row = QHBoxLayout()
            key_label = QLabel(key)
            key_label.setStyleSheet(
                "background: rgba(255,255,255,0.08); padding: 3px 8px; "
                "border-radius: 4px; font-family: Consolas; font-size: 11px; color: #A0A0A0;"
            )
            key_label.setFixedWidth(145)
            desc_label = QLabel(desc)
            desc_label.setStyleSheet("color: #888; font-size: 11px;")
            row.addWidget(key_label)
            row.addWidget(desc_label)
            row.addStretch()
            sc_layout.addLayout(row)

        shortcuts.setLayout(sc_layout)
        layout.addWidget(shortcuts)

        # ── About ──
        about_label = QLabel("VibeLyrics v1.0 — Powered by LRCLIB")
        about_label.setStyleSheet("color: rgba(255,255,255,0.25); font-size: 10px;")
        about_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(about_label)

        layout.addStretch()

        scroll.setWidget(content)
        outer.addWidget(scroll)

    # ──────────────────────────────────────────────────────────
    # Load / Apply Values
    # ──────────────────────────────────────────────────────────

    def _load_values(self):
        """Load current settings into the UI controls."""
        s = self._settings

        self._font_size_slider.setValue(s.get("font_size", 28))
        self._font_family.setCurrentText(s.get("font_family", "Segoe UI"))
        self._current_color = s.get("font_color", "#FFFFFF")
        self._update_color_btn()

        self._overlay_opacity.setValue(int(s.get("overlay_opacity", 0.95) * 100))
        self._bg_opacity.setValue(int(s.get("bg_opacity", 0.55) * 100))

        self._alignment.setCurrentText(s.get("alignment", "center"))

        self._chk_always_top.setChecked(s.get("always_on_top", True))
        self._chk_animations.setChecked(s.get("animations_enabled", True))
        self._chk_click_through.setChecked(s.get("click_through", False))
        self._chk_auto_hide.setChecked(s.get("auto_hide", True))
        self._chk_startup.setChecked(s.get("start_with_windows", False))
        self._chk_dynamic_theme.setChecked(s.get("dynamic_theme", True))
        self._chk_translation.setChecked(s.get("translation_enabled", True))

        # Global offset
        global_ms = s.get("global_offset_ms", 0)
        self._global_offset_slider.setValue(int(global_ms / 100))
        self._global_offset_label.setText(f"{global_ms / 1000:+.1f}s")

        # Track offset (default 0 until a track is set)
        self._track_offset_slider.setValue(0)
        self._track_offset_label.setText("+0.0s")

    def set_current_track(self, track_key: str):
        """Called by main when a new song plays to load its specific offset."""
        self._current_track_key = track_key
        offsets = self._settings.get("song_offsets", {})
        track_ms = offsets.get(track_key, 0)
        
        # Disconnect momentarily to avoid triggering save
        self._track_offset_slider.blockSignals(True)
        self._track_offset_slider.setValue(int(track_ms / 100))
        self._track_offset_label.setText(f"{track_ms / 1000:+.1f}s")
        self._track_offset_slider.blockSignals(False)

        # Update label to show which track is selected (truncate if too long)
        display_name = track_key[:25] + "..." if len(track_key) > 25 else track_key
        self._track_label.setText(f"Override ({display_name}):")

    def _emit_settings(self):
        """Emit the current settings dict."""
        self.settings_changed.emit(self._settings.all)

    # ──────────────────────────────────────────────────────────
    # Event Handlers
    # ──────────────────────────────────────────────────────────

    def _on_font_size(self, value):
        self._font_size_label.setText(f"{value}pt")
        self._settings.set("font_size", value)
        self._emit_settings()

    def _on_font_family(self, family):
        self._settings.set("font_family", family)
        self._emit_settings()

    def _pick_color(self):
        color = QColorDialog.getColor(
            QColor(self._current_color), self, "Choose Font Color"
        )
        if color.isValid():
            self._current_color = color.name()
            self._settings.set("font_color", self._current_color)
            self._update_color_btn()
            self._emit_settings()

    def _update_color_btn(self):
        self._color_btn.setStyleSheet(
            f"QPushButton#colorBtn {{ "
            f"background: {self._current_color}; "
            f"border: 2px solid rgba(255,255,255,0.2); "
            f"border-radius: 6px; min-width: 40px; min-height: 28px; }}"
        )

    def _on_alignment(self, align):
        self._settings.set("alignment", align)
        self._emit_settings()

    def _on_overlay_opacity(self, value):
        self._overlay_opacity_label.setText(f"{value}%")
        self._settings.set("overlay_opacity", value / 100.0)
        self._emit_settings()

    def _on_bg_opacity(self, value):
        self._bg_opacity_label.setText(f"{value}%")
        self._settings.set("bg_opacity", value / 100.0)
        self._emit_settings()

    def _on_toggle(self):
        self._settings.set("always_on_top", self._chk_always_top.isChecked())
        self._settings.set("animations_enabled", self._chk_animations.isChecked())
        self._settings.set("click_through", self._chk_click_through.isChecked())
        self._settings.set("auto_hide", self._chk_auto_hide.isChecked())
        self._settings.set("dynamic_theme", self._chk_dynamic_theme.isChecked())
        self._settings.set("translation_enabled", self._chk_translation.isChecked())
        self._emit_settings()

    def _on_startup_toggle(self):
        enabled = self._chk_startup.isChecked()
        self._settings.set("start_with_windows", enabled)
        self._set_windows_startup(enabled)
        self._emit_settings()

    def _on_global_offset(self, value):
        offset_ms = value * 100
        self._global_offset_label.setText(f"{offset_ms / 1000:+.1f}s")
        self._settings.set("global_offset_ms", offset_ms)
        self._emit_settings()

    def _on_track_offset(self, value):
        if not self._current_track_key:
            return
            
        offset_ms = value * 100
        self._track_offset_label.setText(f"{offset_ms / 1000:+.1f}s")
        
        # Save to the song dictionary
        offsets = self._settings.get("song_offsets", {})
        offsets[self._current_track_key] = offset_ms
        self._settings.set("song_offsets", offsets)
        self._emit_settings()

    def _on_manual_search(self):
        title = self._search_title.text().strip()
        artist = self._search_artist.text().strip()
        if title:
            self.manual_search.emit(title, artist)

    # ──────────────────────────────────────────────────────────
    # Windows Startup Registration
    # ──────────────────────────────────────────────────────────

    def _set_windows_startup(self, enable: bool):
        """Add or remove the app from Windows startup registry."""
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        app_name = "VibeLyrics"

        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE
            )
            if enable:
                if getattr(sys, 'frozen', False):
                    # Running as compiled exe — register the exe directly
                    cmd = f'"{sys.executable}"'
                else:
                    # Running as script — register python + script path
                    exe = sys.executable
                    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py")
                    cmd = f'"{exe}" "{script}"'
                winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, cmd)
            else:
                try:
                    winreg.DeleteValue(key, app_name)
                except FileNotFoundError:
                    pass
            winreg.CloseKey(key)
        except Exception as e:
            print(f"[Settings] Startup registry error: {e}")

    # ──────────────────────────────────────────────────────────
    # Painting (Glassmorphism)
    # ──────────────────────────────────────────────────────────

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        path = QPainterPath()
        radius = 16
        path.addRoundedRect(
            0.0, 0.0,
            float(self.width()), float(self.height()),
            radius, radius,
        )

        # Dark glassmorphism background
        gradient = QLinearGradient(0, 0, 0, self.height())
        gradient.setColorAt(0.0, QColor(22, 18, 35, 240))
        gradient.setColorAt(1.0, QColor(12, 10, 22, 250))
        painter.fillPath(path, QBrush(gradient))

        # Border
        painter.setPen(QPen(QColor(255, 255, 255, 20), 1))
        painter.drawPath(path)

        painter.end()

    # ──────────────────────────────────────────────────────────
    # Dragging
    # ──────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self._dragging and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_position)

    def mouseReleaseEvent(self, event):
        self._dragging = False

    # ──────────────────────────────────────────────────────────
    # Show / Position
    # ──────────────────────────────────────────────────────────

    def show_next_to(self, overlay_geometry):
        """Position the settings panel next to the overlay window."""
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            # Try to place to the right of the overlay
            x = overlay_geometry.right() + 20
            if x + self.width() > geo.right():
                # Place to the left instead
                x = overlay_geometry.left() - self.width() - 20
            y = max(geo.top(), overlay_geometry.top())
            self.move(x, y)
        self.show()
        self.raise_()
