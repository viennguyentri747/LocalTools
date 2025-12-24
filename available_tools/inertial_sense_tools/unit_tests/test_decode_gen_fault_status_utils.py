from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[2]))

from available_tools.inertial_sense_tools.decode_gen_fault_status_utils import (  # noqa: E402
    GeneralFaultCode,
    GeneralFaultStatus,
    decode_gen_fault_status,
)


def test_decode_gen_fault_status_returns_object():
    status_val = int(GeneralFaultCode.INIT_I2C | GeneralFaultCode.GNSS_GENERAL_FAULT)

    decoded = decode_gen_fault_status(status_val)

    assert isinstance(decoded, GeneralFaultStatus)
    assert decoded.raw_value == status_val
    active_codes = {flag.code for flag in decoded.active_flags}
    assert active_codes == {GeneralFaultCode.INIT_I2C, GeneralFaultCode.GNSS_GENERAL_FAULT}
    assert decoded.unknown_bits is None
    text = str(decoded)
    assert "General Fault Status" in text
    assert "GPX-related" in text or "GPX" in text
