from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[2]))

from available_tools.inertial_sense_tools.decode_system_hdw_status_utils import (  # noqa: E402
    HdwStatusFlags,
    SystemHardwareStatus,
    decode_system_hdw_status,
    get_com_parse_error_count,
    HDW_STATUS_COM_PARSE_ERR_COUNT_MASK,
    HDW_STATUS_COM_PARSE_ERR_COUNT_OFFSET,
)


def test_decode_system_hdw_status_creates_object():
    parse_errors = (5 << HDW_STATUS_COM_PARSE_ERR_COUNT_OFFSET) & HDW_STATUS_COM_PARSE_ERR_COUNT_MASK
    status_val = (
        HdwStatusFlags.MOTION_GYR.value
        | HdwStatusFlags.SATURATION_ACC.value
        | HdwStatusFlags.GPS_SATELLITE_RX_VALID.value
        | HdwStatusFlags.SYSTEM_RESET_REQUIRED.value
        | parse_errors
    )

    decoded = decode_system_hdw_status(status_val)

    assert isinstance(decoded, SystemHardwareStatus)
    assert decoded.raw_value == status_val
    assert decoded.motion_and_imu["Gyro motion detected"]
    assert decoded.sensor_saturation["Accelerometer"]
    assert decoded.general_status_and_timing["GPS Satellite RX Valid"]
    assert decoded.faults_and_warnings["System Reset Required"]
    assert decoded.faults_and_warnings["Communications Parse Error Count"] == get_com_parse_error_count(status_val)
    assert "Hardware Status" in str(decoded)
