"""
LED matrix renderer for the transit-board plugin.

Draws one DirectionGroup at a time:
  [BADGE] Direction Label
          2 min  7 min  15 min

Route badge: filled rectangle with official line color + contrasting letter.
Arrival times: green for normal, yellow/white for imminent (< threshold).
"""

import sys
from pathlib import Path
from typing import Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

from transit.models import DirectionGroup


def _find_font_dir() -> Path:
    """
    Locate the LEDMatrix assets/fonts directory.

    LEDMatrix adds its root to sys.path at startup, so we search there.
    Falls back to a sibling-directory heuristic for development.
    """
    for p in sys.path:
        candidate = Path(p) / "assets" / "fonts" / "PressStart2P-Regular.ttf"
        if candidate.exists():
            return Path(p) / "assets" / "fonts"
    # Dev fallback: plugin repo sits next to LEDMatrix/
    return Path(__file__).resolve().parent.parent.parent / "LEDMatrix" / "assets" / "fonts"


_FONT_DIR = _find_font_dir()
_FONT_NORMAL = _FONT_DIR / "PressStart2P-Regular.ttf"
_FONT_SMALL = _FONT_DIR / "4x6-font.ttf"

# Color constants
_COLOR_IMMINENT = (255, 255, 0)    # yellow — train arriving < threshold mins
_COLOR_NORMAL = (0, 255, 120)       # green — normal arrival
_COLOR_NO_DATA = (150, 150, 150)    # gray — no data
_COLOR_BLACK = (0, 0, 0)
_COLOR_WHITE = (255, 255, 255)

_IMMINENT_THRESHOLD = 2  # minutes


def _load_font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(str(path), size)
    except (IOError, OSError):
        return ImageFont.load_default()


def _contrasting_color(hex_color: str) -> Tuple[int, int, int]:
    """Return black or white depending on background luminance."""
    hex_color = hex_color.lstrip("#")
    if len(hex_color) != 6:
        return _COLOR_WHITE
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    # Relative luminance (per WCAG)
    luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return _COLOR_BLACK if luminance > 128 else _COLOR_WHITE


def _hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    hex_color = hex_color.lstrip("#")
    if len(hex_color) != 6:
        return (128, 128, 128)
    return (int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16))


class TransitRenderer:
    """
    Renders a DirectionGroup onto a PIL Image.

    The display_manager is queried for width/height to adapt layout
    to different panel sizes (32px vs 16px tall).
    """

    def __init__(self, display_manager) -> None:
        self._dm = display_manager
        self._preload_fonts()

    def _preload_fonts(self) -> None:
        h = self._dm.height
        if h >= 32:
            self._font_route = _load_font(_FONT_NORMAL, 8)
            self._font_label = _load_font(_FONT_SMALL, 6)
            self._font_time = _load_font(_FONT_SMALL, 6)
            self._badge_size = 10
        else:
            # Small display (16px tall) — use minimal fonts
            self._font_route = _load_font(_FONT_SMALL, 6)
            self._font_label = _load_font(_FONT_SMALL, 6)
            self._font_time = _load_font(_FONT_SMALL, 6)
            self._badge_size = 7

    def draw_direction_group(
        self, group: DirectionGroup, image: Image.Image
    ) -> None:
        """
        Draw route badge + direction label + arrival times onto image.

        Layout (32px display):
          Row 1-12:  [BADGE] direction_label
          Row 13-22: arrival times
        """
        draw = ImageDraw.Draw(image)
        w, h = image.size

        badge_size = self._badge_size
        badge_bg = _hex_to_rgb(group.color)
        badge_fg = _contrasting_color(group.color)

        # --- Route badge (filled rectangle) ---
        x0, y0 = 1, 1
        x1, y1 = x0 + badge_size, y0 + badge_size
        draw.rectangle([x0, y0, x1, y1], fill=badge_bg)

        # Route letter centered in badge
        letter = group.route_id[:1]
        try:
            bbox = draw.textbbox((0, 0), letter, font=self._font_route)
            lw, lh = bbox[2] - bbox[0], bbox[3] - bbox[1]
        except AttributeError:
            lw, lh = self._font_route.getsize(letter)
        lx = x0 + (badge_size - lw) // 2
        ly = y0 + (badge_size - lh) // 2
        draw.text((lx, ly), letter, font=self._font_route, fill=badge_fg)

        # --- Direction label (truncated to fit) ---
        label_x = x1 + 3
        label_y = y0 + 1
        label = group.direction_label
        max_label_w = w - label_x - 2
        # Truncate with ellipsis if needed
        while label:
            try:
                bbox = draw.textbbox((0, 0), label, font=self._font_label)
                lbl_w = bbox[2] - bbox[0]
            except AttributeError:
                lbl_w, _ = self._font_label.getsize(label)
            if lbl_w <= max_label_w:
                break
            label = label[:-1]
        draw.text((label_x, label_y), label, font=self._font_label, fill=_COLOR_WHITE)

        # --- Arrival times ---
        time_y = y1 + 3
        sorted_arrivals = sorted(group.arrivals)
        time_x = 2
        for mins in sorted_arrivals[:3]:
            color = _COLOR_IMMINENT if mins < _IMMINENT_THRESHOLD else _COLOR_NORMAL
            text = f"{mins}m"
            draw.text((time_x, time_y), text, font=self._font_time, fill=color)
            try:
                bbox = draw.textbbox((0, 0), text, font=self._font_time)
                tw = bbox[2] - bbox[0]
            except AttributeError:
                tw, _ = self._font_time.getsize(text)
            time_x += tw + 5

    def draw_no_data(self, image: Image.Image) -> None:
        """Render a 'No arrivals' placeholder screen."""
        draw = ImageDraw.Draw(image)
        w, h = image.size
        text = "No arrivals"
        try:
            bbox = draw.textbbox((0, 0), text, font=self._font_label)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        except AttributeError:
            tw, th = self._font_label.getsize(text)
        x = max(0, (w - tw) // 2)
        y = max(0, (h - th) // 2)
        draw.text((x, y), text, font=self._font_label, fill=_COLOR_NO_DATA)
