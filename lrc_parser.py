"""
lrc_parser.py — LRC Format Parser & Sync Engine

Parses .lrc (synced lyrics) files into timestamped line objects,
and provides a sync engine to retrieve the correct lyric line
for any given playback position.

LRC format example:
    [00:12.34] First line of lyrics
    [00:15.67] Second line of lyrics
"""

import re
from dataclasses import dataclass, field
from typing import Optional


# ──────────────────────────────────────────────────────────────
# Data Classes
# ──────────────────────────────────────────────────────────────

@dataclass
class LyricLine:
    """Represents a single synced lyric line."""
    timestamp_ms: int       # Position in milliseconds
    text: str               # The lyric text
    duration_ms: int = 0    # Duration until next line (calculated after parsing)
    words: list = field(default_factory=list)  # Individual words for karaoke mode
    translation: Optional[str] = None # Translated English text (if any)


@dataclass
class LyricContext:
    """
    The 3-line context shown on the overlay:
    previous line, current line, and next line.
    """
    previous: Optional[LyricLine] = None
    current: Optional[LyricLine] = None
    next: Optional[LyricLine] = None
    current_index: int = -1
    total_lines: int = 0
    progress: float = 0.0   # 0.0–1.0 progress within current line (for karaoke)


# ──────────────────────────────────────────────────────────────
# LRC Timestamp Regex
# Supports: [mm:ss.xx], [mm:ss.xxx], [mm:ss]
# ──────────────────────────────────────────────────────────────

_LRC_TIMESTAMP_RE = re.compile(
    r'\[(\d{1,3}):(\d{2})(?:\.(\d{2,3}))?\]'
)

# Metadata tags to skip (e.g., [ar:Artist], [ti:Title])
_LRC_META_RE = re.compile(
    r'\[(ar|ti|al|au|length|by|offset|re|ve):.*\]',
    re.IGNORECASE
)


# ──────────────────────────────────────────────────────────────
# Parser
# ──────────────────────────────────────────────────────────────

def parse_lrc(lrc_text: str) -> list[LyricLine]:
    """
    Parse an LRC-format string into a sorted list of LyricLine objects.

    Handles:
        - Standard timestamps [mm:ss.xx]
        - Multiple timestamps per line [00:12.34][00:45.67] Same text
        - Metadata tags (skipped)
        - Empty lines (skipped)
        - Millisecond normalization (2-digit → ×10, 3-digit → as-is)
    
    Args:
        lrc_text: Raw LRC string content
    
    Returns:
        List of LyricLine objects sorted by timestamp
    """
    if not lrc_text or not lrc_text.strip():
        return []

    lines: list[LyricLine] = []

    for raw_line in lrc_text.strip().splitlines():
        raw_line = raw_line.strip()

        # Skip empty lines and metadata tags
        if not raw_line or _LRC_META_RE.match(raw_line):
            continue

        # Find all timestamps in this line
        timestamps = _LRC_TIMESTAMP_RE.findall(raw_line)
        if not timestamps:
            continue

        # Extract the text after all timestamp tags
        text = _LRC_TIMESTAMP_RE.sub('', raw_line).strip()
        if not text:
            continue

        # Create a LyricLine for each timestamp (handles multi-timestamp lines)
        for minutes_str, seconds_str, ms_str in timestamps:
            minutes = int(minutes_str)
            seconds = int(seconds_str)

            # Normalize milliseconds: "34" → 340ms, "345" → 345ms
            if ms_str:
                if len(ms_str) == 2:
                    milliseconds = int(ms_str) * 10
                else:
                    milliseconds = int(ms_str)
            else:
                milliseconds = 0

            timestamp_ms = (minutes * 60 + seconds) * 1000 + milliseconds

            # Split text into words for karaoke highlighting
            words = text.split()

            lines.append(LyricLine(
                timestamp_ms=timestamp_ms,
                text=text,
                words=words,
            ))

    # Sort by timestamp (important for binary search later)
    lines.sort(key=lambda l: l.timestamp_ms)

    # Calculate durations (time between consecutive lines)
    for i in range(len(lines) - 1):
        lines[i].duration_ms = lines[i + 1].timestamp_ms - lines[i].timestamp_ms

    # Last line: assume 5 seconds duration
    if lines:
        lines[-1].duration_ms = 5000

    return lines


def parse_plain_lyrics(plain_text: str) -> list[LyricLine]:
    """
    Convert plain (unsynced) lyrics into LyricLine objects.
    
    Since there are no timestamps, each line gets a sequential
    index-based timestamp with 0ms (they won't auto-scroll,
    but can still be displayed and manually navigated).
    
    Args:
        plain_text: Raw plain lyrics text
    
    Returns:
        List of LyricLine objects (all with timestamp_ms=0)
    """
    if not plain_text or not plain_text.strip():
        return []

    lines = []
    for text in plain_text.strip().splitlines():
        text = text.strip()
        if text:
            lines.append(LyricLine(
                timestamp_ms=0,
                text=text,
                words=text.split(),
            ))

    return lines


# ──────────────────────────────────────────────────────────────
# Sync Engine
# ──────────────────────────────────────────────────────────────

class SyncEngine:
    """
    Sync engine that tracks playback position and returns
    the correct lyric context (previous / current / next lines).
    
    Uses binary search for efficient lookup in large lyric files.
    """

    def __init__(self):
        self._lines: list[LyricLine] = []
        self._is_synced: bool = False
        self._last_index: int = -1  # Cache to avoid redundant updates

    def load_lyrics(self, lines: list[LyricLine], is_synced: bool = True):
        """
        Load a new set of parsed lyrics into the engine.
        
        Args:
            lines: Parsed LyricLine objects
            is_synced: True if lyrics have real timestamps (from .lrc)
        """
        self._lines = lines
        self._is_synced = is_synced
        self._last_index = -1

    def clear(self):
        """Clear all loaded lyrics."""
        self._lines = []
        self._is_synced = False
        self._last_index = -1

    @property
    def is_synced(self) -> bool:
        """Whether currently loaded lyrics are time-synced."""
        return self._is_synced

    @property
    def has_lyrics(self) -> bool:
        """Whether any lyrics are loaded."""
        return len(self._lines) > 0

    @property
    def total_lines(self) -> int:
        return len(self._lines)

    def get_context(self, position_ms: int) -> LyricContext:
        """
        Get the 3-line lyric context for a given playback position.
        
        Uses binary search to find the current line efficiently.
        
        Args:
            position_ms: Current playback position in milliseconds
        
        Returns:
            LyricContext with previous, current, and next lines
        """
        if not self._lines:
            return LyricContext()

        # For unsynced lyrics, just return the first few lines
        if not self._is_synced:
            return LyricContext(
                previous=None,
                current=self._lines[0] if self._lines else None,
                next=self._lines[1] if len(self._lines) > 1 else None,
                current_index=0,
                total_lines=len(self._lines),
                progress=0.0,
            )

        # Binary search: find the last line whose timestamp <= position_ms
        index = self._binary_search(position_ms)

        # Build the context
        ctx = LyricContext(
            current_index=index,
            total_lines=len(self._lines),
        )

        if 0 <= index < len(self._lines):
            ctx.current = self._lines[index]

            # Calculate progress within current line (for karaoke highlighting)
            if ctx.current.duration_ms > 0:
                elapsed = position_ms - ctx.current.timestamp_ms
                ctx.progress = max(0.0, min(1.0, elapsed / ctx.current.duration_ms))
            else:
                ctx.progress = 0.0

        if index > 0:
            ctx.previous = self._lines[index - 1]

        if index + 1 < len(self._lines):
            ctx.next = self._lines[index + 1]

        return ctx

    def has_line_changed(self, position_ms: int) -> bool:
        """
        Check if the current line has changed since last query.
        Useful to trigger animations only on line changes.
        """
        index = self._binary_search(position_ms)
        changed = index != self._last_index
        self._last_index = index
        return changed

    def get_line_at_index(self, index: int) -> Optional[LyricLine]:
        """Get a specific line by index (for plain lyrics scrolling)."""
        if 0 <= index < len(self._lines):
            return self._lines[index]
        return None

    def _binary_search(self, position_ms: int) -> int:
        """
        Binary search to find the index of the current lyric line.
        
        Returns the index of the last line whose timestamp_ms <= position_ms.
        Returns -1 if position is before the first line.
        """
        if not self._lines:
            return -1

        lo, hi = 0, len(self._lines) - 1

        # Before the first lyric
        if position_ms < self._lines[0].timestamp_ms:
            return -1

        # After or at the last lyric
        if position_ms >= self._lines[-1].timestamp_ms:
            return hi

        # Standard binary search
        while lo <= hi:
            mid = (lo + hi) // 2
            if self._lines[mid].timestamp_ms <= position_ms:
                # Check if next line is after position → this is our answer
                if mid + 1 < len(self._lines) and self._lines[mid + 1].timestamp_ms > position_ms:
                    return mid
                lo = mid + 1
            else:
                hi = mid - 1

        return lo
