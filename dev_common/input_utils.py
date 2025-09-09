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
from dev_common.constants import ARG_PATH_LONG, ARG_PATH_SHORT, ARG_PATHS_LONG, ARG_PATHS_SHORT, ARGUMENT_PREFIX, LINE_SEPARATOR
from dev_common.core_utils import LOG
from dev_common.file_utils import expand_and_check_path
from dev_common.gui_utils import _get_terminal_size
from dev_common.tools_utils import ToolTemplate

MENTION_SYMBOL = '@'


def replace_arg_paths_with_single_mention(default_input: str) -> str:
    """Replace existing paths in default input with 1 MENTION_SYMBOL (per path arg)."""
    if not default_input:
        return default_input
    try:
        parts = shlex.split(default_input)
    except ValueError:
        return default_input

    processed: List[str] = []
    part_index = 0
    while part_index < len(parts):
        part = parts[part_index]
        processed.append(part)
        part_index += 1

        # Check if this part is an argument prefix
        if is_path_arg(part):
            current_arg_index = 0
            found_existing_path = False
            # Process all following consecutive paths
            while part_index < len(parts):
                next_part = parts[part_index]

                # Stop if we hit another argument
                if next_part.startswith(ARGUMENT_PREFIX):
                    break

                # Check if this part is an existing path
                exists, _ = expand_and_check_path(next_part)
                if exists and current_arg_index == 0:
                    processed.append(f"{MENTION_SYMBOL}")
                    found_existing_path = True
                # Ignore non-existing paths or subsequent paths
                current_arg_index += 1
                part_index += 1

            # Ensure at least one MENTION_SYMBOL if no existing paths were found
            if not found_existing_path:
                processed.append(f"{MENTION_SYMBOL}")
    return shlex.join(processed)


def is_path_arg(part: str) -> bool:
    return part.startswith(ARG_PATH_LONG) or part.startswith(ARG_PATHS_LONG) or part.startswith(ARG_PATH_SHORT) or part.startswith(ARG_PATHS_SHORT)


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
        """Accepts a completion or a manually typed path and adds a space if valid."""
        buffer: Buffer = event.current_buffer
        completion = buffer.complete_state.current_completion if buffer.complete_state else None

        # If a completion is active, use its text. Otherwise, use the word before the cursor.
        target_txt = ""
        if completion:
            target_txt = completion.text
        else:
            target_txt = buffer.document.get_word_before_cursor(WORD=True)

        # It must start with the mention symbol to be processed.
        if target_txt and target_txt.startswith(MENTION_SYMBOL):
            # Extract the actual path string (remove the '@' symbol).
            potential_path = target_txt[len(MENTION_SYMBOL):]

            # Validate the path.
            path_is_valid, _ = expand_and_check_path(potential_path)

            # If the path is valid, add a trailing space for a smoother workflow.
            if path_is_valid:
                current_text = buffer.document.text
                cursor_pos = buffer.document.cursor_position
                # Only add a space if one isn't already there.
                if cursor_pos == len(current_text) or current_text[cursor_pos] != ' ':
                    buffer.insert_text(' ')

    @custom_keybindings.add(Keys.Enter, filter=has_completions)
    def _(event):
        accept_completion(event)

    @custom_keybindings.add(" ", filter=has_completions)  # Space key
    def _(event):
        accept_completion(event)

    try:
        # Preprocess default input: add mentions to existing paths
        default_with_mentions = replace_arg_paths_with_single_mention(default_input)
        LOG(LINE_SEPARATOR, show_time=False)
        user_input = prompt(
            message=f"{prompt_message} (use {MENTION_SYMBOL} to trigger fuzzy search path, search dir: {config.search_root}): ",
            default=default_with_mentions,
            completer=EnhancedPathCompleter(config=config),
            complete_while_typing=True,
            complete_style=CompleteStyle.COLUMN,
            key_bindings=custom_keybindings,  # Pass the custom key bindings to the prompt.
        ).strip()

        # --- Improvement: Post-process the input to clean up path mentions ---
        processed_parts = []
        input_parts = shlex.split(user_input)
        i = 0
        while i < len(input_parts):
            part = input_parts[i]
            processed_parts.append(part)
            i += 1  # Move index to the part *after* the argument flag

            # Check if the one u just add is an argument that takes paths, if yes then try process paths
            if is_path_arg(part):
                # Now, process all following parts until we hit another argument
                while i < len(input_parts):
                    path_candidate = input_parts[i]
                    # If we find another argument, stop processing paths for the previous one
                    if path_candidate.startswith(ARGUMENT_PREFIX):
                        break  # Exit inner loop; the outer loop will handle this new argument

                    # Check if it's a correctly formatted path mention
                    replaced = False
                    if path_candidate.startswith(MENTION_SYMBOL) and len(path_candidate) > 1:
                        potential_path = path_candidate[len(MENTION_SYMBOL):]
                        exists, _ = expand_and_check_path(potential_path)
                        if exists:
                            # Success: It's a valid path, so add it without the symbol
                            processed_parts.append(potential_path)
                            replaced = True

                    if not replaced:
                        processed_parts.append(path_candidate)
                    i += 1

        # Reconstruct the final string, correctly quoting any parts that contain spaces
        final_input = shlex.join(processed_parts)
        return final_input
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
