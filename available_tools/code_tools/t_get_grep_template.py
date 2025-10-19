#!/home/vien/local_tools/MyVenvFolder/bin/python
from __future__ import annotations
import argparse
import re
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple
from dev_common import *


@dataclass(frozen=True)
class TemplateArgs:
    """Context passed to template builders."""
    search_path: Path
    ignore_case: bool
    literal: bool
    context: int
    max_depth: Optional[int]
    pattern: Optional[str] = None


@dataclass(frozen=True)
class SearchPattern:
    """Individual search pattern within a grouped search."""
    name: str
    regex_c_builder: Callable[[str, bool], str]
    description: str


TemplateBuilder = Callable[[TemplateArgs], Tuple[str, Optional[str]]]
ARG_DISPLAY_NAME = f"{ARGUMENT_LONG_PREFIX}display-name"
ARG_SEARCH_MODE = f"{ARGUMENT_LONG_PREFIX}search-mode"
ARG_PATTERN_KEYS = f"{ARGUMENT_LONG_PREFIX}pattern-keys"
ARG_FILE_EXTS = f"{ARGUMENT_LONG_PREFIX}file-exts"
ARG_CASE_SENSITIVE = f"{ARGUMENT_LONG_PREFIX}case-sensitive"
ARG_REGEX = f"{ARGUMENT_LONG_PREFIX}regex"
ARG_CONTEXT = f"{ARGUMENT_LONG_PREFIX}context"
ARG_MAX_DEPTH = f"{ARGUMENT_LONG_PREFIX}max-depth"
ARG_NO_COPY = f"{ARGUMENT_LONG_PREFIX}no-copy"

SEARCH_MODE_SYMBOL = "fzf-symbols"
SEARCH_MODE_FILE = "fzf-files"
SEARCH_MODE_TEXT = "fzf-text"


def quote(s: str) -> str:
    return shlex.quote(s)


def build_rg_base_command(args: TemplateArgs, file_exts: List[str]) -> str:
    """Build the reusable portion of the ripgrep command."""
    parts = ["rg", "--color=always", "-n"]

    if args.literal:
        parts.append("-F")  # Use fixed-string (literal) search
    else:
        parts.append("-P")  # Use Perl regex (original default )

    if args.ignore_case:
        parts.append("-i")

    if args.context > 0:
        parts.extend(["-C", str(args.context)])

    if file_exts:
        for ext in file_exts:
            parts.extend(["-g", f"*.{ext}"])

    return " ".join(quote(part) for part in parts)


def build_fzf_rgrep_command(description: str, template_args: TemplateArgs, patterns: List[SearchPattern], file_exts: List[str], initial_query: str = "") -> str:
    """Build the fzf command with a search_symbol shell function as a one-liner."""
    base_rg_command = build_rg_base_command(template_args, file_exts)
    search_dir = str(template_args.search_path)
    search_dir_arg = quote(search_dir)

    def shell_regex(regex_template: str) -> str:
        """Convert the template regex into something safe for double-quoted shell usage."""
        escaped = regex_template.replace("\\", "\\\\").replace('"', '\\"')
        return escaped.replace("SYMBOL_PLACEHOLDER", "${symbol}")

    command_parts = []
    for pattern in patterns:
        regex_template = pattern.regex_c_builder("SYMBOL_PLACEHOLDER", template_args.literal)
        regex_expression = shell_regex(regex_template)

        conditional_command = (
            # Using --color=always ensures the output is colored even when piped.
            f'output=$({base_rg_command} -e "{regex_expression}" {search_dir_arg} 2>/dev/null); '
            f'if [ -n "$output" ]; then '
            f'echo "$output"; '
            f'fi'
        )
        command_parts.append(conditional_command)

    search_function_body = "; ".join(command_parts)

    initial_query_arg = f'--query {quote(initial_query)}' if initial_query else ''

    fzf_runner = (
        f'echo "" | fzf '
        f'--header "{description}. Type to start searching ..." '
        f'--prompt "Symbol> " '
        f'{initial_query_arg} '
        f'--print-query '
        f'--bind "change:reload:search_symbol {{q}}" '
        f'--preview-window "up:80%" '
        # --ansi tells fzf to interpret the color codes from rg.
        f'--ansi --disabled --no-sort'
    )

    # MODIFICATION: Simplified final output with color.
    fzf_command = (
        # Define color variables for the final output.
        f"GREEN='\\033[0;32m'; "  # Actually yellow?
        f"NC='\\033[0m'; "  # No Color (to reset the terminal).
        f'SEARCH_DIR="{search_dir}"; '
        f'search_symbol() {{ '
        f'local symbol="$1"; '
        f'if [ -z "$symbol" ]; then echo "Type a symbol name to search..."; return; fi; '
        f'local output; '
        f'{search_function_body} '
        f'}}; '
        f'export -f search_symbol; '
        f'export SEARCH_DIR; '
        f'selection=$({fzf_runner}); '
        f'if [ -n "$selection" ]; then '
        # The symbol is the first line of the output (as we use print-query).
        f'  symbol=$(echo "$selection" | head -n 1); '
        # The line from rg already has colors, so we just print it.
        f'  line=$(echo "$selection" | tail -n 1); '
        # Use `echo -e` to add color to the labels.
        f'  echo -e "${{GREEN}}Selected Symbol:${{NC}} $symbol"; '
        f'  echo -e "${{GREEN}}Selected line:${{NC}}   $line"; '
        f'else '
        f'  echo -e "${{GREEN}}No selection made!${{NC}}"; '
        f'fi; '
    )

    return fzf_command


def build_fzf_fd_command(search_dir: str, initial_query: str = "") -> str:
    """Builds an fzf command that uses fd for file searching."""
    return (
        f'fd --type f . "{search_dir}" | fzf '
        f'--header "Find files by name. Press Enter to open in editor." '
        f'--prompt "File> " '
        f'--query "{initial_query}"'
    )


def build_fd_command(pattern: str, args: TemplateArgs) -> str:
    """Build fd command for file search."""
    parts = ["fd"]

    if args.ignore_case:
        parts.append("-i")

    if args.max_depth is not None:
        parts.extend(["-d", str(args.max_depth)])

    parts.extend(["-t", "f", quote(pattern), quote(str(args.search_path))])
    return " ".join(parts)


def _regex_not_c_keyword_prefix() -> str:
    """
    Common negative-lookahead cluster to exclude non-target lines
    """
    parts = [
        rf"(?!return\s*)",        # Not a return statement
        rf"(?!if\s*)",            # Not an if statement
        rf"(?!while\s*)",         # Not a while loop
        rf"(?!for\s*)",           # Not a for loop
        rf"(?!switch\s*)",        # Not a switch statement
        rf"(?!case\s+)",          # Not a case label
        rf"(?!goto\s+)",          # Not a goto statement
        rf"(?!do\s*)",            # Not a do-while loop start
        rf"(?!try\s*)",           # Not a try block
        rf"(?!catch\s*)",         # Not a catch block
        rf"(?!else\s*)",          # Not an else/else-if
        rf"(?!delete\s*)",        # Not a delete statement
        rf"(?!new\s*)",           # Not a 'new' expression statement
    ]

    return "".join(parts)


def regex_c_function_definition(symbol: str, literal: bool) -> str:
    """
    Matches a likely C/C++ *definition* header line for a function whose name
    starts with `symbol` (or exactly equals if literal=True).
    Keeps your original
    shape but uses the shared negative-lookahead cluster.
    """
    sym = build_symbol_regex(symbol, literal, just_match_prefix=True)
    pattern = (
        rf"^\s*"
        rf"{_regex_not_c_keyword_prefix()}"
        rf"(?:\[\[[\w\s:]+\]\]\s*)*"                # [[attributes]]
        rf"(?:(?:static|extern|inline|virtual|explicit|constexpr|friend)\s+)*"
        rf"(?:(?:const|volatile)\s+)*"
        rf"[\w:]+"                                  # base type
        rf"(?:\s*<[^>]+>)?"                         # template params
        rf"(?:\s*[\*&]+)*"                          # ptr/ref qualifiers
        rf"(?:\s+(?:const|volatile))*"              # trailing cv
        rf"\s+"
        rf"{sym}"
        rf"\s*\("                                    # open paren for params
    )
    return pattern


def regex_c_variable_definition(symbol: str, literal: bool) -> str:
    """
    Matches a C/C++ variable definition/declaration line for a name starting
    with `symbol` (or exact if literal=True). Uses the shared exclusions.
    """
    sym = build_symbol_regex(symbol, literal, just_match_prefix=True)
    return (
        rf"^\s*"
        rf"{_regex_not_c_keyword_prefix()}"
        rf"(const|static|constexpr|extern|volatile|[\w:<>\[\]\s\*&]+)\s+{sym}\s*(=|;|\[)"
    )


def regex_c_class_struct_definition(symbol: str, literal: bool) -> str:
    """Generates a regex to find C/C++ class or struct definitions."""
    symbol_name = build_symbol_regex(symbol, literal, word_boundaries=True, just_match_prefix=True)

    return (
        rf"^\s*"
        rf"(?:\[\[[\w\s:,()]+\]\]\s*)*"  # Attributes like [[nodiscard]]
        rf"(?:template\s*<[^>]*>\s*)?"  # Template declaration
        rf"(?:typedef\s+)?"  # Typedef keyword
        rf"(?:(?:static|extern|inline|virtual|explicit|constexpr|friend)\s+)*"  # Storage/specifiers
        rf"(class|struct)"  # Class or struct keyword
        rf"(?:\s+(?:alignas|__declspec|__attribute__)\s*\([^)]*\))?"  # Attribute specifiers
        rf"(?:\s+(?:final|abstract))?"  # Class specifiers
        rf"\s+"
        rf"{symbol_name}"
        rf"\b"
    )


def regex_c_macro_definition(symbol: str, literal: bool) -> str:
    sym = build_symbol_regex(symbol, literal, just_match_prefix=True)
    return rf"^\s*#\s*define\s+{sym}\b"


def regex_c_typedef_definition(symbol: str, literal: bool) -> str:
    """
    Generates a regex to find a C typedef definition for a given symbol.
    This version handles both:
    1. Single-line definitions (e.g., `typedef int my_int;`)
    2. The closing line of a multi-line struct, enum, or union
       (e.g., `} my_struct_t;`)
    """
    sym = build_symbol_regex(symbol, literal, just_match_prefix=True)

    # This pattern matches a line that either starts with `typedef`
    # OR starts with a closing brace `}` followed by the symbol.
    return rf"^(?:\s*typedef\s+.*?|\s*}})\s+{sym}\s*;"


def regex_c_enum_definition(symbol: str, literal: bool) -> str:
    sym = build_symbol_regex(symbol, literal, word_boundaries=False, just_match_prefix=True)
    return rf"^\s*enum\s+(class\s+)?{sym}\b"


def regex_c_enum_value_definition(symbol: str, literal: bool) -> str:
    """
    Generates a regex to match an enum value definition line in C/C++.
    Examples matched:
        VALUE_A,
        VALUE_B=3,    // or VALUE_B = (1 << 4),
        VALUE_C,      // with space or trailing comma
    """
    sym = build_symbol_regex(symbol, literal, word_boundaries=False, just_match_prefix=True)
    # Match beginning of line or after comma, optional spaces, then symbol, optionally followed by = and an expression
    optional_enum_assigment = rf"(?:=\s*[^,]*?)?"
    return rf"^\s*{sym}\s*{optional_enum_assigment}\s*,?\s*$"


def regex_c_function_call(symbol: str, literal: bool) -> str:
    sym = build_symbol_regex(symbol, literal, just_match_prefix=True)
    return rf"{sym}\s*\("


def regex_c_symbol_usage(symbol: str, literal: bool) -> str:
    return build_symbol_regex(symbol, literal, just_match_prefix=True)


def build_symbol_regex(symbol: str, literal: bool, word_boundaries: bool = True, just_match_prefix: bool = False) -> str:
    """
    Builds a regex for a symbol with optional word boundaries and prefix matching.

    Args:
        symbol: The symbol to search for.
        literal: If True, treats the symbol as a literal string; otherwise, as a regex.
        word_boundaries: If True, ensures the symbol is matched as a whole word.
        just_match_prefix: If True, matches symbols that start with the given pattern. Don't haven to match the full symbol.
    Returns:
        A regex string tailored to the provided specifications.
    """
    body = re.escape(symbol) if literal else symbol

    if just_match_prefix:
        if literal:
            body = rf"{body}\w*"
        else:
            body = rf"(?:{body})\w*"

    return rf"\b{body}\b" if word_boundaries else body


# Template definitions
C_CPP_EXTS = ["c", "cpp", "cc", "cxx", "h", "hpp", "hxx"]

PATTERN_KEY_FUNCTION_DEFINITION = "c-function-definition"
PATTERN_KEY_VARIABLE_DEFINITION = "c-variable-definition"
PATTERN_KEY_CLASS_STRUCT_DEFINITION = "c-class-struct-definition"
PATTERN_KEY_MACRO_DEFINITION = "c-macro-definition"
PATTERN_KEY_TYPEDEF_DEFINITION = "c-typedef-definition"
PATTERN_KEY_ENUM_DEFINITION = "c-enum-definition"
PATTERN_KEY_ENUM_VALUE_DEFINITION = "c-enum-value-definition"
PATTERN_KEY_FUNCTION_CALL = "c-function-call"
PATTERN_KEY_SYMBOL_USAGE = "c-symbol-usage"

PATTERN_REGISTRY: Dict[str, SearchPattern] = {
    PATTERN_KEY_FUNCTION_DEFINITION: SearchPattern("Function Definitions", regex_c_function_definition, "Function declarations"),
    PATTERN_KEY_VARIABLE_DEFINITION: SearchPattern("Variable Definitions", regex_c_variable_definition, "Variable/field declarations"),
    PATTERN_KEY_CLASS_STRUCT_DEFINITION: SearchPattern("Class/Struct Definitions", regex_c_class_struct_definition, "Class and struct declarations"),
    PATTERN_KEY_MACRO_DEFINITION: SearchPattern("Macro Definitions", regex_c_macro_definition, "#define preprocessor macros"),
    PATTERN_KEY_TYPEDEF_DEFINITION: SearchPattern("Typedef Definitions", regex_c_typedef_definition, "Type alias declarations"),
    PATTERN_KEY_ENUM_DEFINITION: SearchPattern("Enum Definitions", regex_c_enum_definition, "Enumeration declarations"),
    PATTERN_KEY_ENUM_VALUE_DEFINITION: SearchPattern("Enum Value Definitions", regex_c_enum_value_definition, "Enumeration value declarations"),
    PATTERN_KEY_FUNCTION_CALL: SearchPattern("Function Calls", regex_c_function_call, "Function invocations"),
    PATTERN_KEY_SYMBOL_USAGE: SearchPattern("Symbol References", regex_c_symbol_usage, "All symbol references"),
}

DEFINITION_PATTERN_KEYS = [
    PATTERN_KEY_FUNCTION_DEFINITION,
    PATTERN_KEY_VARIABLE_DEFINITION,
    PATTERN_KEY_CLASS_STRUCT_DEFINITION,
    PATTERN_KEY_MACRO_DEFINITION,
    PATTERN_KEY_TYPEDEF_DEFINITION,
    PATTERN_KEY_ENUM_DEFINITION,
    PATTERN_KEY_ENUM_VALUE_DEFINITION,
]

USAGE_PATTERN_KEYS = [
    PATTERN_KEY_FUNCTION_CALL,
    PATTERN_KEY_SYMBOL_USAGE,
]


def resolve_patterns(pattern_keys: List[str]) -> Tuple[List[SearchPattern], List[str]]:
    """Resolve pattern keys to SearchPattern objects."""
    resolved: List[SearchPattern] = []
    missing: List[str] = []
    for key in pattern_keys:
        pattern = PATTERN_REGISTRY.get(key)
        if pattern is None:
            missing.append(key)
        else:
            resolved.append(pattern)
    return resolved, missing


def get_tool_templates() -> List[ToolTemplate]:
    """Generate examples for CLI help."""
    return [
        ToolTemplate(
            name="Fzf C/C++ definitions",
            extra_description="Interactively search definitions (functions, variables, etc.) using fzf",
            args={
                ARG_DISPLAY_NAME: "Fzf C/C++ definitions (functions, variables, etc.)",
                ARG_SEARCH_MODE: SEARCH_MODE_SYMBOL,
                ARG_PATTERN_KEYS: DEFINITION_PATTERN_KEYS,
                ARG_FILE_EXTS: C_CPP_EXTS,
                ARG_PATH_LONG: "~/core_repos/",
            },
            should_run_now=True,
        ),
        ToolTemplate(
            name="Fzf C/C++ symbol usages",
            extra_description="Interactively search symbol usages (function calls, references, etc.) using fzf",
            args={
                ARG_DISPLAY_NAME: "Fzf C/C++ symbol usages (function calls, references, etc.)",
                ARG_SEARCH_MODE: SEARCH_MODE_SYMBOL,
                ARG_PATTERN_KEYS: USAGE_PATTERN_KEYS,
                ARG_FILE_EXTS: C_CPP_EXTS,
                ARG_PATH_LONG: "~/core_repos/",
            },
            should_run_now=True,
        ),
        ToolTemplate(
            name="Fzf file name",
            extra_description="Interactively search for files by name using fd and fzf.",
            args={
                ARG_DISPLAY_NAME: "Fzf file name",
                ARG_SEARCH_MODE: SEARCH_MODE_FILE,
                ARG_PATH_LONG: "~/core_repos/",
            },
            should_run_now=True,
        ),
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate ripgrep/fd command templates for code search",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=build_examples_epilog(get_tool_templates(), Path(__file__)),
    )

    parser.add_argument(ARG_DISPLAY_NAME, default="", help="Display name for the interactive command header.")
    parser.add_argument(ARG_SEARCH_MODE, choices=[SEARCH_MODE_SYMBOL, SEARCH_MODE_FILE], required=True,
                        help="Search mode to execute.")
    parser.add_argument(ARG_PATTERN_KEYS, nargs='*', default=[],
                        help="Pattern keys to include when using symbol search.")
    parser.add_argument(ARG_FILE_EXTS, nargs='*', default=[],
                        help="File extensions to filter when searching with ripgrep.")
    parser.add_argument(ARG_PATH_LONG, default=".", help="Root search path (default: current directory)")

    parser.add_argument(ARG_CASE_SENSITIVE, type=lambda x: x.lower() == TRUE_STR_VALUE, default=False,
                        help="Enable case-sensitive search (true or false). Default: false (i.e., ignore case).")
    parser.add_argument(ARG_REGEX, type=lambda x: x.lower() == TRUE_STR_VALUE, default=False,
                        help="Treat pattern as regex (true or false). Default: false (i.e., literal search).")
    parser.add_argument(ARG_CONTEXT, type=int, default=0, help="Lines of context around matches")
    parser.add_argument(ARG_MAX_DEPTH, type=int, help="Max directory depth for file search")
    parser.add_argument(ARG_NO_COPY, type=lambda x: x.lower() == TRUE_STR_VALUE, default=False,
                        help="Don't copy to clipboard (true or false). Default: false.")

    parser.add_argument("pattern", nargs="?", default=None,
                        help="Symbol or pattern to search (optional, used for initial query in some templates)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    search_mode = get_arg_value(args, ARG_SEARCH_MODE)
    display_name = get_arg_value(args, ARG_DISPLAY_NAME) or "Interactive search"
    pattern_keys = get_arg_value(args, ARG_PATTERN_KEYS) or []
    file_exts = get_arg_value(args, ARG_FILE_EXTS) or []

    search_path_value = get_arg_value(args, ARG_PATH_LONG)
    ignore_case = not bool(get_arg_value(args, ARG_CASE_SENSITIVE))
    literal = not bool(get_arg_value(args, ARG_REGEX))
    context_value = get_arg_value(args, ARG_CONTEXT)
    max_depth_value = get_arg_value(args, ARG_MAX_DEPTH)
    pattern_value = get_arg_value(args, "pattern")

    template_args = TemplateArgs(
        pattern=pattern_value,
        search_path=Path(search_path_value).expanduser(),
        ignore_case=ignore_case,
        literal=literal,
        context=context_value,
        max_depth=max_depth_value,
    )

    if search_mode == SEARCH_MODE_FILE:
        full_output = build_fzf_fd_command(str(template_args.search_path), initial_query=template_args.pattern or "")
    elif search_mode == SEARCH_MODE_SYMBOL:
        resolved_patterns, missing_keys = resolve_patterns(pattern_keys)
        if missing_keys:
            LOG(f"{LOG_PREFIX_MSG_ERROR} Unknown pattern keys: {', '.join(missing_keys)}")
            return
        if not resolved_patterns:
            LOG(f"{LOG_PREFIX_MSG_ERROR} No patterns provided for symbol search.")
            return

        placeholder_args = TemplateArgs(
            pattern="SYMBOL_PLACEHOLDER",
            search_path=template_args.search_path,
            ignore_case=template_args.ignore_case,
            literal=template_args.literal,
            context=template_args.context,
            max_depth=template_args.max_depth,
        )

        full_output = build_fzf_rgrep_command(display_name, placeholder_args,
                                              resolved_patterns, file_exts, initial_query=template_args.pattern or "")
    else:
        LOG(f"{LOG_PREFIX_MSG_ERROR} Unsupported search mode '{search_mode}'")
        return

    LOG(f"{display_name} -> launching interactive search")
    run_shell(["bash", "-lc", full_output], shell=False, show_cmd=False)


if __name__ == "__main__":
    main()
