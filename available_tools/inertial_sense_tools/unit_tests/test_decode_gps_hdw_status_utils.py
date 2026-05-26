from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[2]))

from available_tools.inertial_sense_tools.decode_gps_hdw_status_utils import (  # noqa: E402
    GNSS1_RESET_COUNT_MASK,
    GNSS1_RESET_COUNT_OFFSET,
    GpsHardwareStatus,
    GpsHdwStatusFlags,
    decode_gps_hdw_status,
)


def test_decode_gps_hdw_status_creates_structured_object():
    status_val = (
        GpsHdwStatusFlags.GNSS1_SATELLITE_RX.value
        | GpsHdwStatusFlags.GNSS2_SATELLITE_RX.value
        | ((3 << GNSS1_RESET_COUNT_OFFSET) & GNSS1_RESET_COUNT_MASK)
        | GpsHdwStatusFlags.GPS_PPS_TIMESYNC.value
        | GpsHdwStatusFlags.ERR_NO_GPS1_PPS.value
    )

    decoded = decode_gps_hdw_status(status_val)

    assert isinstance(decoded, GpsHardwareStatus)
    assert decoded.raw_value == status_val
    assert decoded.receiver_state.gnss1_satellite_rx
    assert decoded.receiver_state.gnss2_satellite_rx
    assert decoded.reset_counts.gnss1_reset_count == 3
    assert decoded.pps_and_timing.gps_pps_timesync
    assert decoded.pps_and_timing.no_gps1_pps_signal
    assert "GPS Hardware Status" in str(decoded)
