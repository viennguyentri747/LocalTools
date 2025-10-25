

from dev_common.constants import *


def get_md_todo_checkbox(is_done: bool) -> str:
    """Returns checkbox markdown for todo items."""
    return "[x]" if is_done else "[ ]"


def get_md_heading_prefix(level: int) -> str:
    """Returns markdown heading prefix."""
    return MD_DOUBLE_NEWLINE + "#" * level + " "


def get_md_list_prefix(list_level: int, is_ordered: bool = False, index: int = 1) -> str:
    """Returns markdown list prefix with proper indentation."""
    indent = MD_LIST_INDENT * list_level
    if is_ordered:
        return f"{MD_NEWLINE}{indent}{index}. "
    return f"{MD_NEWLINE}{indent}* "


def get_md_todo_prefix(list_level: int, is_done: bool) -> str:
    """Returns markdown todo item prefix."""
    indent = MD_LIST_INDENT * list_level
    checkbox = get_md_todo_checkbox(is_done)
    return f"{MD_NEWLINE}{indent}{checkbox} "


def get_md_wrap_text(text: str, wrapper: str) -> str:
    """Wraps text with markdown formatting."""
    return f"{wrapper}{text}{wrapper}"


def get_md_code_block_start(language: str = "") -> str:
    """Returns code block opening with optional language."""
    return f"{MD_NEWLINE}{MD_CODE_BLOCK_WRAPPER}{language}{MD_NEWLINE}"


def get_md_code_block_end() -> str:
    """Returns code block closing."""
    return f"{MD_NEWLINE}{MD_CODE_BLOCK_WRAPPER}{MD_NEWLINE}"


def get_md_link_text(text: str, url: str) -> str:
    """Returns formatted markdown link."""
    if text:
        return f"{text} ({url})"
    return url


def get_md_inline_link(url: str) -> str:
    """Returns inline markdown link."""
    return f"[{url}]({url})"


def get_md_panel_prefix(panel_type: str) -> str:
    """Returns panel/callout prefix."""
    return f"{MD_NEWLINE}[{panel_type.upper()}]: "


def get_md_status_badge(text: str) -> str:
    """Returns status badge text."""
    return f"[{text}]"


def get_md_date_text(timestamp: str) -> str:
    """Returns formatted date text."""
    return f"[Date: {timestamp}]"


def get_md_media_text(alt_text: str = "", url: str = "") -> str:
    """Returns formatted media reference."""
    if alt_text:
        return f"[Image: {alt_text}]"
    elif url:
        return f"[Media: {url}]"
    return "[Image]"


def get_md_expand_header(title: str) -> str:
    """Returns expand section header."""
    return f"{MD_NEWLINE}[Expand: {title}]{MD_NEWLINE}"


def get_md_decision_prefix(state: str) -> str:
    """Returns decision item prefix."""
    return f"{MD_NEWLINE}[Decision - {state}]: "


def get_md_extension_text(extension_key: str) -> str:
    """Returns extension reference text."""
    return f"[Extension: {extension_key}]"


def get_md_table_cell_separator() -> str:
    """Returns table cell separator."""
    return " | "


def get_md_apply_text_marks(text: str, marks: list) -> str:
    """Applies text formatting marks to text."""
    for mark in marks:
        mark_type = mark.get("type")
        if mark_type == "strong":
            text = get_md_wrap_text(text, MD_BOLD_WRAPPER)
        elif mark_type == "em":
            text = get_md_wrap_text(text, MD_ITALIC_WRAPPER)
        elif mark_type == "strike":
            text = get_md_wrap_text(text, MD_STRIKETHROUGH_WRAPPER)
        elif mark_type == "underline":
            text = get_md_wrap_text(text, MD_UNDERLINE_WRAPPER)
        elif mark_type == "code":
            text = get_md_wrap_text(text, MD_CODE_WRAPPER)
    return text
