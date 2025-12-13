from __future__ import annotations

import curses
import shutil
import sys
from typing import List, Optional
from dataclasses import dataclass, field
from typing import Any

from dev.dev_common.core_utils import LOG


@dataclass
class OptionData:
    title: str
    selectable: bool
    data: Optional[Any] = None
    children: List[OptionData] = field(default_factory=list)
    collapsed: bool = True
    # Temporary fields for tracking
    parent: Optional[OptionData] = None
    level: int = 0

    def __init__(self, title: str, selectable: bool = False, data: Optional[Any] = None, children: List[OptionData] = [], collapsed: bool = True):
        self.title = title
        self.selectable = selectable
        self.data = data
        self.children = children
        self.collapsed = collapsed


def _set_levels(options: List[OptionData], level: int = 0, parent: Optional[OptionData] = None) -> None:
    """Set the level and parent for each option recursively."""
    for option in options:
        option.level = level
        option.parent = parent
        if option.children:
            _set_levels(option.children, level + 1, option)


def find_next_selectable_and_expand(options: List[OptionData], current_index: int, direction: int) -> int:
    """
    Find next selectable item using depth-first search and expand parent chains as needed.

    Args:
        options: Root level options
        current_index: Current cursor position in flattened list
        direction: 1 for next, -1 for previous

    Returns:
        Index of next selectable item in flattened list
    """
    # Get all options in depth-first order (this represents the "navigation order")
    def get_all_options_dfs(opts: List[OptionData]) -> List[OptionData]:
        """Get all options in depth-first order, regardless of collapsed state."""
        result = []
        for opt in opts:
            result.append(opt)
            if opt.children:
                result.extend(get_all_options_dfs(opt.children))
        return result

    all_options_dfs = get_all_options_dfs(options)

    # Find current option in the DFS order
    current_flat = _flatten_non_collapsed_options(options)
    if current_index >= len(current_flat) or current_index < 0:
        # Handle initialization case - find first selectable
        if direction > 0:
            current_dfs_index = -1  # Start before first item
        else:
            current_dfs_index = len(all_options_dfs)  # Start after last item
    else:
        current_option = current_flat[current_index]
        try:
            current_dfs_index = all_options_dfs.index(current_option)
        except ValueError:
            current_dfs_index = 0

    # Search for next selectable in DFS order
    dfs_length = len(all_options_dfs)
    for step in range(1, dfs_length + 1):  # +1 to handle full wrap-around
        next_dfs_index = (current_dfs_index + direction * step) % dfs_length
        next_option = all_options_dfs[next_dfs_index]

        if next_option.selectable:
            # Found a selectable option - now expand its parent chain
            _expand_parent_chain(next_option)

            # Collapse siblings of parents at each level to maintain clean navigation
            _collapse_siblings_of_parents(next_option, options)

            # Get new flattened list and find the index
            new_flat = _flatten_non_collapsed_options(options)
            try:
                return new_flat.index(next_option)
            except ValueError:
                return current_index

    return current_index  # No selectable found, stay put


def _expand_parent_chain(option: OptionData) -> None:
    """Expand all parents up to the root for the given option."""
    current = option.parent
    while current:
        current.collapsed = False
        current = current.parent


def _collapse_siblings_of_parents(option: OptionData, root_options: List[OptionData]) -> None:
    """
    Collapse sibling branches that are not in the path to the selected option.
    This keeps the interface clean by only showing the relevant expanded branches.
    """
    # Get the path from root to the option
    path_to_option = []
    current = option
    while current:
        path_to_option.append(current)
        current = current.parent
    path_to_option.reverse()  # Now root to option

    def collapse_siblings_recursive(opts: List[OptionData], path_index: int):
        if path_index >= len(path_to_option):
            return

        target_option = path_to_option[path_index]

        for opt in opts:
            if opt == target_option:
                # This is in our path - don't collapse it, but recurse into its children
                if opt.children and path_index + 1 < len(path_to_option):
                    collapse_siblings_recursive(opt.children, path_index + 1)
            else:
                # This is a sibling - collapse it if it has children
                if opt.children and not opt.collapsed:
                    # Only collapse if it's at the same level as our target and not a parent
                    if opt.level == target_option.level:
                        opt.collapsed = True

    # Start the collapsing process from root
    if path_to_option:
        collapse_siblings_recursive(root_options, 0)


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

    # Never modify the original list
    options_copy = [od for od in option_data]

    # Set levels for all options
    _set_levels(options_copy)

    # Build a title that can span multiple lines. If the caller supplies
    # multiple lines, put the help hint on its own line for clarity.
    help_hint = "(↑/↓ or j/k, Enter to select, q to cancel)"
    if menu_title:
        if "\n" in menu_title:
            full_title = f"{menu_title}\n{help_hint}\n"
        else:
            full_title = f"{menu_title} {help_hint}\n"
    else:
        full_title = f"{help_hint}\n"
    # Fallback if not a terminal
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        return _numeric_fallback(option_data, full_title)
    try:
        return curses.wrapper(_interactive_menu_selector, options_copy, full_title)
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

    # Initialize cursor to first selectable item
    cursor = find_next_selectable_and_expand(option_data, -1, 1)
    top = 0

    while True:
        height, width = stdscr.getmaxyx()  # Get current dimensions (in case of resize)

        # Re-flatten after any expansions
        flat_options = _flatten_non_collapsed_options(option_data)

        # Pre-process option data to handle multi-line titles
        processed_options: List[tuple[OptionData, list[str]]] = []
        option_line_counts: List[int] = []

        for od in flat_options:
            prefix = ""
            if od.children:
                prefix = "[-] " if not od.collapsed else "[+] "

            lines = _wrap_text(prefix + od.title, width - 2)
            processed_options.append((od, lines))
            option_line_counts.append(len(lines))

        # Ensure cursor is still valid
        if cursor >= len(flat_options):
            cursor = max(0, len(flat_options) - 1)

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
            cursor = find_next_selectable_and_expand(option_data, cursor, -1)
        elif ch in (curses.KEY_DOWN, ord('j')):
            cursor = find_next_selectable_and_expand(option_data, cursor, 1)
        elif ch in (curses.KEY_HOME,):
            cursor = find_next_selectable_and_expand(option_data, -1, 1)
        elif ch in (curses.KEY_END,):
            cursor = find_next_selectable_and_expand(option_data, len(flat_options), -1)
        elif ch in (10, 13, curses.KEY_ENTER):  # Enter
            if cursor < len(flat_options):
                selected_option = flat_options[cursor]
                if selected_option.selectable:
                    return selected_option
        elif ch in (27, ord('q')):  # ESC or q to cancel
            return None
        elif ch == curses.KEY_RESIZE:
            # Handled at the start of the loop
            pass


def _flatten_non_collapsed_options(options: List[OptionData], parent: Optional[OptionData] = None) -> List[OptionData]:
    """Recursively flattens the list of options, respecting the collapsed state."""
    flat_list = []
    for option in options:
        option.parent = parent
        flat_list.append(option)
        if option.children and not option.collapsed:
            flat_list.extend(_flatten_non_collapsed_options(option.children, parent=option))
    return flat_list


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
                attr = curses.A_REVERSE
                if not od.selectable:
                    # Non-selectable items shouldn't be fully reversed.
                    # This could be customized further.
                    attr = curses.A_BOLD
                try:
                    stdscr.addstr(display_row, 0, display_line, attr)
                except curses.error:
                    pass
            else:
                attr = curses.A_NORMAL
                if not od.selectable:
                    attr = curses.A_DIM  # Make non-selectable items less prominent
                try:
                    stdscr.addstr(display_row, 0, display_line, attr)
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


def _numeric_fallback(option_data: List[OptionData], title: Optional[str] = None) -> Optional[OptionData]:
    """Provides a fallback numeric selection when curses is not available or fails."""
    flat_options = _flatten_non_collapsed_options(option_data)
    selectable_options = [od for od in flat_options if od.selectable]
    if not selectable_options:
        return None
    if title:
        print(title)

    for num, od in enumerate(selectable_options, start=1):
        prefix = ""
        if od.children:
            prefix = "[+] " if od.collapsed else "[-] "
        print(f"  [{num}] {prefix}{od.title}")

    while True:
        try:
            raw = input("Select number (or 'q' to cancel): ").strip()
        except EOFError:
            return None
        if raw.lower() in {"q", "quit", "exit"}:
            return None
        if raw.isdigit():
            num = int(raw)
            if 1 <= num <= len(selectable_options):
                selected = selectable_options[num-1]
                if selected.children:
                    selected.collapsed = not selected.collapsed
                    # Recurse or re-render; for simplicity, we restart the selection
                    return _numeric_fallback(option_data, title)
                return selected
        print("Invalid choice. Enter a number from the list.")


__all__ = ["interactive_select_with_arrows", "OptionData"]
