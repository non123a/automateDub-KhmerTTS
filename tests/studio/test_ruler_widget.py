from __future__ import annotations

from automatedub_studio.timeline.ruler_widget import (
    DEFAULT_SNAP_INTERVAL_MS,
    TimelineRulerWidget,
    format_timestamp,
    generate_ruler_ticks,
    minor_tick_interval_ms,
    snap_offset,
)
from automatedub_studio.timeline.timeline_widget import BASE_PIXELS_PER_SECOND, TimelineWidget


def test_format_timestamp_uses_minutes_and_seconds():
    assert format_timestamp(0) == "00:00"
    assert format_timestamp(1000) == "00:01"
    assert format_timestamp(62_000) == "01:02"


def test_format_timestamp_uses_hours_after_one_hour():
    assert format_timestamp(3_661_000) == "01:01:01"


def test_generate_ruler_ticks_has_major_ticks_every_second():
    ticks = generate_ruler_ticks(
        duration_ms=3_000,
        zoom=1.0,
        pixels_per_second=BASE_PIXELS_PER_SECOND,
    )
    major_times = [tick.time_ms for tick in ticks if tick.major]

    assert major_times == [0, 1000, 2000, 3000]


def test_generate_ruler_ticks_has_minor_ticks_at_100ms_when_zoom_allows():
    ticks = generate_ruler_ticks(
        duration_ms=1_000,
        zoom=1.0,
        pixels_per_second=BASE_PIXELS_PER_SECOND,
    )
    minor_times = [tick.time_ms for tick in ticks if not tick.major]

    assert minor_times[:9] == [100, 200, 300, 400, 500, 600, 700, 800, 900]


def test_minor_tick_interval_grows_when_zoomed_out():
    normal = minor_tick_interval_ms(1.0, BASE_PIXELS_PER_SECOND)
    zoomed_out = minor_tick_interval_ms(0.05, BASE_PIXELS_PER_SECOND)

    assert normal == DEFAULT_SNAP_INTERVAL_MS
    assert zoomed_out > normal


def test_generate_ruler_ticks_uses_zoom_dependent_minor_spacing():
    normal_ticks = generate_ruler_ticks(1_000, 1.0, BASE_PIXELS_PER_SECOND)
    zoomed_out_ticks = generate_ruler_ticks(1_000, 0.05, BASE_PIXELS_PER_SECOND)

    normal_minor_count = len([tick for tick in normal_ticks if not tick.major])
    zoomed_out_minor_count = len([tick for tick in zoomed_out_ticks if not tick.major])
    assert zoomed_out_minor_count < normal_minor_count


def test_ruler_position_to_time_accounts_for_origin_scroll_and_zoom(qapp):
    ruler = TimelineRulerWidget(
        pixels_per_second=BASE_PIXELS_PER_SECOND,
        time_origin_x=100,
    )
    ruler.set_zoom(2.0)
    ruler.set_scroll_value(50)

    assert ruler._position_to_time_ms(350) == 1000


def test_snap_offset_rounds_to_default_100ms_interval():
    assert snap_offset(0) == 0
    assert snap_offset(49) == 0
    assert snap_offset(50) == 100
    assert snap_offset(149) == 100
    assert snap_offset(150) == 200
    assert snap_offset(-49) == 0
    assert snap_offset(-51) == -100


def test_timeline_snap_disabled_keeps_pixel_accurate_offset(qapp):
    widget = TimelineWidget()
    widget.set_snap_enabled(False)
    widget._view._drag_start_offset_ms = 0

    assert widget._view._offset_for_drag_delta(153) == 153


def test_timeline_snap_enabled_uses_grid_interval(qapp):
    widget = TimelineWidget()
    widget.set_snap_enabled(True)
    widget._view._drag_start_offset_ms = 0

    assert widget._view._offset_for_drag_delta(153) == 200
