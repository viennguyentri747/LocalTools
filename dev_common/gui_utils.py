from __future__ import annotations

import curses
import shutil
import sys
from typing import List, Optional
from dataclasses import dataclass
from typing import Any


@dataclass
class OptionData:
    title: str
    selectable: bool
    data: Optional[Any] = None


def interactive_select_with_arrows(option_data: List[OptionData], menu_title: Optional[str] = None) -> Optional[OptionData]:
    """Interactive selector using arrow keys.

    - Up/Down or k/j to navigate
    - Enter to select
    - q or ESC to cancel (returns None)

    Falls back to numeric selection if stdout/stderr are not TTYs
    or if curses fails to initialize.
    """
    if not option_data:
        return None

    # Build a title that can span multiple lines. If the caller supplies
    # multiple lines, put the help hint on its own line for clarity.
    help_hint = "(↑/↓ or j/k, Enter to select, q to cancel)"
    if menu_title:
        if "\n" in menu_title:
            full_title = f"{menu_title}\n{help_hint}"
        else:
            full_title = f"{menu_title} {help_hint}"
    else:
        full_title = help_hint
    # Fallback if not a terminal
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        return _numeric_fallback(option_data, full_title)
    try:
        return curses.wrapper(_interactive_menu_selector, option_data, full_title)
    except Exception:
        # If curses fails for any reason, gracefully fall back
        return _numeric_fallback(option_data, full_title)


def _interactive_menu_selector(stdscr: "curses._CursesWindow", option_data: List[OptionData], title: Optional[str]) -> Optional[OptionData]:
    """
    Display a keyboard-navigable terminal menu for option selection.
    Navigation: UP/DOWN or k/j (move), HOME/END (jump), ENTER (select), ESC/q (cancel)

    Args:
        stdscr: Curses window for rendering
        option_data: List of OptionData for menu options
        title: Optional header text

    Returns:
        Selected OptionData, or None if cancelled
    """
    curses.curs_set(0)
    stdscr.keypad(True)
    curses.use_default_colors()

    # Get initial terminal dimensions
    height, width = stdscr.getmaxyx()

    # Pre-process option data to handle multi-line titles
    processed_options = []
    option_line_counts = []

    for od in option_data:
        lines = _wrap_text(od.title, width - 2)  # Use actual terminal width minus padding
        processed_options.append((od, lines))
        option_line_counts.append(len(lines))

    # Start cursor on first selectable item
    cursor = next((i for i in range(len(option_data)) if option_data[i].selectable), 0)
    top = 0

    while True:
        height, width = stdscr.getmaxyx()  # Get current dimensions (in case of resize)
        # Compute wrapped title lines count for current width
        title_lines: List[str] = []
        if title:
            for tline in title.split("\n"):
                title_lines.extend(_wrap_text(tline, max(1, width - 1)))
        first_row = len(title_lines)
        visible_rows = max(1, height - first_row)

        # Calculate total lines needed for display
        total_lines_before_cursor = sum(option_line_counts[:cursor])
        cursor_lines = option_line_counts[cursor] if cursor < len(option_line_counts) else 1

        # Adjust top to keep cursor visible
        if total_lines_before_cursor < top:
            top = total_lines_before_cursor
        elif total_lines_before_cursor + cursor_lines > top + visible_rows:
            top = max(0, total_lines_before_cursor + cursor_lines - visible_rows)

        _draw_menu_multiline(stdscr, processed_options, title, cursor, top)

        ch = stdscr.getch()
        if ch in (curses.KEY_UP, ord('k')):
            cursor = _next_selectable(option_data, cursor, -1)
        elif ch in (curses.KEY_DOWN, ord('j')):
            cursor = _next_selectable(option_data, cursor, 1)
        elif ch in (curses.KEY_HOME,):
            cursor = next((i for i in range(len(option_data)) if option_data[i].selectable), 0)
        elif ch in (curses.KEY_END,):
            cursor = next((i for i in range(len(option_data) - 1, -1, -1)
                          if option_data[i].selectable), len(option_data) - 1)
        elif ch in (10, 13, curses.KEY_ENTER):  # Enter
            return option_data[cursor]
        elif ch in (27, ord('q')):  # ESC or q to cancel
            return None
        elif ch == curses.KEY_RESIZE:
            # Re-process options with new width on resize
            height, width = stdscr.getmaxyx()
            processed_options = []
            option_line_counts = []

            for od in option_data:
                lines = _wrap_text(od.title, width - 2)
                processed_options.append((od, lines))
                option_line_counts.append(len(lines))


def _draw_menu_multiline(
    stdscr: "curses._CursesWindow",
    processed_options: List[tuple],
    title: Optional[str],
    cursor: int,
    top: int,
) -> None:
    """Draws the menu with support for multi-line options."""
    stdscr.erase()
    height, width = _get_terminal_size()  # Use reliable terminal size detection

    # Draw (possibly multi-line) title
    row = 0
    if title:
        wrapped_title: List[str] = []
        for tline in title.split("\n"):
            wrapped_title.extend(_wrap_text(tline, max(1, width - 1)))
        for tline in wrapped_title:
            try:
                stdscr.addstr(row, 0, tline[: max(0, width - 1)], curses.A_BOLD)
            except curses.error:
                pass
            row += 1

    visible_rows = height - row
    if visible_rows <= 0:
        stdscr.refresh()
        return

    current_line = 0
    display_row = row

    for option_idx, (od, lines) in enumerate(processed_options):
        # Skip lines before the visible top
        if current_line + len(lines) <= top:
            current_line += len(lines)
            continue

        # Check if we've filled the visible area
        if display_row >= height:
            break

        # Display lines for this option
        for line_idx, line in enumerate(lines):
            line_number = current_line + line_idx

            # Skip lines before visible top
            if line_number < top:
                continue

            # Check if we've run out of screen space
            if display_row >= height:
                break

            # Truncate line to fit screen width with some padding
            display_line = line[: max(0, width - 2)] if len(line) > width - 2 else line

            # Highlight entire option if this is the cursor position
            if option_idx == cursor:
                try:
                    stdscr.addstr(display_row, 0, display_line, curses.A_REVERSE)
                except curses.error:
                    pass
            else:
                try:
                    stdscr.addstr(display_row, 0, display_line)
                except curses.error:
                    pass

            display_row += 1

        current_line += len(lines)

        # Stop if we've filled the screen
        if display_row >= height:
            break

    stdscr.refresh()


def _get_terminal_size() -> tuple[int, int]:
    """Get terminal size using multiple fallback methods.
    Returns:
        A tuple of (lines, columns)
    """
    size = shutil.get_terminal_size()
    return size.lines, size.columns


def _next_selectable(option_data: List[OptionData], current: int, direction: int) -> int:
    """Find the next selectable index in the given direction, wrapping around if necessary."""
    n = len(option_data)
    i = current
    while True:
        i = (i + direction) % n
        if i == current:
            return current  # No other selectable items, stay put
        if option_data[i].selectable:
            return i


def _wrap_text(text: str, width: int) -> List[str]:
    """Wrap text to fit within the given width, respecting word boundaries where possible."""
    if width <= 0:
        return [text]

    lines = []
    for line in text.split('\n'):
        if len(line) <= width:
            lines.append(line)
        else:
            # For very long lines, try to break at spaces first
            words = line.split(' ')
            current_line = ""

            for word in words:
                test_line = f"{current_line} {word}".strip()
                if len(test_line) <= width:
                    current_line = test_line
                else:
                    if current_line:
                        lines.append(current_line)
                    # If single word is too long, truncate it
                    if len(word) > width:
                        lines.append(word[:width-3] + "...")
                    else:
                        current_line = word

            if current_line:
                lines.append(current_line)

    return lines


def _numeric_fallback(option_data: List[OptionData], title: Optional[str] = None) -> Optional[OptionData]:
    """Provides a fallback numeric selection when curses is not available or fails."""
    selectable_indices = [i for i, od in enumerate(option_data) if od.selectable]
    if not selectable_indices:
        return None
    if title:
        print(title)
    for num, idx in enumerate(selectable_indices, start=1):
        print(f"  [{num}] {option_data[idx].title}")
    while True:
        try:
            raw = input("Select number (or 'q' to cancel): ").strip()
        except EOFError:
            return None
        if raw.lower() in {"q", "quit", "exit"}:
            return None
        if raw.isdigit():
            num = int(raw)
            if 1 <= num <= len(selectable_indices):
                return option_data[selectable_indices[num - 1]]
        print("Invalid choice. Enter a number from the list.")


__all__ = ["interactive_select_with_arrows", "OptionData"]
