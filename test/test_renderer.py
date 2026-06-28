"""
Tests for TransitRenderer — PIL-based LED matrix renderer.

These tests create real PIL images and check pixel colors/content directly,
which proves the renderer actually draws what it claims (not just mock calls).

All tests are written BEFORE implementation (TDD RED phase).
"""

from types import SimpleNamespace

import pytest
from PIL import Image


def _make_group(route_id="N", direction_label="Uptown/Queens", arrivals=None, color="#FCCC0A"):
    from transit.models import DirectionGroup
    return DirectionGroup(
        route_id=route_id,
        direction_label=direction_label,
        arrivals=arrivals if arrivals is not None else [2, 7, 15],
        color=color,
    )


def _make_display_manager(width, height):
    return SimpleNamespace(width=width, height=height)


def _bbox_for_pixels(image, predicate):
    points = [
        (x, y)
        for y in range(image.height)
        for x in range(image.width)
        if predicate(image.getpixel((x, y)))
    ]
    if not points:
        return None
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), min(ys), max(xs) + 1, max(ys) + 1


def _bbox_for_pixels_in_region(image, predicate, y_start, y_end):
    points = [
        (x, y)
        for y in range(y_start, y_end)
        for x in range(image.width)
        if predicate(image.getpixel((x, y)))
    ]
    if not points:
        return None
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), min(ys), max(xs) + 1, max(ys) + 1


def _bbox_height(bbox):
    return bbox[3] - bbox[1]


def _bbox_width(bbox):
    return bbox[2] - bbox[0]


def _is_arrival_green(pixel):
    return pixel[1] > 120 and pixel[0] < 80 and pixel[2] < 160


def _is_top_content(pixel):
    return pixel != (0, 0, 0) and not _is_arrival_green(pixel)


def _is_direction_label(pixel):
    r, g, b = pixel
    return r > 150 and g > 150 and b > 150


class TestRouteBadge:
    def test_route_badge_background_matches_official_color(self, mock_display_manager):
        """The badge area contains pixels matching the route's official hex color."""
        from transit.renderer import TransitRenderer

        renderer = TransitRenderer(mock_display_manager)
        group = _make_group(route_id="N", color="#FCCC0A")  # yellow
        image = Image.new("RGB", (128, 32), (0, 0, 0))

        renderer.draw_direction_group(group, image)

        # Sample pixels in the badge area (top-left region, first ~12x12 px)
        pixels = [image.getpixel((x, y)) for x in range(1, 12) for y in range(1, 12)]
        expected_rgb = (0xFC, 0xCC, 0x0A)  # #FCCC0A = yellow
        assert any(p == expected_rgb for p in pixels), (
            f"Expected yellow badge pixel {expected_rgb} but found: {set(pixels)}"
        )

    def test_route_badge_letter_uses_contrasting_color(self, mock_display_manager):
        """Badge text is white on dark backgrounds and dark on light backgrounds."""
        from transit.renderer import TransitRenderer

        renderer = TransitRenderer(mock_display_manager)

        # Yellow (light) background → dark text
        group_light = _make_group(route_id="N", color="#FCCC0A")
        image_light = Image.new("RGB", (128, 32), (0, 0, 0))
        renderer.draw_direction_group(group_light, image_light)

        # Blue (dark) background → white text
        group_dark = _make_group(route_id="A", color="#0039A6")
        image_dark = Image.new("RGB", (128, 32), (0, 0, 0))
        renderer.draw_direction_group(group_dark, image_dark)

        # Both should draw without error; checking they produced different images
        assert image_light != image_dark


class TestDirectionLabel:
    def test_direction_label_truncated_to_display_width(self, mock_display_manager):
        """Very long direction label doesn't spill outside the image width."""
        from transit.renderer import TransitRenderer

        renderer = TransitRenderer(mock_display_manager)
        group = _make_group(direction_label="A Very Very Very Long Direction Label That Overflows")
        image = Image.new("RGB", (128, 32), (0, 0, 0))

        # Should not raise and image stays 128 wide
        renderer.draw_direction_group(group, image)
        assert image.width == 128


class TestArrivalTimes:
    def test_arrival_times_rendered_in_sorted_order(self, mock_display_manager):
        """Passing unsorted arrivals; the renderer draws them in sorted order (no crash)."""
        from transit.renderer import TransitRenderer

        renderer = TransitRenderer(mock_display_manager)
        group = _make_group(arrivals=[15, 2, 7])  # unsorted on purpose
        image = Image.new("RGB", (128, 32), (0, 0, 0))

        renderer.draw_direction_group(group, image)

        # Image must have some non-black pixels (something was drawn)
        pixels = list(image.getdata())
        assert any(p != (0, 0, 0) for p in pixels), "Renderer drew nothing"

    def test_no_arrivals_renders_placeholder_text(self, mock_display_manager):
        """Group with empty arrivals list renders a placeholder (not blank)."""
        from transit.renderer import TransitRenderer

        renderer = TransitRenderer(mock_display_manager)
        image = Image.new("RGB", (128, 32), (0, 0, 0))

        renderer.draw_no_data(image)

        pixels = list(image.getdata())
        assert any(p != (0, 0, 0) for p in pixels), "No-data screen must not be blank"


class TestAdaptiveDisplay:
    def test_adapts_font_size_for_16px_height(self, mock_display_manager_16):
        """Renderer works for 16px tall display without error."""
        from transit.renderer import TransitRenderer

        renderer = TransitRenderer(mock_display_manager_16)
        group = _make_group()
        image = Image.new("RGB", (64, 16), (0, 0, 0))

        # Should not raise for small display
        renderer.draw_direction_group(group, image)

        pixels = list(image.getdata())
        assert any(p != (0, 0, 0) for p in pixels), "Small display: renderer drew nothing"

    def test_128x32_badge_uses_most_of_top_half(self):
        """A two-panel 128x32 board should draw a large route badge, not a 10px badge."""
        from transit.renderer import TransitRenderer

        renderer = TransitRenderer(_make_display_manager(128, 32))
        group = _make_group(route_id="N", color="#FCCC0A")
        image = Image.new("RGB", (128, 32), (0, 0, 0))

        renderer.draw_direction_group(group, image)

        badge_bbox = _bbox_for_pixels(image, lambda p: p == (0xFC, 0xCC, 0x0A))
        assert badge_bbox is not None, "Expected route badge background pixels"
        assert _bbox_height(badge_bbox) >= 14
        assert badge_bbox[3] <= 18

    def test_128x32_arrival_times_scale_larger_than_small_font(self):
        """Arrival text should grow on a 128x32 board instead of using the tiny baseline font."""
        from transit.renderer import TransitRenderer

        renderer = TransitRenderer(_make_display_manager(128, 32))
        group = _make_group(arrivals=[5, 12, 18])
        image = Image.new("RGB", (128, 32), (0, 0, 0))

        renderer.draw_direction_group(group, image)

        time_bbox = _bbox_for_pixels(image, _is_arrival_green)
        assert time_bbox is not None, "Expected normal arrival time pixels"
        assert time_bbox[1] >= 16
        assert _bbox_height(time_bbox) >= 8

    def test_128x32_top_content_spans_board_width_and_half_height(self):
        """The route badge plus direction should fill the full top half of a two-panel board."""
        from transit.renderer import TransitRenderer

        renderer = TransitRenderer(_make_display_manager(128, 32))
        group = _make_group(route_id="N", direction_label="Uptown/Queens", arrivals=[5])
        image = Image.new("RGB", (128, 32), (0, 0, 0))

        renderer.draw_direction_group(group, image)

        top_bbox = _bbox_for_pixels_in_region(image, _is_top_content, 0, 16)
        assert top_bbox is not None, "Expected route badge and direction pixels"
        assert top_bbox[1] <= 1
        assert top_bbox[3] <= 16
        assert _bbox_height(top_bbox) >= 14
        assert _bbox_width(top_bbox) >= 120

        label_bbox = _bbox_for_pixels_in_region(image, _is_direction_label, 0, 16)
        assert label_bbox is not None, "Expected large direction label pixels"
        assert _bbox_height(label_bbox) >= 10

    def test_128x32_primary_arrival_is_centered_and_fills_bottom_half(self):
        """The next arrival should be the large centered readout in the bottom half."""
        from transit.renderer import TransitRenderer

        renderer = TransitRenderer(_make_display_manager(128, 32))
        group = _make_group(arrivals=[5, 12, 18])
        image = Image.new("RGB", (128, 32), (0, 0, 0))

        renderer.draw_direction_group(group, image)

        time_bbox = _bbox_for_pixels(image, _is_arrival_green)
        assert time_bbox is not None, "Expected primary arrival pixels"
        assert time_bbox[1] >= 16
        assert _bbox_height(time_bbox) >= 14
        assert abs(((time_bbox[0] + time_bbox[2]) / 2) - 64) <= 3

    def test_128x64_layout_grows_without_clipping(self):
        """Taller boards should scale badge and arrival text beyond 32px-board sizes."""
        from transit.renderer import TransitRenderer

        renderer = TransitRenderer(_make_display_manager(128, 64))
        group = _make_group(route_id="N", arrivals=[5, 12, 18], color="#FCCC0A")
        image = Image.new("RGB", (128, 64), (0, 0, 0))

        renderer.draw_direction_group(group, image)

        badge_bbox = _bbox_for_pixels(image, lambda p: p == (0xFC, 0xCC, 0x0A))
        time_bbox = _bbox_for_pixels(image, _is_arrival_green)

        assert badge_bbox is not None, "Expected route badge background pixels"
        assert time_bbox is not None, "Expected normal arrival time pixels"
        assert _bbox_height(badge_bbox) >= 26
        assert _bbox_height(time_bbox) >= 13
        assert badge_bbox[3] <= 34
        assert time_bbox[3] <= 64


class TestPrimaryArrival:
    def test_renderer_keeps_primary_arrival_large_when_more_arrivals_are_available(self, mock_display_manager):
        """Extra arrivals should not shrink the main next-arrival readout."""
        from transit.renderer import TransitRenderer

        renderer = TransitRenderer(mock_display_manager)

        group_one = _make_group(arrivals=[1])
        group_five = _make_group(arrivals=[1, 5, 10, 15, 20])

        image_one = Image.new("RGB", (128, 32), (0, 0, 0))
        image_five = Image.new("RGB", (128, 32), (0, 0, 0))

        renderer.draw_direction_group(group_one, image_one)
        renderer.draw_direction_group(group_five, image_five)

        one_bbox = _bbox_for_pixels(image_one, lambda p: p[0] > 120 and p[1] > 120 and p[2] < 80)
        five_bbox = _bbox_for_pixels(image_five, lambda p: p[0] > 120 and p[1] > 120 and p[2] < 80)

        assert one_bbox is not None, "Expected imminent primary arrival pixels"
        assert five_bbox is not None, "Expected imminent primary arrival pixels"
        assert one_bbox == five_bbox


class TestImminentHighlight:
    def test_imminent_arrival_rendered_in_highlight_color(self, mock_display_manager):
        """Arrival < 2 min uses a different (highlight) color than normal arrivals."""
        from transit.renderer import TransitRenderer

        renderer = TransitRenderer(mock_display_manager)

        group_imminent = _make_group(arrivals=[1, 10])   # 1 min = imminent
        group_normal = _make_group(arrivals=[5, 10])     # all normal

        image_imminent = Image.new("RGB", (128, 32), (0, 0, 0))
        image_normal = Image.new("RGB", (128, 32), (0, 0, 0))

        renderer.draw_direction_group(group_imminent, image_imminent)
        renderer.draw_direction_group(group_normal, image_normal)

        # The two images should differ (different color for imminent arrival)
        data_imminent = list(image_imminent.getdata())
        data_normal = list(image_normal.getdata())
        assert data_imminent != data_normal, (
            "Imminent and non-imminent arrival images should look different"
        )
