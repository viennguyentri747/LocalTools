"""Math and integer-base conversion helpers shared across local tools."""

from typing import Literal

IntegerFormat = Literal["hex", "dec", "bin"]
INT_FORMAT_HEX: IntegerFormat = "hex"
INT_FORMAT_DEC: IntegerFormat = "dec"
INT_FORMAT_BIN: IntegerFormat = "bin"
SUPPORTED_INT_FORMATS: tuple[str, ...] = (INT_FORMAT_HEX, INT_FORMAT_DEC, INT_FORMAT_BIN)


def normalize_integer_format(raw_format: str | None) -> IntegerFormat:
    """Normalize and validate integer format name.

    Examples:
        >>> normalize_integer_format("HEX")
        'hex'
        >>> normalize_integer_format(None)
        'hex'
    """
    normalized = (raw_format or INT_FORMAT_HEX).strip().lower()
    if normalized not in SUPPORTED_INT_FORMATS:
        raise ValueError(f"Unsupported integer format '{raw_format}'. Supported formats: {', '.join(SUPPORTED_INT_FORMATS)}")
    return normalized  # type: ignore[return-value]


def _split_sign(raw: str) -> tuple[int, str]:
    if raw.startswith("+"): return 1, raw[1:]
    if raw.startswith("-"): return -1, raw[1:]
    return 1, raw


def parse_integer_value(value: int | str, parse_format: str, value_name: str = "value") -> int:
    """Parse integer value from number/text with explicit base behavior.

    Args:
        value: Integer or text form (`"42"`, `"0x2A"`, `"2A"`, `"0b101010"`).
        parse_format: One of `hex|dec|bin`.
            - `hex`: parse as base-16 (optional `0x` prefix).
            - `dec`: parse as base-10.
            - `bin`: parse as base-2 (optional `0b` prefix).
        value_name: Field label used in error messages.

    Returns:
        Parsed integer.

    Raises:
        TypeError: Unsupported value type.
        ValueError: Empty/invalid text or invalid format.

    Examples:
        >>> parse_integer_value("92492279", "dec")
        92492279
        >>> parse_integer_value("58351f7", "hex")
        92492279
        >>> parse_integer_value("-0b1010", "bin")
        -10
    """
    if isinstance(value, int): return value
    if not isinstance(value, str): raise TypeError(f"{value_name} must be int or str, got {type(value).__name__}")
    raw = value.strip().replace("_", "")
    if not raw: raise ValueError(f"{value_name} cannot be empty")
    fmt = normalize_integer_format(parse_format)
    sign, unsigned = _split_sign(raw)
    if not unsigned: raise ValueError(f"{value_name} is missing digits: '{value}'")
    if fmt == INT_FORMAT_HEX:
        if unsigned.lower().startswith("0x"): unsigned = unsigned[2:]
        if not unsigned: raise ValueError(f"{value_name} is missing hex digits: '{value}'")
        return sign * int(unsigned, 16)
    if fmt == INT_FORMAT_DEC:
        return int(raw, 10)
    if fmt == INT_FORMAT_BIN:
        if unsigned.lower().startswith("0b"): unsigned = unsigned[2:]
        if not unsigned: raise ValueError(f"{value_name} is missing binary digits: '{value}'")
        return sign * int(unsigned, 2)
    raise ValueError(f"Unsupported integer format '{fmt}'")


def format_integer_value(value: int, output_format: str = INT_FORMAT_HEX, width: int = 0, include_prefix: bool = True) -> str:
    """Format integer into selected base string.

    Args:
        value: Integer to format.
        output_format: One of `hex|dec|bin`.
        width: Zero-padding width for hex/bin digits (excluding sign/prefix).
        include_prefix: Include `0x` or `0b` for hex/bin output.

    Returns:
        Formatted string representation.

    Examples:
        >>> format_integer_value(92492279, "hex", width=8)
        '0x058351F7'
        >>> format_integer_value(92492279, "dec")
        '92492279'
        >>> format_integer_value(10, "bin", width=8)
        '0b00001010'
    """
    fmt = normalize_integer_format(output_format)
    if fmt == INT_FORMAT_DEC: return str(value)
    if fmt == INT_FORMAT_HEX:
        sign = "-" if value < 0 else ""
        body = f"{abs(value):0{width}X}" if width > 0 else f"{abs(value):X}"
        return f"{sign}{'0x' if include_prefix else ''}{body}"
    if fmt == INT_FORMAT_BIN:
        sign = "-" if value < 0 else ""
        body = f"{abs(value):0{width}b}" if width > 0 else f"{abs(value):b}"
        return f"{sign}{'0b' if include_prefix else ''}{body}"
    raise ValueError(f"Unsupported integer format '{fmt}'")


def hex_to_dec(value: int | str) -> int:
    """Convert a hex value into decimal integer."""
    return parse_integer_value(value=value, parse_format=INT_FORMAT_HEX, value_name="hex value")


def dec_to_hex(value: int | str, width: int = 0, include_prefix: bool = True) -> str:
    """Convert a decimal value into a hex string."""
    dec_value = parse_integer_value(value=value, parse_format=INT_FORMAT_DEC, value_name="decimal value")
    return format_integer_value(dec_value, output_format=INT_FORMAT_HEX, width=width, include_prefix=include_prefix)


def normalize_int_format(input_format: str | None) -> IntegerFormat:
    """Backward-compatible alias for `normalize_integer_format`."""
    return normalize_integer_format(input_format)


def parse_int_with_format(value: int | str, input_format: str = INT_FORMAT_HEX, value_name: str = "value") -> int:
    """Backward-compatible alias for `parse_integer_value`."""
    return parse_integer_value(value=value, parse_format=input_format, value_name=value_name)


def format_int_with_format(value: int, output_format: str = INT_FORMAT_HEX, width: int = 0, include_prefix: bool = True) -> str:
    """Backward-compatible alias for `format_integer_value`."""
    return format_integer_value(value=value, output_format=output_format, width=width, include_prefix=include_prefix)
