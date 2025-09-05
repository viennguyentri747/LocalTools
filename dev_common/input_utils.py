from asyncio import sleep
import shlex
from typing import Optional, List, Tuple, Callable

import os
from pathlib import Path
from prompt_toolkit import prompt
from prompt_toolkit.completion import PathCompleter, Completer, Completion
from prompt_toolkit.shortcuts import CompleteStyle
from prompt_toolkit.key_binding.key_processor import KeyPressEvent
from prompt_toolkit.document import Document
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.application import get_app
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.layout.containers import Window
from prompt_toolkit.layout.controls import BufferControl
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.application import Application


# Added for custom key bindings
from prompt_toolkit.filters import has_completions
from prompt_toolkit.keys import Keys


from dev_common.algo_utils import PathSearchConfig, fuzzy_find_paths
from dev_common.gui_utils import _get_terminal_size
from dev_common.tools_utils import ToolTemplate

MENTION_SYMBOL = '@'


def prompt_confirmation(message: str) -> bool:
    """Prompt the user for a yes/no confirmation."""
    while True:
        response = input(f"{message} (y/n): ").strip().lower()
        if response in ('y', 'yes'):
            return True
        elif response in ('n', 'no'):
            return False
        else:
            print("Please enter 'y' or 'n'.")


class EnhancedPathCompleter(Completer):
    """Enhanced completer that handles both MENTION_SYMBOL triggers and regular path completion."""

    def __init__(self, config: PathSearchConfig):
        self.config = config
        self.path_completer = PathCompleter(expanduser=True)
        self._cache = {}
        self._cache_size_limit = 100
        self.fuzzy_mode = False
        self.fuzzy_query_start = 0

    def _get_fuzzy_paths(self, query: str) -> List[Path]:
        """Get fuzzy paths with simple caching."""
        if query in self._cache:
            return self._cache[query]

        if len(self._cache) >= self._cache_size_limit:
            self._cache.clear()

        paths = fuzzy_find_paths(query, self.config)
        self._cache[query] = paths
        return paths

    def get_completions(self, document: Document, complete_event):
        text = document.text
        cursor_pos = document.cursor_position

        # Find the last MENTION_SYMBOL symbol before cursor
        at_pos = text.rfind(MENTION_SYMBOL, 0, cursor_pos)

        if at_pos != -1:
            # We're in fuzzy mode - everything after MENTION_SYMBOL is the query
            query = text[at_pos + 1:cursor_pos]

            # If query is empty, show help
            if not query:
                yield Completion(text="", start_position=0, display="🔍 Type to search files/directories...",)
                return

            # Check if there's a space after @, which would end fuzzy mode
            space_after_at = text.find(' ', at_pos)
            if space_after_at != -1 and space_after_at < cursor_pos:
                # Space found between MENTION_SYMBOL and cursor, not in fuzzy mode
                yield from self.path_completer.get_completions(document, complete_event)
                return

            # Use 80% of terminal width for the completion menu
            display_width = int(_get_terminal_size()[1] * 0.4)

            # 1. Get fuzzy-matched paths
            try:
                paths = self._get_fuzzy_paths(query)
            except Exception:
                return

            for p in paths:
                rel_path_str = str(p.relative_to(self.config.search_root))

                # 2. Use the helper to create a useful, truncated display string
                truncated_display_path = _truncate_path_middle(rel_path_str, display_width)

                icon = "📄" if p.is_file() else "📁"
                display_suffix = "/" if p.is_dir() else ""
                display_text = f"{icon} {truncated_display_path}{display_suffix}"

                replacement_text = f"{MENTION_SYMBOL}{str(p)}"
                start_position = at_pos - cursor_pos

                yield Completion(
                    text=replacement_text,
                    start_position=start_position,
                    display=display_text,  # Use the new truncated text here
                )
        else:
            # Regular path completion
            yield from self.path_completer.get_completions(document, complete_event)


def _truncate_path_middle(path_str: str, max_len: int) -> str:
    """
    Truncates a string in the middle, keeping the start and end.
    e.g., 'a/very/long/path/to/a/file.txt' -> 'a/very/.../to/a/file.txt'
    """
    if len(path_str) <= max_len:
        return path_str

    # Prioritize showing more of the end of the path
    head_len = int(max_len * 0.4)
    tail_len = max_len - head_len - 3  # -3 for '...'

    if head_len + tail_len < len(path_str):
        return f"{path_str[:head_len]}...{path_str[-tail_len:]}"
    return path_str


def prompt_input_with_paths(
    prompt_message: str,
    default_input: str = "",
    config: PathSearchConfig = PathSearchConfig()
) -> Optional[str]:
    """
    Enhanced input prompt with MENTION_SYMBOL trigger for fuzzy path insertion.

    When user types MENTION_SYMBOL followed by search terms, it will show fuzzy matches.
    User can have multiple MENTION_SYMBOL triggers in the same input.
    """
    # Create custom key bindings to change Enter key behavior during completion.
    custom_keybindings = KeyBindings()

    def accept_completion(event: KeyPressEvent):
        """Accept the currently selected completion in the completion menu (for Enter and Space keys).
        Removes the mention symbol before inserting the completion."""
        buffer: Buffer = event.current_buffer
        completion = buffer.complete_state.current_completion if buffer.complete_state else None
        if completion is None:
            return

        # Find mention symbol position
        text_before_cursor = buffer.document.text_before_cursor
        at_pos = text_before_cursor.rfind(MENTION_SYMBOL)
        is_fuzzy_completion = at_pos != -1

        if is_fuzzy_completion:
            # Delete mention symbol + whatever was typed after it, all at once! then insert the completion.
            ########
            # chars_to_delete = len(text_before_cursor) - at_pos
            # buffer.delete_before_cursor(chars_to_delete)
            # insert_text = completion.text
            # if insert_text.startswith(MENTION_SYMBOL):
            #     insert_text = insert_text[len(MENTION_SYMBOL):]
            # buffer.insert_text(insert_text)
            ########

            # Add a space if none exists after cursor
            current_text = buffer.document.text
            cursor_pos = buffer.document.cursor_position
            if cursor_pos < len(current_text) and current_text[cursor_pos] != ' ':
                buffer.insert_text(' ')
            elif cursor_pos == len(current_text):
                buffer.insert_text(' ')

    @custom_keybindings.add(Keys.Enter, filter=has_completions)
    def _(event):
        accept_completion(event)

    @custom_keybindings.add(" ", filter=has_completions)
    def _(event):
        accept_completion(event)

    # Updated help text to reflect the new behavior.
    help_text = f"💡 Use '{MENTION_SYMBOL}' for fuzzy path search. Press Enter on a suggestion to select it and continue typing."
    print(help_text)

    try:
        user_input = prompt(
            f"{prompt_message} (use {MENTION_SYMBOL} to trigger fuzzy search path, search dir: {config.search_root}): ",
            default=default_input,
            completer=EnhancedPathCompleter(config=config),
            complete_while_typing=True,
            complete_style=CompleteStyle.COLUMN,
            key_bindings=custom_keybindings,  # Pass the custom key bindings to the prompt.
        ).strip()

        # --- Improvement: Post-process the input to clean up path mentions ---
        processed_parts = []
        # Use shlex to correctly split the input, handling quoted paths with spaces
        input_parts = shlex.split(user_input)

        for part in input_parts:
            added: bool = False
            if part.startswith(MENTION_SYMBOL) and len(part) > 1:
                potential_path = part[len(MENTION_SYMBOL):]
                # Expand user home directory (e.g., '~') and check if the path exists
                expanded_path = os.path.expanduser(potential_path)
                if os.path.exists(expanded_path):
                    # If it's a valid path, add the clean path string
                    processed_parts.append(potential_path)
                    added = True

            if not added:
                # Add all other parts as they are
                processed_parts.append(part)

        # Reconstruct the final string, correctly quoting any parts that contain spaces
        final_input = shlex.join(processed_parts)
        return final_input

        return user_input if user_input else None
    except KeyboardInterrupt:
        print("\n❌ Cancelled")
        return None
    except EOFError:
        return None


def test_input_with_path():
    print("=" * 60)


if __name__ == "__main__":
    print("🚀 Enhanced Fuzzy Path Completer with MENTION_SYMBOL Trigger (Fixed)")
    print("=" * 60)

    while True:
        # Simplified loop for testing
        test_input_with_path()
        if not prompt_confirmation("Run another test?"):
            break
