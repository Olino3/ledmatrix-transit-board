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

_IMMINENT_THRESHOLD_DEFAULT = 2  # minutes — used when no config value is available


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
        # Badge ~30% of display height, proportional across all sizes (7–48px)
        self._badge_size = max(7, min(48, round(h * 0.30)))
        bs = self._badge_size
        route_size = max(6, bs - 2)       # letter fills most of badge
        text_size = max(6, bs // 2)       # label and time text ~half badge height
        # Switch to the scalable font once text is large enough to benefit
        text_font = _FONT_NORMAL if text_size >= 8 else _FONT_SMALL
        self._font_route = _load_font(_FONT_NORMAL, route_size)
        self._font_label = _load_font(text_font, text_size)
        self._font_time = _load_font(text_font, text_size)

    def draw_direction_group(
        self,
        group: DirectionGroup,
        image: Image.Image,
        imminent_threshold: int = _IMMINENT_THRESHOLD_DEFAULT,
    ) -> None:
        """
        Draw route badge + direction label + arrival times onto image.

        Layout (32px display):
          Row 1-12:  [BADGE] direction_label
          Row 13-22: arrival times

        Args:
            imminent_threshold: Minutes below which an arrival is highlighted in
                yellow. Should match live_threshold_mins from plugin config.
        """
        draw = ImageDraw.Draw(image)
        w, h = image.size

        bs = self._badge_size
        # Scale factor relative to the baseline 10px badge (32px display)
        scale = bs / 10.0
        margin = max(1, round(scale))

        badge_bg = _hex_to_rgb(group.color)
        badge_fg = _contrasting_color(group.color)

        # --- Route badge (filled circle) ---
        x0, y0 = margin, margin
        x1, y1 = x0 + bs, y0 + bs
        draw.ellipse([x0, y0, x1, y1], fill=badge_bg)

        # Route letter centered at the circle's midpoint using PIL's "mm" anchor,
        # which positions the text by its visual middle rather than bounding-box corner.
        letter = group.route_id[:1]
        cx = x0 + bs // 2
        cy = y0 + bs // 2
        try:
            draw.text((cx, cy), letter, font=self._font_route, anchor="mm", fill=badge_fg)
        except TypeError:
            # Pillow < 8.0: fall back to manual bbox centering
            try:
                bbox = draw.textbbox((0, 0), letter, font=self._font_route)
                lw, lh = bbox[2] - bbox[0], bbox[3] - bbox[1]
            except AttributeError:
                lw, lh = self._font_route.getsize(letter)
            draw.text((cx - lw // 2, cy - lh // 2), letter, font=self._font_route, fill=badge_fg)

        # --- Direction label (truncated to fit, vertically aligned with badge center) ---
        label_x = x1 + max(2, round(3 * scale))
        label = group.direction_label
        max_label_w = w - label_x - margin
        while label:
            try:
                bbox = draw.textbbox((0, 0), label, font=self._font_label)
                lbl_w = bbox[2] - bbox[0]
            except AttributeError:
                lbl_w, _ = self._font_label.getsize(label)
            if lbl_w <= max_label_w:
                break
            label = label[:-1]
        try:
            draw.text((label_x, cy), label, font=self._font_label, anchor="lm", fill=_COLOR_WHITE)
        except TypeError:
            # Pillow < 8.0: offset by half the text height
            try:
                bbox = draw.textbbox((0, 0), label, font=self._font_label)
                lh = bbox[3] - bbox[1]
            except AttributeError:
                _, lh = self._font_label.getsize(label)
            draw.text((label_x, cy - lh // 2), label, font=self._font_label, fill=_COLOR_WHITE)

        # --- Arrival times ---
        time_gap = max(3, round(5 * scale))
        sorted_arrivals = sorted(group.arrivals)[:3]
        time_texts = [f"{mins}m" for mins in sorted_arrivals]

        # Measure all labels to center them and anchor vertically
        time_widths = []
        font_bottom = 6  # fallback
        for text in time_texts:
            try:
                bbox = draw.textbbox((0, 0), text, font=self._font_time)
                time_widths.append(bbox[2] - bbox[0])
                font_bottom = bbox[3]
            except AttributeError:
                tw, th = self._font_time.getsize(text)
                time_widths.append(tw)
                font_bottom = th

        total_w = sum(time_widths) + time_gap * max(0, len(time_widths) - 1)
        time_x = (w - total_w) // 2
        time_y = h - font_bottom - margin  # margin scales with display size

        for mins, text, tw in zip(sorted_arrivals, time_texts, time_widths):
            color = _COLOR_IMMINENT if mins < imminent_threshold else _COLOR_NORMAL
            draw.text((time_x, time_y), text, font=self._font_time, fill=color)
            time_x += tw + time_gap

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
