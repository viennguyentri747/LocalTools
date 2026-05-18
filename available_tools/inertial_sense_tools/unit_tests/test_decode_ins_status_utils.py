from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[2]))

from available_tools.inertial_sense_tools.decode_ins_status_utils import (
    InsStatus,
    decode_ins_status,
    INS_STATUS_GPS_AIDING_POS,
    INS_STATUS_GPS_AIDING_VEL,
    INS_STATUS_NAV_MODE,
    INS_STATUS_RTK_RAW_GPS_DATA_ERROR,
    INS_STATUS_KINEMATIC_CAL_GOOD,
    INS_STATUS_SOLUTION_NAV,
    INS_STATUS_SOLUTION_OFFSET,
    INS_STATUS_SOLUTION_MASK,
)


def _build_status_with_solution(solution_constant: int) -> int:
    return (solution_constant << INS_STATUS_SOLUTION_OFFSET) & INS_STATUS_SOLUTION_MASK


def test_decode_ins_status_creates_object():
    status_val = (
        INS_STATUS_GPS_AIDING_POS
        | INS_STATUS_GPS_AIDING_VEL
        | INS_STATUS_NAV_MODE
        | INS_STATUS_RTK_RAW_GPS_DATA_ERROR
        | INS_STATUS_KINEMATIC_CAL_GOOD
        | _build_status_with_solution(INS_STATUS_SOLUTION_NAV)
    )

    decoded = decode_ins_status(status_val)

    assert isinstance(decoded, InsStatus)
    assert decoded.raw_value == status_val
    assert decoded.solution_status == "Nav"
    assert decoded.aiding_status["GPS Aiding Position"]
    assert decoded.aiding_status["GPS Aiding Velocity"]
    assert decoded.operational_mode["Navigation Mode"]
    assert decoded.rtk_status["Raw GPS Data Error"]
    assert decoded.kinematic_calibration_good
    assert "INS Status" in str(decoded)


def test_ins_status_compact_string_is_single_line():
    status_val = INS_STATUS_GPS_AIDING_POS | INS_STATUS_NAV_MODE | _build_status_with_solution(INS_STATUS_SOLUTION_NAV)
    compact = decode_ins_status(status_val).to_compact_str()
    assert "\n" not in compact
    assert "INS 0x" in compact
    assert "sol=Nav" in compact
    assert "aid=" in compact
