from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[2]))

from available_tools.inertial_sense_tools.decode_gps_status_utils import (  # noqa: E402
    GpsFixType,
    GpsStatusFlags,
    GpsStatusReport,
    decode_gps_status,
)


def test_decode_gps_status_yields_report_object():
    status_val = int(GpsFixType.FIX_3D) | GpsStatusFlags.FIX_OK.value | GpsStatusFlags.GPS_PPS_TIMESYNC.value

    report = decode_gps_status(status_val)

    assert isinstance(report, GpsStatusReport)
    assert report.raw_status == status_val
    assert report.fix_type == GpsFixType.FIX_3D
    assert GpsStatusFlags.FIX_OK in report.flags
    assert GpsStatusFlags.GPS_PPS_TIMESYNC in report.flags
    assert "Raw Status" in str(report)
