from available_tools.test_tools.test_ut_log.t_test_ins_status_ins_monitor_log import (
    INS1MSG_PATTERN,
    InsStatusData,
    compute_ins_message_time_diff_stats,
    group_consecutive_status_spans,
    parse_ins_status_data_from_line,
)


SAMPLE_LINE = "[2026-05-07 03:01:25.130], INS1Msg, TimeOfWeek[356501.012s], LLA[0.0000000, 0.0000000, 0.000], Roll[0.84], Pitch[-0.12], Yaw[-91.90], Yaw (with offset)[-91.9], insStatus[0x470800], hdwStatus[0x32080050], Velocity U,V,W[0.00, 0.00, 0.00, NED: 0.00, 0.00, -0.00]"


def test_parse_ins_status_data_from_line():
    result = parse_ins_status_data_from_line(SAMPLE_LINE)
    assert result is not None
    assert result.status == 0x470800
    assert result.timestamp.year == 2026
    assert result.timestamp.month == 5
    assert result.timestamp.day == 7
    assert result.timestamp.hour == 3
    assert result.timestamp.minute == 1
    assert result.timestamp.second == 25
    assert result.timestamp.microsecond == 130000


def test_parse_ins_status_data_from_line_no_match():
    assert parse_ins_status_data_from_line("some random line") is None
    assert parse_ins_status_data_from_line("") is None


def test_parse_ins_status_data_from_line_status_hex():
    result = parse_ins_status_data_from_line("[2026-01-01 00:00:00.000], insStatus[0xABCD]")
    assert result is not None
    assert result.status == 0xABCD


def test_group_consecutive_status_spans_single_status():
    from datetime import datetime

    ts = datetime(2026, 5, 7, 3, 1, 25, 130000)
    ts2 = datetime(2026, 5, 7, 3, 1, 25, 230000)
    status_entries = [InsStatusData(timestamp=ts, status=0x470800), InsStatusData(timestamp=ts2, status=0x470800)]
    status_spans = group_consecutive_status_spans(status_entries)
    assert len(status_spans) == 1
    span = status_spans[0]
    assert span.start_time == ts
    assert span.end_time == ts2
    assert span.message_count == 2
    assert span.start_offset == 0
    assert span.status == 0x470800


def test_group_consecutive_status_spans_two_statuses():
    from datetime import datetime

    ts_a = datetime(2026, 5, 7, 3, 1, 25, 130000)
    ts_b = datetime(2026, 5, 7, 3, 1, 26, 0)
    ts_c = datetime(2026, 5, 7, 3, 1, 27, 0)
    status_entries = [InsStatusData(timestamp=ts_a, status=0x470800), InsStatusData(timestamp=ts_b, status=0x123456), InsStatusData(timestamp=ts_c, status=0x123456)]
    status_spans = group_consecutive_status_spans(status_entries)
    assert len(status_spans) == 2
    assert status_spans[0].status == 0x470800
    assert status_spans[1].status == 0x123456
    assert status_spans[0].message_count == 1
    assert status_spans[1].message_count == 2


def test_group_consecutive_status_spans_interleaved():
    from datetime import datetime

    ts_a = datetime(2026, 5, 7, 3, 0, 0, 0)
    ts_b = datetime(2026, 5, 7, 3, 0, 1, 0)
    ts_c = datetime(2026, 5, 7, 3, 0, 2, 0)
    ts_d = datetime(2026, 5, 7, 3, 0, 3, 0)
    status_entries = [
        InsStatusData(timestamp=ts_a, status=0x1),
        InsStatusData(timestamp=ts_b, status=0x2),
        InsStatusData(timestamp=ts_c, status=0x1),
        InsStatusData(timestamp=ts_d, status=0x1),
    ]
    status_spans = group_consecutive_status_spans(status_entries)
    assert len(status_spans) == 3
    assert status_spans[0].status == 0x1
    assert status_spans[1].status == 0x2
    assert status_spans[2].status == 0x1
    assert status_spans[0].message_count == 1
    assert status_spans[1].message_count == 1
    assert status_spans[2].message_count == 2


def test_compute_message_time_diff_stats_empty():
    stats = compute_ins_message_time_diff_stats([])
    assert stats is None


def test_compute_message_time_diff_stats_single():
    from datetime import datetime

    stats = compute_ins_message_time_diff_stats([InsStatusData(timestamp=datetime(2026, 1, 1), status=0)])
    assert stats is None


def test_compute_message_time_diff_stats_multiple():
    from datetime import datetime

    status_entries = [
        InsStatusData(timestamp=datetime(2026, 1, 1, 0, 0, 0), status=0),
        InsStatusData(timestamp=datetime(2026, 1, 1, 0, 0, 1), status=0),
        InsStatusData(timestamp=datetime(2026, 1, 1, 0, 0, 3), status=0),
        InsStatusData(timestamp=datetime(2026, 1, 1, 0, 0, 7), status=0),
    ]
    stats = compute_ins_message_time_diff_stats(status_entries)
    assert stats is not None
    assert stats.min_secs == 1.0
    assert stats.max_secs == 4.0
    assert stats.count == 3
    assert abs(stats.avg_secs - 2.33333) < 0.001
    assert stats.median_secs == 2.0


def test_ins1msg_pattern():
    m = INS1MSG_PATTERN.search(SAMPLE_LINE)
    assert m is not None
    assert m.group("timestamp") == "2026-05-07 03:01:25.130"
    assert m.group("status") == "0x470800"


def test_ins1msg_pattern_no_match():
    assert INS1MSG_PATTERN.search("no status here") is None
    assert INS1MSG_PATTERN.search("insStatus_without_brackets") is None
