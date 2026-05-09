from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[2]))

from local_tools.available_tools.test_tools.test_ut_log.t_test_ins_status_ins_monitor_log import (
    INS1MSG_PATTERN,
    compute_time_diff_stats,
    group_statuses,
    parse_ins1msg_line,
)


SAMPLE_LINE = "[2026-05-07 03:01:25.130], INS1Msg, TimeOfWeek[356501.012s], LLA[0.0000000, 0.0000000, 0.000], Roll[0.84], Pitch[-0.12], Yaw[-91.90], Yaw (with offset)[-91.9], insStatus[0x470800], hdwStatus[0x32080050], Velocity U,V,W[0.00, 0.00, 0.00, NED: 0.00, 0.00, -0.00]"


def test_parse_ins1msg_line():
    result = parse_ins1msg_line(SAMPLE_LINE)
    assert result is not None
    ts, status = result
    assert status == 0x470800
    assert ts.year == 2026
    assert ts.month == 5
    assert ts.day == 7
    assert ts.hour == 3
    assert ts.minute == 1
    assert ts.second == 25
    assert ts.microsecond == 130000


def test_parse_ins1msg_line_no_match():
    assert parse_ins1msg_line("some random line") is None
    assert parse_ins1msg_line("") is None


def test_parse_ins1msg_line_status_hex():
    result = parse_ins1msg_line("[2026-01-01 00:00:00.000], insStatus[0xABCD]")
    assert result is not None
    _, status = result
    assert status == 0xABCD


def test_group_statuses_single_status():
    from datetime import datetime

    ts = datetime(2026, 5, 7, 3, 1, 25, 130000)
    ts2 = datetime(2026, 5, 7, 3, 1, 25, 230000)
    parsed = [(ts, 0x470800), (ts2, 0x470800)]
    grouped = group_statuses(parsed)
    assert len(grouped) == 1
    start, end, count, offset, status = grouped[0]
    assert start == ts
    assert end == ts2
    assert count == 2
    assert offset == 0
    assert status == 0x470800


def test_group_statuses_two_statuses():
    from datetime import datetime

    ts_a = datetime(2026, 5, 7, 3, 1, 25, 130000)
    ts_b = datetime(2026, 5, 7, 3, 1, 26, 0)
    ts_c = datetime(2026, 5, 7, 3, 1, 27, 0)
    parsed = [(ts_a, 0x470800), (ts_b, 0x123456), (ts_c, 0x123456)]
    grouped = group_statuses(parsed)
    assert len(grouped) == 2
    _, _, count_a, _, status_a = grouped[0]
    _, _, count_b, _, status_b = grouped[1]
    assert status_a == 0x470800
    assert status_b == 0x123456
    assert count_a == 1
    assert count_b == 2


def test_group_statuses_interleaved():
    from datetime import datetime

    ts_a = datetime(2026, 5, 7, 3, 0, 0, 0)
    ts_b = datetime(2026, 5, 7, 3, 0, 1, 0)
    ts_c = datetime(2026, 5, 7, 3, 0, 2, 0)
    ts_d = datetime(2026, 5, 7, 3, 0, 3, 0)
    parsed = [
        (ts_a, 0x1),
        (ts_b, 0x2),
        (ts_c, 0x1),
        (ts_d, 0x1),
    ]
    grouped = group_statuses(parsed)
    assert len(grouped) == 3
    _, _, c1, _, s1 = grouped[0]
    _, _, c_mid, _, s_mid = grouped[1]
    _, _, c2, _, s2 = grouped[2]
    assert s1 == 0x1
    assert s_mid == 0x2
    assert s2 == 0x1
    assert c1 == 1
    assert c_mid == 1
    assert c2 == 2


def test_compute_time_diff_stats_empty():
    stats = compute_time_diff_stats([])
    assert stats is None


def test_compute_time_diff_stats_single():
    from datetime import datetime

    stats = compute_time_diff_stats([(datetime(2026, 1, 1), 0)])
    assert stats is None


def test_compute_time_diff_stats_multiple():
    from datetime import datetime

    parsed = [
        (datetime(2026, 1, 1, 0, 0, 0), 0),
        (datetime(2026, 1, 1, 0, 0, 1), 0),
        (datetime(2026, 1, 1, 0, 0, 3), 0),
        (datetime(2026, 1, 1, 0, 0, 7), 0),
    ]
    stats = compute_time_diff_stats(parsed)
    assert stats is not None
    assert stats["min"] == 1.0
    assert stats["max"] == 4.0
    assert stats["count"] == 3
    assert abs(stats["avg"] - 2.33333) < 0.001
    assert stats["median"] == 2.0


def test_ins1msg_pattern():
    m = INS1MSG_PATTERN.search(SAMPLE_LINE)
    assert m is not None
    assert m.group("timestamp") == "2026-05-07 03:01:25.130"
    assert m.group("status") == "0x470800"


def test_ins1msg_pattern_no_match():
    assert INS1MSG_PATTERN.search("no status here") is None
    assert INS1MSG_PATTERN.search("insStatus_without_brackets") is None
