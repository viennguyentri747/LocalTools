import re
from readable_number import ReadableNumber


def beautify_number(n, precision=2, use_shortform=True):
    """
    Converts a number to a human-readable abbreviated format.
    Examples:
        1234 -> 1.23k
        1234567 -> 1.23M
        1234567890 -> 1.23B

    Args:
        n (int or float): Number to convert.
        precision (int): Decimal places to round to.
        use_shortform (bool): Whether to use abbreviated units (k, M, B, etc.)

    Returns:
        str: Human-readable string of the number.
    """
    return str(ReadableNumber(n, precision=precision, use_shortform=use_shortform))


def str_to_slug(s: str):
    s = s.lower().strip()
    s = re.sub(r'[^\w\s-]', '', s)
    s = re.sub(r'[\s_-]+', '-', s)
    s = re.sub(r'^-+|-+$', '', s)
    return s


def get_path_no_suffix(path: str, suffix: str) -> str:
    if path.endswith(suffix):
        path = path[:-len(suffix)]
    return path
