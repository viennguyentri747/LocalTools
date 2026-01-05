import re
from datetime import datetime
import shlex
from typing import List, Union
from readable_number import ReadableNumber
from pathvalidate import sanitize_filename


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


def sanitize_str_to_file_name(s: str):
    """
    Convert a string to a safe filename while preserving spaces and readability.
    Removes/replaces invalid characters but keeps the name natural.
    """
    return sanitize_filename(s.strip())


def get_path_no_suffix(path: str, suffix: str) -> str:
    if path.endswith(suffix):
        path = path[:-len(suffix)]
    return path


def get_short_date_now(dt=None) -> str:
    """
    Return a short, lowercase date string like 'aug 1'.
    If dt is None, uses the current local date/time.
    """
    dt = dt or datetime.now()
    return f"{dt.strftime('%b').lower()} {dt.day}"


def get_time_stamp_now() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def quote(s: Union[str, List[str], None]) -> Union[str, List[str]]:
    """Quote a string, list of strings, or None value for shell safety.
    Ensures all values are wrapped in quotes for consistency.
    """
    def ensure_quoted(value: str) -> str:
        """Ensure a string is quoted, adding quotes if not present."""
        quoted = shlex.quote(value)
        # If shlex.quote didn't add quotes (safe string), add them manually
        if quoted == value and not (quoted.startswith("'") or quoted.startswith('"')):
            return f"'{value}'"
        return quoted

    if s is None:
        return '""'
    elif isinstance(s, list):
        # Quote each list item individually and return list
        return [ensure_quoted(str(item)) for item in s]
    elif not isinstance(s, (str, bytes)):
        # Convert other types to string
        print(f"[WARNING] Converting {type(s)} to string")
        s = str(s)

    return ensure_quoted(s)


def quote_arg_value_if_need(arg_value) -> Union[str, List[str]]:
    """Quote strings with glob characters, handle lists too."""
    def _quote_one(single_value: str) -> str:
        if (single_value.startswith("'") and single_value.endswith("'")) or (single_value.startswith('"') and single_value.endswith('"')):
            # Already quoted? leave it alone
            return single_value

        # Characters that need quoting in shell arguments
        # * ? [ ] { }  - Glob/wildcard expansion characters
        # ( ) < >      - Redirection and subshell characters
        # | & ;        - Pipe, background, and command separator
        # $ `          - Variable expansion and command substitution
        # \            - Escape character
        # \s           - Whitespace (spaces, tabs, newlines)
        # " '          - Quote characters themselves
        needs_quoting = bool(re.search(r'[*?\[\]{}()<>|;&$`\\\s"\']', single_value))

        if needs_quoting:
            # Use single quotes and escape any single quotes within
            escaped_value = single_value.replace("'", "'\"'\"'")
            return f"'{escaped_value}'"

        return single_value

    if isinstance(arg_value, list):
        return [_quote_one(str(v)) for v in arg_value]
    elif isinstance(arg_value, str):
        return _quote_one(arg_value)
    else:
        return str(arg_value)


def strip_quotes(path_str: str) -> str:
    """Remove surrounding quotes from a path string."""
    path_str = path_str.strip()
    if (path_str.startswith('"') and path_str.endswith('"')) or \
       (path_str.startswith("'") and path_str.endswith("'")):
        return path_str[1:-1]
    return path_str


def get_stripped_paragraph(paragraph: str) -> str:
    result = paragraph
    # Remove consecutive blank lines
    result = re.sub(r'^\n\s*\n', '\n', result)
    # Remove leading and trailing newlines
    result = result.strip('\n')
    return result


def format_float(value, min_decimals=3, max_decimals=10):
    formatted = f"{value:.{max_decimals}f}".rstrip('0')  # Remove trailing zeros. Ex: 1.2300 -> 1.23, 1.0000 -> 1.
    
    # If no decimal point or too few decimals, enforce minimum
    if '.' not in formatted or len(formatted.split('.')[1]) < min_decimals:
        return f"{value:.{min_decimals}f}"
    
    return formatted
