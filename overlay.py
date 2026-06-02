"""
overlay.py — Floating Lyrics Overlay Window

The main visual component of VibeLyrics. Displays lyrics as a floating,
transparent, always-on-top overlay that works on top of any application.

Features:
    - Glassmorphism UI with rounded corners
    - 3-line lyric display (previous / current / next)
    - Smooth fade + slide animations
    - Draggable and resizable
    - Click-through mode (Windows)
    - Mini mode (single-line compact)
    - Karaoke word highlighting
    - Adjustable opacity, font, and colors
"""

import sys
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGraphicsOpacityEffect,
    QSizeGrip, QApplication,
)
from PyQt6.QtCore import (
    Qt, QPropertyAnimation, QEasingCurve, QPoint, QRect, QSize,
    pyqtSignal, QParallelAnimationGroup, QSequentialAnimationGroup,
    QTimer, pyqtProperty,
)
from PyQt6.QtGui import (
    QPainter, QColor, QPainterPath, QFont, QLinearGradient,
    QBrush, QPen, QFontMetrics, QCursor,
)

from lrc_parser import LyricContext, LyricLine


# ──────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────

DEFAULT_FONT_SIZE = 28
DEFAULT_FONT_FAMILY = "Segoe UI"
DEFAULT_FONT_COLOR = "#FFFFFF"
DEFAULT_BG_OPACITY = 0.55
DEFAULT_OVERLAY_OPACITY = 0.95
DEFAULT_CORNER_RADIUS = 20
ANIMATION_DURATION = 300  # milliseconds


# ──────────────────────────────────────────────────────────────
# Animated Lyric Label
# ──────────────────────────────────────────────────────────────

class LyricLabel(QWidget):
    """
    Custom label for displaying a single lyric line with:
    - Fade in/out animations
    - Slide up/down animations
    - Karaoke-style progressive word highlighting
    - Customizable font, color, and opacity
    """

    def __init__(self, role: str = "current", parent=None):
        """
        Args:
            role: "previous", "current", or "next" — determines styling
        """
        super().__init__(parent)
        self._role = role
        self._text = ""
        self._font_size = DEFAULT_FONT_SIZE
        self._font_family = DEFAULT_FONT_FAMILY
        self._font_color = QColor(DEFAULT_FONT_COLOR)
        self._karaoke_progress = 0.0  # 0.0–1.0 for word highlighting
        self._base_opacity = self._get_role_opacity()
        self._alignment = Qt.AlignmentFlag.AlignCenter
        self._animations_enabled = True

        # Opacity effect for fade animations
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(self._base_opacity)
        self.setGraphicsEffect(self._opacity_effect)

        # Size based on role
        self._update_font_metrics()

        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def _get_role_opacity(self) -> float:
        """Get the default opacity based on the label's role."""
        if self._role == "current":
            return 1.0
        elif self._role == "previous":
            return 0.35
        else:  # next
            return 0.35

    def _get_role_font_scale(self) -> float:
        """Get the font size scale based on the label's role."""
        if self._role == "current":
            return 1.0
        else:
            return 0.65

    def set_text(self, text: str, animate: bool = True):
        """Update the displayed text with optional animation."""
        if text == self._text:
            return

        if animate and self._animations_enabled and text:
            self._animate_text_change(text)
        else:
            self._text = text
            self._karaoke_progress = 0.0
            self.update()

    def _animate_text_change(self, new_text: str):
        """Animate the transition between lyric lines."""
        # Fade out → change text → fade in
        fade_out = QPropertyAnimation(self._opacity_effect, b"opacity", self)
        fade_out.setDuration(ANIMATION_DURATION // 2)
        fade_out.setStartValue(self._opacity_effect.opacity())
        fade_out.setEndValue(0.0)
        fade_out.setEasingCurve(QEasingCurve.Type.InQuad)

        fade_in = QPropertyAnimation(self._opacity_effect, b"opacity", self)
        fade_in.setDuration(ANIMATION_DURATION // 2)
        fade_in.setStartValue(0.0)
        fade_in.setEndValue(self._base_opacity)
        fade_in.setEasingCurve(QEasingCurve.Type.OutQuad)

        def on_fade_out_finished():
            self._text = new_text
            self._karaoke_progress = 0.0
            self.update()
            fade_in.start()

        fade_out.finished.connect(on_fade_out_finished)
        fade_out.start()

        # Keep reference to prevent garbage collection
        self._current_anim = (fade_out, fade_in)

    def set_karaoke_progress(self, progress: float):
        """Set karaoke highlighting progress (0.0 to 1.0)."""
        self._karaoke_progress = max(0.0, min(1.0, progress))
        if self._role == "current":
            self.update()

    def set_font_size(self, size: int):
        """Update the font size."""
        self._font_size = size
        self._update_font_metrics()
        self.update()

    def set_font_family(self, family: str):
        """Update the font family."""
        self._font_family = family
        self._update_font_metrics()
        self.update()

    def set_font_color(self, color: QColor):
        """Update the font color."""
        self._font_color = color
        self.update()

    def set_alignment(self, alignment: Qt.AlignmentFlag):
        """Set text alignment."""
        self._alignment = alignment
        self.update()

    def set_animations_enabled(self, enabled: bool):
        """Enable or disable animations."""
        self._animations_enabled = enabled

    def _update_font_metrics(self):
        """Recalculate minimum height based on font."""
        scale = self._get_role_font_scale()
        font = QFont(self._font_family, int(self._font_size * scale))
        font.setWeight(QFont.Weight.Bold if self._role == "current" else QFont.Weight.Normal)
        metrics = QFontMetrics(font)
        self.setMinimumHeight(metrics.height() + 12)

    def paintEvent(self, event):
        """Custom paint for the lyric text with karaoke highlighting."""
        if not self._text:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        # Configure font
        scale = self._get_role_font_scale()
        font = QFont(self._font_family, int(self._font_size * scale))
        if self._role == "current":
            font.setWeight(QFont.Weight.Bold)
        else:
            font.setWeight(QFont.Weight.Normal)
        painter.setFont(font)

        rect = self.rect().adjusted(20, 0, -20, 0)

        if self._role == "current" and self._karaoke_progress > 0.01:
            # Karaoke mode: draw highlighted portion + unhighlighted portion
            metrics = QFontMetrics(font)
            text_width = metrics.horizontalAdvance(self._text)

            # Calculate text position based on alignment
            if self._alignment == Qt.AlignmentFlag.AlignCenter:
                text_x = rect.x() + (rect.width() - text_width) // 2
            elif self._alignment == Qt.AlignmentFlag.AlignRight:
                text_x = rect.x() + rect.width() - text_width
            else:
                text_x = rect.x()

            text_y = rect.y() + (rect.height() + metrics.ascent() - metrics.descent()) // 2

            # Draw text shadow / glow
            painter.setPen(QColor(self._font_color.red(), self._font_color.green(),
                                  self._font_color.blue(), 40))
            painter.drawText(text_x + 2, text_y + 2, self._text)

            # Draw unhighlighted text (dimmed)
            dim_color = QColor(self._font_color)
            dim_color.setAlpha(100)
            painter.setPen(dim_color)
            painter.drawText(text_x, text_y, self._text)

            # Draw highlighted portion (full brightness) with clip
            highlight_width = int(text_width * self._karaoke_progress)
            painter.save()
            painter.setClipRect(text_x, 0, highlight_width, self.height())

            # Bright accent color for highlighted portion
            accent = QColor("#7C3AED")  # Purple accent
            painter.setPen(accent)
            painter.drawText(text_x, text_y, self._text)
            painter.restore()
        else:
            # Standard text rendering
            # Draw subtle text shadow for depth
            shadow_color = QColor(0, 0, 0, 80)
            painter.setPen(shadow_color)
            painter.drawText(rect.adjusted(2, 2, 2, 2),
                             self._alignment | Qt.AlignmentFlag.AlignVCenter,
                             self._text)

            # Draw main text
            painter.setPen(self._font_color)
            painter.drawText(rect,
                             self._alignment | Qt.AlignmentFlag.AlignVCenter,
                             self._text)

        painter.end()


# ──────────────────────────────────────────────────────────────
# Status Bar (bottom of overlay)
# ──────────────────────────────────────────────────────────────

class StatusBar(QWidget):
    """Small status bar showing current song info and detection status."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._text = ""
        self._font_size = 11
        self.setFixedHeight(22)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def set_text(self, text: str):
        self._text = text
        self.update()

    def paintEvent(self, event):
        if not self._text:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        font = QFont(DEFAULT_FONT_FAMILY, self._font_size)
        painter.setFont(font)
        painter.setPen(QColor(255, 255, 255, 100))
        painter.drawText(self.rect().adjusted(20, 0, -20, 0),
                         Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter,
                         self._text)
        painter.end()


# ──────────────────────────────────────────────────────────────
# Main Overlay Window
# ──────────────────────────────────────────────────────────────

class OverlayWindow(QWidget):
    """
    The main floating overlay window for displaying lyrics.
    
    Features:
        - Frameless, transparent, always-on-top
        - Glassmorphism background
        - 3-line lyric display with animations
        - Draggable (click and drag anywhere)
        - Resizable (bottom-right grip)
        - Click-through mode toggle
        - Mini mode (single line)
    
    Signals:
        visibility_changed(bool): Emitted when overlay is shown/hidden
        settings_requested: Emitted when user double-clicks overlay
    """

    visibility_changed = pyqtSignal(bool)
    settings_requested = pyqtSignal()

    def __init__(self):
        super().__init__()

        # ── Window properties ──
        self._setup_window_flags()

        # ── State ──
        self._bg_opacity = DEFAULT_BG_OPACITY
        self._corner_radius = DEFAULT_CORNER_RADIUS
        self._is_mini_mode = False
        self._click_through = False
        self._always_on_top = True
        self._dragging = False
        self._drag_position = QPoint()
        self._resizing = False
        self._resize_start = QPoint()
        self._resize_start_size = QSize()
        self._animations_enabled = True
        self._auto_hide = True
        self._is_idle = False

        # ── Layout ──
        self._setup_ui()

        # ── Position: center bottom of primary screen ──
        self._center_on_screen()

    def _setup_window_flags(self):
        """Configure window flags for floating overlay behavior."""
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool  # Don't show in taskbar
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        # Minimum and default sizes — compact to avoid being intrusive
        self.setMinimumSize(350, 100)
        self.resize(650, 180)

    def _setup_ui(self):
        """Build the lyric display layout."""
        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Container widget (for content inside the glassmorphism panel)
        self._container = QWidget(self)
        container_layout = QVBoxLayout(self._container)
        container_layout.setContentsMargins(15, 15, 15, 8)
        container_layout.setSpacing(4)

        # ── Lyric labels ──
        self._prev_label = LyricLabel("previous", self)
        self._curr_label = LyricLabel("current", self)
        self._next_label = LyricLabel("next", self)

        container_layout.addWidget(self._prev_label)
        container_layout.addWidget(self._curr_label, stretch=2)
        container_layout.addWidget(self._next_label)

        # ── Status bar ──
        self._status_bar = StatusBar(self)
        container_layout.addWidget(self._status_bar)

        main_layout.addWidget(self._container)

        # ── Resize grip (bottom-right corner) ──
        self._size_grip = QSizeGrip(self)
        self._size_grip.setFixedSize(16, 16)
        self._size_grip.setStyleSheet("background: transparent;")

    def _center_on_screen(self):
        """Position the overlay at the bottom-right of the primary screen (near tray)."""
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            x = geo.x() + geo.width() - self.width() - 20  # 20px from right edge
            y = geo.y() + geo.height() - self.height() - 20  # 20px from bottom
            self.move(x, y)

    # ──────────────────────────────────────────────────────────
    # Painting — Glassmorphism Background
    # ──────────────────────────────────────────────────────────

    def paintEvent(self, event):
        """
        Custom paint for the glassmorphism background.
        
        Draws a semi-transparent rounded rectangle with:
        - Dark background with adjustable opacity
        - Subtle gradient overlay
        - Thin border with low opacity
        - Inner shadow for depth
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()
        radius = self._corner_radius

        # ── Background path (rounded rectangle) ──
        path = QPainterPath()
        path.addRoundedRect(
            float(rect.x()), float(rect.y()),
            float(rect.width()), float(rect.height()),
            radius, radius
        )

        # ── Main background fill ──
        bg_alpha = int(self._bg_opacity * 255)
        bg_color = QColor(12, 12, 20, bg_alpha)

        # Subtle gradient (top slightly lighter)
        gradient = QLinearGradient(0, 0, 0, rect.height())
        gradient.setColorAt(0.0, QColor(25, 25, 40, bg_alpha))
        gradient.setColorAt(0.5, QColor(15, 15, 28, bg_alpha))
        gradient.setColorAt(1.0, QColor(8, 8, 16, bg_alpha))

        painter.fillPath(path, QBrush(gradient))

        # ── Border ──
        border_pen = QPen(QColor(255, 255, 255, 25), 1.0)
        painter.setPen(border_pen)
        painter.drawPath(path)

        # ── Top highlight line (glass reflection effect) ──
        highlight_path = QPainterPath()
        highlight_path.addRoundedRect(
            float(rect.x() + 1), float(rect.y() + 1),
            float(rect.width() - 2), float(rect.height() // 3),
            radius, radius
        )
        highlight_gradient = QLinearGradient(0, 0, 0, rect.height() // 3)
        highlight_gradient.setColorAt(0.0, QColor(255, 255, 255, 12))
        highlight_gradient.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.fillPath(highlight_path, QBrush(highlight_gradient))

        painter.end()

    def resizeEvent(self, event):
        """Reposition the resize grip on window resize."""
        super().resizeEvent(event)
        # Place grip at bottom-right
        self._size_grip.move(
            self.width() - self._size_grip.width(),
            self.height() - self._size_grip.height(),
        )

    # ──────────────────────────────────────────────────────────
    # Lyric Updates
    # ──────────────────────────────────────────────────────────

    def update_lyrics(self, context: LyricContext):
        """
        Update the 3-line lyrics display from a LyricContext.
        
        Args:
            context: The current lyric context from the sync engine
        """
        animate = self._animations_enabled

        # Previous line
        prev_text = context.previous.text if context.previous else ""
        self._prev_label.set_text(prev_text, animate=animate)

        # Current line
        curr_text = context.current.text if context.current else ""
        self._curr_label.set_text(curr_text, animate=animate)

        # Next line
        next_text = context.next.text if context.next else ""
        self._next_label.set_text(next_text, animate=animate)

        # Karaoke progress
        self._curr_label.set_karaoke_progress(context.progress)

        # Show overlay if hidden during auto-hide idle
        if self._is_idle and curr_text:
            self._is_idle = False
            self.show()

    def update_karaoke_progress(self, progress: float):
        """Update just the karaoke highlighting progress."""
        self._curr_label.set_karaoke_progress(progress)

    def set_status(self, text: str):
        """Update the status bar text."""
        self._status_bar.set_text(text)

    def show_idle(self):
        """Show idle state (no lyrics / waiting for music)."""
        self._curr_label.set_text("♫ Waiting for music...", animate=False)
        self._prev_label.set_text("", animate=False)
        self._next_label.set_text("", animate=False)

    def show_no_lyrics(self, title: str = "", artist: str = ""):
        """Show a message when no lyrics are found."""
        if title:
            self._curr_label.set_text(f"No lyrics found for \"{title}\"", animate=False)
        else:
            self._curr_label.set_text("No lyrics found", animate=False)
        self._prev_label.set_text("", animate=False)
        self._next_label.set_text("Try searching manually in settings", animate=False)

    def show_plain_lyrics_message(self):
        """Inform user that only plain (unsynced) lyrics are available."""
        self._prev_label.set_text("⚠ Synced lyrics not available", animate=False)

    # ──────────────────────────────────────────────────────────
    # Appearance Settings
    # ──────────────────────────────────────────────────────────

    def set_font_size(self, size: int):
        """Update font size for all lyric labels."""
        self._prev_label.set_font_size(size)
        self._curr_label.set_font_size(size)
        self._next_label.set_font_size(size)

    def set_font_family(self, family: str):
        """Update font family for all lyric labels."""
        self._prev_label.set_font_family(family)
        self._curr_label.set_font_family(family)
        self._next_label.set_font_family(family)

    def set_font_color(self, color_hex: str):
        """Update font color for all lyric labels."""
        color = QColor(color_hex)
        self._prev_label.set_font_color(color)
        self._curr_label.set_font_color(color)
        self._next_label.set_font_color(color)

    def set_bg_opacity(self, opacity: float):
        """Set background panel opacity (0.0–1.0)."""
        self._bg_opacity = max(0.0, min(1.0, opacity))
        self.update()

    def set_overlay_opacity(self, opacity: float):
        """Set overall window opacity (0.0–1.0)."""
        self.setWindowOpacity(max(0.1, min(1.0, opacity)))

    def set_alignment(self, alignment: str):
        """Set text alignment ('left', 'center', 'right')."""
        align_map = {
            "left": Qt.AlignmentFlag.AlignLeft,
            "center": Qt.AlignmentFlag.AlignCenter,
            "right": Qt.AlignmentFlag.AlignRight,
        }
        qt_align = align_map.get(alignment, Qt.AlignmentFlag.AlignCenter)
        self._prev_label.set_alignment(qt_align)
        self._curr_label.set_alignment(qt_align)
        self._next_label.set_alignment(qt_align)

    def set_animations_enabled(self, enabled: bool):
        """Enable or disable text transition animations."""
        self._animations_enabled = enabled
        self._prev_label.set_animations_enabled(enabled)
        self._curr_label.set_animations_enabled(enabled)
        self._next_label.set_animations_enabled(enabled)

    def set_always_on_top(self, enabled: bool):
        """Toggle always-on-top behavior."""
        self._always_on_top = enabled
        flags = self.windowFlags()
        if enabled:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.show()  # Required after changing window flags

    def set_auto_hide(self, enabled: bool):
        """Enable auto-hide when no music is playing."""
        self._auto_hide = enabled

    # ──────────────────────────────────────────────────────────
    # Click-through Mode (Windows-specific)
    # ──────────────────────────────────────────────────────────

    def set_click_through(self, enabled: bool):
        """
        Toggle click-through mode.
        When enabled, mouse clicks pass through the overlay to the window below.
        """
        self._click_through = enabled
        try:
            import ctypes
            from ctypes import wintypes

            hwnd = int(self.winId())
            GWL_EXSTYLE = -20
            WS_EX_TRANSPARENT = 0x00000020
            WS_EX_LAYERED = 0x00080000

            user32 = ctypes.windll.user32
            style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)

            if enabled:
                style |= WS_EX_TRANSPARENT | WS_EX_LAYERED
            else:
                style &= ~WS_EX_TRANSPARENT

            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
        except Exception as e:
            print(f"[Overlay] Click-through toggle failed: {e}")

    # ──────────────────────────────────────────────────────────
    # Mini Mode
    # ──────────────────────────────────────────────────────────

    def toggle_mini_mode(self):
        """Toggle between full 3-line and mini single-line mode."""
        self._is_mini_mode = not self._is_mini_mode

        if self._is_mini_mode:
            self._prev_label.hide()
            self._next_label.hide()
            self._status_bar.hide()
            self.setMinimumSize(300, 60)
            self.resize(600, 70)
        else:
            self._prev_label.show()
            self._next_label.show()
            self._status_bar.show()
            self.setMinimumSize(400, 120)
            self.resize(800, 220)

    # ──────────────────────────────────────────────────────────
    # Mouse Events (Drag to move)
    # ──────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        """Handle mouse press for dragging."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        """Handle mouse move for dragging."""
        if self._dragging and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_position)
            event.accept()

    def mouseReleaseEvent(self, event):
        """Handle mouse release to stop dragging."""
        self._dragging = False
        event.accept()

    def mouseDoubleClickEvent(self, event):
        """Double-click opens settings panel."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.settings_requested.emit()
            event.accept()

    # ──────────────────────────────────────────────────────────
    # Visibility Controls
    # ──────────────────────────────────────────────────────────

    def toggle_visibility(self):
        """Toggle overlay visibility."""
        if self.isVisible():
            self.hide()
            self.visibility_changed.emit(False)
        else:
            self.show()
            self.visibility_changed.emit(True)

    def show(self):
        """Show the overlay."""
        super().show()
        self.visibility_changed.emit(True)

    def hide(self):
        """Hide the overlay."""
        super().hide()
        self.visibility_changed.emit(False)

    def auto_hide_idle(self):
        """Hide overlay when no music is playing (if auto-hide enabled)."""
        if self._auto_hide:
            self._is_idle = True
            self.hide()
