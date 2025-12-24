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
    assert decoded.receiver_state["GNSS1 satellite signals received"]
    assert decoded.receiver_state["GNSS2 satellite signals received"]
    assert decoded.reset_counts["GNSS1 reset count"] == 3
    assert decoded.pps_and_timing["GPS PPS time-synchronized"]
    assert decoded.pps_and_timing["No GPS1 PPS signal"]
    assert "GPS Hardware Status" in str(decoded)
