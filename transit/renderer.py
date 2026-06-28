"""
LED matrix renderer for the transit-board plugin.

Draws one DirectionGroup at a time:
  [BADGE] Direction Label
          2 min  7 min  15 min

Route badge: filled circle with official line color + contrasting letter.
Arrival times: green for normal, yellow/white for imminent (< threshold).
"""

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple

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
_FONT_PIXEL = _FONT_DIR / "5by7.regular.ttf"

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
        try:
            return ImageFont.truetype("DejaVuSans.ttf", size)
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


@dataclass(frozen=True)
class _TextRun:
    text: str
    width: int
    height: int
    bbox: Tuple[int, int, int, int]


@dataclass(frozen=True)
class _Layout:
    margin: int
    top_h: int
    divider_y: int
    bottom_y: int
    badge_size: int
    badge_xy: Tuple[int, int]
    label_x: int
    label_cy: int
    label_max_w: int
    label_max_h: int
    time_y: int
    time_gap: int
    time_max_w: int
    route_font: ImageFont.ImageFont
    label_font: ImageFont.ImageFont
    time_font: ImageFont.ImageFont


class TransitRenderer:
    """
    Renders a DirectionGroup onto a PIL Image.

    The public constructor accepts the display manager for compatibility with
    the plugin, while each draw call adapts to the target image dimensions.
    """

    def __init__(self, display_manager) -> None:
        self._font_cache: dict = {}

    def _font(self, path: Path, size: int) -> ImageFont.ImageFont:
        key = (str(path), size)
        if key not in self._font_cache:
            self._font_cache[key] = _load_font(path, size)
        return self._font_cache[key]

    @staticmethod
    def _measure(draw: ImageDraw.ImageDraw, font: ImageFont.ImageFont, text: str) -> _TextRun:
        try:
            bbox = draw.textbbox((0, 0), text, font=font)
            return _TextRun(text, bbox[2] - bbox[0], bbox[3] - bbox[1], bbox)
        except AttributeError:
            width, height = font.getsize(text)
            return _TextRun(text, width, height, (0, 0, width, height))

    @staticmethod
    def _text_pos_for_center(run: _TextRun, cx: int, cy: int) -> Tuple[int, int]:
        x = cx - (run.bbox[0] + run.bbox[2]) // 2
        y = cy - (run.bbox[1] + run.bbox[3]) // 2
        return x, y

    @staticmethod
    def _text_pos_for_left_center(run: _TextRun, x: int, cy: int) -> Tuple[int, int]:
        y = cy - (run.bbox[1] + run.bbox[3]) // 2
        return x, y

    def _text_font_for_size(self, size: int) -> ImageFont.ImageFont:
        path = _FONT_PIXEL if size >= 8 else _FONT_SMALL
        return self._font(path, size)

    def _text_image(
        self,
        font: ImageFont.ImageFont,
        text: str,
        fill: Tuple[int, int, int],
        weight: int = 0,
    ) -> Image.Image:
        tmp = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
        draw = ImageDraw.Draw(tmp)
        run = self._measure(draw, font, text)
        image = Image.new("RGBA", (max(1, run.width + weight), max(1, run.height)), (0, 0, 0, 0))
        image_draw = ImageDraw.Draw(image)
        for dx in range(weight + 1):
            image_draw.text((dx - run.bbox[0], -run.bbox[1]), text, font=font, fill=(*fill, 255))
        return image

    def _paste_fitted_text(
        self,
        image: Image.Image,
        font: ImageFont.ImageFont,
        text: str,
        xy: Tuple[int, int],
        fill: Tuple[int, int, int],
        max_width: int,
        weight: int = 0,
    ) -> Tuple[int, int]:
        text_image = self._text_image(font, text, fill, weight=weight)
        if text_image.width > max_width:
            text_image = text_image.resize((max(1, max_width), text_image.height), Image.Resampling.NEAREST)
        image.paste(text_image, xy, text_image)
        return text_image.size

    def _fit_label_font(
        self,
        draw: ImageDraw.ImageDraw,
        label: str,
        max_width: int,
        max_height: int,
    ) -> ImageFont.ImageFont:
        min_size = 6
        max_size = max(min_size, min(48, round(max_height * 0.85)))
        for size in range(max_size, min_size - 1, -1):
            font = self._text_font_for_size(size)
            measured = self._measure(draw, font, label or "M")
            if measured.height <= max_height and measured.width <= max_width:
                return font
        return self._text_font_for_size(min_size)

    def _fit_time_font(
        self,
        draw: ImageDraw.ImageDraw,
        time_texts: list,
        max_width: int,
        max_height: int,
    ) -> Tuple[ImageFont.ImageFont, int]:
        min_size = 6
        max_size = max(min_size, min(64, round(max_height * 0.75)))
        if not time_texts:
            return self._text_font_for_size(min_size), 0

        for size in range(max_size, min_size - 1, -1):
            font = self._text_font_for_size(size)
            runs = [self._measure(draw, font, text) for text in time_texts]
            max_h = max(run.height for run in runs)
            if max_h > max_height:
                continue
            natural_gap = max(2, round(size * 0.45))
            for gap in range(natural_gap, 0, -1):
                total_w = sum(run.width for run in runs) + gap * max(0, len(runs) - 1)
                if total_w <= max_width:
                    return font, gap
        return self._text_font_for_size(min_size), 1

    def _compute_layout(
        self,
        draw: ImageDraw.ImageDraw,
        width: int,
        height: int,
        label: str,
        time_texts: list,
    ) -> _Layout:
        divider_y = max(6, (height // 2) - 1)
        top_h = divider_y
        bottom_y = min(height, divider_y + 1)
        bottom_h = max(0, height - bottom_y)
        margin = max(1, round(min(width, height) * 0.03))

        badge_size = max(6, min(48, top_h - margin))
        badge_size = min(badge_size, max(1, width // 3))
        badge_x = margin
        badge_y = max(0, (top_h - badge_size) // 2)

        gap = max(2, round(badge_size * 0.22))
        label_x = badge_x + badge_size + gap
        label_right_margin = max(4, round(width * 0.035))
        label_max_w = max(1, width - label_x - label_right_margin)
        label_max_h = max(1, top_h - (2 * margin))
        label_font = self._fit_label_font(draw, label, label_max_w, label_max_h)

        time_max_w = max(1, width - (2 * margin))
        time_max_h = max(1, bottom_h)
        time_font, time_gap = self._fit_time_font(draw, time_texts, time_max_w, time_max_h)
        time_runs = [self._measure(draw, time_font, text) for text in time_texts]
        tallest_time = max((run.height for run in time_runs), default=0)
        time_y = bottom_y + max(0, (bottom_h - tallest_time) // 2)

        return _Layout(
            margin=margin,
            top_h=top_h,
            divider_y=divider_y,
            bottom_y=bottom_y,
            badge_size=badge_size,
            badge_xy=(badge_x, badge_y),
            label_x=label_x,
            label_cy=badge_y + badge_size // 2,
            label_max_w=label_max_w,
            label_max_h=label_max_h,
            time_y=time_y,
            time_gap=time_gap,
            time_max_w=time_max_w,
            route_font=self._font(_FONT_PIXEL, max(6, round(badge_size * 0.75))),
            label_font=label_font,
            time_font=time_font,
        )

    def draw_direction_group(
        self,
        group: DirectionGroup,
        image: Image.Image,
        imminent_threshold: int = _IMMINENT_THRESHOLD_DEFAULT,
    ) -> None:
        """
        Draw route badge + direction label + arrival times onto image.

        Layout:
          Top half:     [BADGE] direction_label
          Bottom half:  arrival times

        Args:
            imminent_threshold: Minutes below which an arrival is highlighted in
                yellow. Should match live_threshold_mins from plugin config.
        """
        draw = ImageDraw.Draw(image)
        w, h = image.size

        badge_bg = _hex_to_rgb(group.color)
        badge_fg = _contrasting_color(group.color)
        sorted_arrivals = sorted(group.arrivals)
        time_texts = [f"{mins}m" for mins in sorted_arrivals]
        layout = self._compute_layout(draw, w, h, group.direction_label, time_texts)
        bs = layout.badge_size

        draw.line((0, layout.divider_y, w, layout.divider_y), fill=(50, 80, 110))

        # --- Route badge (filled circle) ---
        x0, y0 = layout.badge_xy
        x1, y1 = x0 + bs - 1, y0 + bs - 1
        draw.ellipse([x0, y0, x1, y1], fill=badge_bg)

        # Route letter centered at circle midpoint using actual ink pixel bounds.
        letter = group.route_id[:1]
        cx = x0 + bs // 2
        cy = y0 + bs // 2
        route_run = self._measure(draw, layout.route_font, letter)
        draw.text(
            self._text_pos_for_center(route_run, cx, cy),
            letter,
            font=layout.route_font,
            fill=badge_fg,
        )

        # --- Direction label (fit full text; compress only if physically necessary) ---
        label = group.direction_label
        if label:
            label_run = self._measure(draw, layout.label_font, label)
            label_x, label_y = self._text_pos_for_left_center(label_run, layout.label_x, layout.label_cy)
            self._paste_fitted_text(
                image,
                layout.label_font,
                label,
                (label_x, label_y),
                (210, 232, 255),
                layout.label_max_w,
                weight=1,
            )

        # --- Arrival times ---
        time_runs = [self._measure(draw, layout.time_font, text) for text in time_texts]
        total_w = sum(run.width for run in time_runs) + layout.time_gap * max(0, len(time_runs) - 1)
        row_scale_w = min(total_w, layout.time_max_w)
        row = Image.new("RGBA", (max(1, total_w), max(1, max((r.height for r in time_runs), default=1))), (0, 0, 0, 0))
        row_draw = ImageDraw.Draw(row)
        row_x = 0

        for mins, run in zip(sorted_arrivals, time_runs):
            color = _COLOR_IMMINENT if mins < imminent_threshold else _COLOR_NORMAL
            row_draw.text(
                (row_x - run.bbox[0], -run.bbox[1]),
                run.text,
                font=layout.time_font,
                fill=(*color, 255),
            )
            row_x += run.width + layout.time_gap
        if row.width > row_scale_w:
            row = row.resize((max(1, row_scale_w), row.height), Image.Resampling.NEAREST)
        time_x = (w - row.width) // 2
        image.paste(row, (time_x, layout.time_y), row)

    def draw_slide_transition(
        self,
        old_group: DirectionGroup,
        new_group: DirectionGroup,
        image: Image.Image,
        progress: float,
        imminent_threshold: int = _IMMINENT_THRESHOLD_DEFAULT,
    ) -> None:
        """Draw one slide-down transition frame between two direction groups."""
        w, h = image.size
        old_image = Image.new("RGB", (w, h), _COLOR_BLACK)
        new_image = Image.new("RGB", (w, h), _COLOR_BLACK)
        self.draw_direction_group(old_group, old_image, imminent_threshold=imminent_threshold)
        self.draw_direction_group(new_group, new_image, imminent_threshold=imminent_threshold)

        offset = max(0, min(h, round(h * progress)))
        image.paste(_COLOR_BLACK, (0, 0, w, h))
        if offset < h:
            image.paste(old_image.crop((0, 0, w, h - offset)), (0, offset))
        if offset > 0:
            image.paste(new_image.crop((0, h - offset, w, h)), (0, 0))

    def draw_no_data(self, image: Image.Image) -> None:
        """Render a 'No arrivals' placeholder screen."""
        draw = ImageDraw.Draw(image)
        w, h = image.size
        text = "No arrivals"
        font = self._fit_label_font(draw, text, max(1, w - 2), max(1, h - 2))
        run = self._measure(draw, font, text)
        x = max(0, (w - run.width) // 2)
        y = max(0, (h - run.height) // 2 - run.bbox[1])
        draw.text((x, y), text, font=font, fill=_COLOR_NO_DATA)
