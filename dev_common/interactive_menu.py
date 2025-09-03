from __future__ import annotations

import curses
import sys
from typing import List, Optional


def interactive_select_with_arrows(options: List[str], title: Optional[str] = None, selectables: Optional[List[bool]] = None) -> Optional[int]:
    """Interactive selector using arrow keys.

    - Up/Down or k/j to navigate
    - Enter to select
    - q or ESC to cancel (returns None)

    Falls back to numeric selection if stdout/stderr are not TTYs
    or if curses fails to initialize.
    """
    if not options:
        return None

    full_title = f"{title} (↑/↓ or j/k, Enter to select, q to cancel)"
    # Fallback if not a terminal
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        return _numeric_fallback(options, full_title, selectables)
    try:
        return curses.wrapper(_interactive_menu_selector, options, full_title, selectables)
    except Exception:
        # If curses fails for any reason, gracefully fall back
        return _numeric_fallback(options, title, selectables)


def _next_selectable(options: List[str], selectables: List[bool], current: int, direction: int) -> int:
    """Find the next selectable index in the given direction, wrapping around if necessary."""
    n = len(options)
    i = current
    while True:
        i = (i + direction) % n
        if i == current:
            return current  # No other selectable items, stay put
        if selectables[i]:
            return i


def _interactive_menu_selector(stdscr: "curses._CursesWindow", options: List[str], title: Optional[str], selectables: Optional[List[bool]]) -> Optional[int]:
    """
    Display a keyboard-navigable terminal menu for option selection.
    Navigation: UP/DOWN or k/j (move), HOME/END (jump), ENTER (select), ESC/q (cancel)
    
    Args:
        stdscr: Curses window for rendering
        options: List of menu option strings
        title: Optional header text
        selectables: Optional list of booleans indicating if each option is selectable
        
    Returns:
        Zero-based index of selected option, or None if cancelled
    """
    if selectables is None:
        selectables = [True] * len(options)
    curses.curs_set(0)
    stdscr.keypad(True)
    curses.use_default_colors()

    # Start cursor on first selectable item
    cursor = next((i for i in range(len(options)) if selectables[i]), 0)
    top = 0

    while True:
        height, width = stdscr.getmaxyx()
        first_row = 1 if title else 0
        visible_rows = max(1, height - first_row)

        # Ensure cursor is within the visible window
        if cursor < top:
            top = cursor
        elif cursor >= top + visible_rows:
            top = cursor - visible_rows + 1

        _draw_menu(stdscr, options, title, cursor, top)

        ch = stdscr.getch()
        if ch in (curses.KEY_UP, ord('k')):
            cursor = _next_selectable(options, selectables, cursor, -1)
        elif ch in (curses.KEY_DOWN, ord('j')):
            cursor = _next_selectable(options, selectables, cursor, 1)
        elif ch in (curses.KEY_HOME,):
            cursor = next((i for i in range(len(options)) if selectables[i]), 0)
        elif ch in (curses.KEY_END,):
            cursor = next((i for i in range(len(options) - 1, -1, -1) if selectables[i]), len(options) - 1)
        elif ch in (10, 13, curses.KEY_ENTER):  # Enter
            return cursor
        elif ch in (27, ord('q')):  # ESC or q to cancel
            return None
        elif ch == curses.KEY_RESIZE:
            # Redraw on resize; loop will handle
            pass


def _draw_menu(
    stdscr: "curses._CursesWindow",
    options: List[str],
    title: Optional[str],
    cursor: int,
    top: int,
) -> None:
    """Draws the menu on the screen with the given options, title, cursor position, and top visible index."""
    stdscr.erase()
    height, width = stdscr.getmaxyx()

    # Reserve first line for title (if any)
    row = 0
    if title:
        title_text = title[: max(0, width - 1)]
        stdscr.addstr(row, 0, title_text, curses.A_BOLD)
        row += 1

    visible_rows = height - row
    if visible_rows <= 0:
        stdscr.refresh()
        return

    end = min(len(options), top + visible_rows)
    for i, opt in enumerate(options[top:end], start=top):
        y = row + (i - top)
        line = opt[: max(0, width - 1)]
        if i == cursor:
            stdscr.addstr(y, 0, line, curses.A_REVERSE)
        else:
            stdscr.addstr(y, 0, line)
    stdscr.refresh()


def _numeric_fallback(options: List[str], title: Optional[str] = None, selectables: Optional[List[bool]] = None) -> Optional[int]:
    """Provides a fallback numeric selection when curses is not available or fails."""
    if selectables is None:
        selectables = [True] * len(options)
    selectable_indices = [i for i, s in enumerate(selectables) if s]
    if not selectable_indices:
        return None
    if title:
        print(title)
    for num, idx in enumerate(selectable_indices, start=1):
        print(f"  [{num}] {options[idx]}")
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
                return selectable_indices[num - 1]
        print("Invalid choice. Enter a number from the list.")


__all__ = ["interactive_select_with_arrows"]
