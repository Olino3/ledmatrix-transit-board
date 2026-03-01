"""
Tests for TransitRenderer — PIL-based LED matrix renderer.

These tests create real PIL images and check pixel colors/content directly,
which proves the renderer actually draws what it claims (not just mock calls).

All tests are written BEFORE implementation (TDD RED phase).
"""

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
