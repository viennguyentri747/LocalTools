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
    pattern: str
    search_path: Path
    ignore_case: bool
    literal: bool
    context: int
    max_depth: Optional[int]


@dataclass(frozen=True)
class SearchPattern:
    """Individual search pattern within a grouped search."""
    name: str
    regex_c_builder: Callable[[str, bool], str]
    description: str


TemplateBuilder = Callable[[TemplateArgs], Tuple[str, Optional[str]]]
GroupedTemplateBuilder = Callable[[TemplateArgs], List[Tuple[str, str, str]]]  # (command, category, description)


@dataclass(frozen=True)
class TemplateDefinition:
    """Template configuration."""
    key: str
    display_name: str
    description: str
    builder: TemplateBuilder
    file_exts: List[str]
    default_args: Dict[str, object]
    usage_note: str = ""
    is_grouped: bool = False


@dataclass(frozen=True)
class GroupedTemplateDefinition:
    """Grouped template configuration."""
    key: str
    display_name: str
    description: str
    patterns: List[SearchPattern]
    file_exts: List[str]
    default_args: Dict[str, object]
    usage_note: str = ""


def quote(s: str) -> str:
    return shlex.quote(s)


def build_symbol_regex(symbol: str, literal: bool, word_boundaries: bool = True) -> str:
    body = re.escape(symbol) if literal else symbol
    return rf"\b{body}\b" if word_boundaries else body


def build_rg_command(regex: str, args: TemplateArgs, file_exts: List[str], extra_flags: Optional[List[str]] = None) -> str:
    """Build ripgrep command with common options."""
    parts = ["rg", "-n"]

    if args.ignore_case:
        parts.append("-i")

    if args.context > 0:
        parts.extend(["-C", str(args.context)])

    # File type filtering
    if file_exts:
        for ext in file_exts:
            parts.extend(["-g", quote(f"*.{ext}")])

    if extra_flags:
        parts.extend(extra_flags)

    parts.extend(["-e", quote(regex), quote(str(args.search_path))])
    return " ".join(parts)


def build_fd_command(pattern: str, args: TemplateArgs) -> str:
    """Build fd command for file search."""
    parts = ["fd"]

    if args.ignore_case:
        parts.append("-i")

    if args.max_depth is not None:
        parts.extend(["-d", str(args.max_depth)])

    parts.extend(["-t", "f", quote(pattern), quote(str(args.search_path))])
    return " ".join(parts)


# Regex builders for different pattern types
def regex_c_function_definition(symbol: str, literal: bool) -> str:
    sym = build_symbol_regex(symbol, literal)
    pattern = (
        rf"^\s*"
        rf"(?:\[\[[\w\s:]+\]\]\s*)*"  # Attributes like [[nodiscard]]
        rf"(?:(?:static|extern|inline|virtual|explicit|constexpr|friend)\s+)*"
        rf"(?:(?:const|volatile)\s+)*"
        rf"[\w:]+"  # Base type
        rf"(?:\s*<[^>]+>)?"  # Template parameters
        rf"(?:\s*[\*&]+)*"
        rf"(?:\s+(?:const|volatile))*"
        rf"\s+"
        rf"{sym}"
        rf"\s*\("
    )

    return pattern


def regex_c_variable_definition(symbol: str, literal: bool) -> str:
    sym = build_symbol_regex(symbol, literal)
    return rf"^\s*(const|static|constexpr|extern|volatile|[\w:<>\[\]\s\*&]+)\s+{sym}\s*(=|;|\[)"


def regex_c_class_struct_definition(symbol: str, literal: bool) -> str:
    """Generates a regex to find C/C++ class or struct definitions."""
    symbol_name = build_symbol_regex(symbol, literal, word_boundaries=True)

    return (
        rf"^\s*"
        rf"(?:\[\[[\w\s:,()]+\]\]\s*)*"  # Attributes like [[nodiscard]]
        rf"(?:template\s*<[^>]*>\s*)?"  # Template declaration
        rf"(?:typedef\s+)?"  # Typedef keyword, Note for now only work if symbol in same line/section as typedef (at the start)
        rf"(?:(?:static|extern|inline|virtual|explicit|constexpr|friend)\s+)*"  # Storage/specifiers
        rf"(class|struct)"  # Class or struct keyword
        rf"(?:\s+(?:alignas|__declspec|__attribute__)\s*\([^)]*\))?"  # Attribute specifiers
        rf"(?:\s+(?:final|abstract))?"  # Class specifiers
        rf"\s+"
        rf"{symbol_name}"
        rf"\b"  # Word boundary
    )


def regex_c_macro_definition(symbol: str, literal: bool) -> str:
    sym = build_symbol_regex(symbol, literal)
    return rf"^\s*#\s*define\s+{sym}"


def regex_c_typedef_definition(symbol: str, literal: bool) -> str:
    """
    Generates a regex to find a C typedef definition for a given symbol.

    This version handles both:
    1. Single-line definitions (e.g., `typedef int my_int;`)
    2. The closing line of a multi-line struct, enum, or union
       (e.g., `} my_struct_t;`)
    """
    sym = build_symbol_regex(symbol, literal)

    # This pattern matches a line that either starts with `typedef`
    # OR starts with a closing brace `}` followed by the symbol.
    return rf"^(?:\s*typedef\s+.*?|\s*}})\s+{sym}\s*;"


def regex_c_enum_definition(symbol: str, literal: bool) -> str:
    sym = build_symbol_regex(symbol, literal, word_boundaries=False)
    return rf"^\s*enum\s+(class\s+)?{sym}\b"


def regex_c_function_call(symbol: str, literal: bool) -> str:
    sym = build_symbol_regex(symbol, literal)
    return rf"{sym}\s*\("


def regex_c_symbol_usage(symbol: str, literal: bool) -> str:
    return build_symbol_regex(symbol, literal)


# Grouped template builders
def build_grouped_search(args: TemplateArgs, patterns: List[SearchPattern], file_exts: List[str]) -> List[Tuple[str, str, str]]:
    """Build multiple search commands for grouped patterns."""
    results = []
    for pattern in patterns:
        regex = pattern.regex_c_builder(args.pattern, args.literal)
        command = build_rg_command(regex, args, file_exts)
        results.append((command, pattern.name, pattern.description))
    return results


# C/C++ Template builder functions (legacy single search)
def fn_c_function_call(args: TemplateArgs, file_exts: List[str]) -> Tuple[str, Optional[str]]:
    symbol = build_symbol_regex(args.pattern, args.literal)
    regex = rf"{symbol}\s*\("
    return build_rg_command(regex, args, file_exts), "Use --context to see call arguments"


def fn_c_variable_usage(args: TemplateArgs, file_exts: List[str]) -> Tuple[str, Optional[str]]:
    symbol = build_symbol_regex(args.pattern, args.literal)
    return build_rg_command(symbol, args, file_exts, ["--color=always"]), None


# Generic file search
def fn_file_name(args: TemplateArgs, file_exts: List[str]) -> Tuple[str, Optional[str]]:
    return build_fd_command(args.pattern, args), None


# Template definitions
C_CPP_EXTS = ["c", "cpp", "cc", "cxx", "h", "hpp", "hxx"]

# Grouped patterns
DEFINITION_PATTERNS = [
    SearchPattern("Function Definitions", regex_c_function_definition, "Function declarations"),
    SearchPattern("Variable Definitions", regex_c_variable_definition, "Variable/field declarations"),
    SearchPattern("Class/Struct Definitions", regex_c_class_struct_definition, "Class and struct declarations"),
    SearchPattern("Macro Definitions", regex_c_macro_definition, "#define preprocessor macros"),
    SearchPattern("Typedef Definitions", regex_c_typedef_definition, "Type alias declarations"),
    SearchPattern("Enum Definitions", regex_c_enum_definition, "Enumeration declarations"),
]

USAGE_PATTERNS = [
    SearchPattern("Function Calls", regex_c_function_call, "Function invocations"),
    SearchPattern("Symbol References", regex_c_symbol_usage, "All symbol references"),
]

# Grouped template definitions
GROUPED_TEMPLATES: Dict[str, GroupedTemplateDefinition] = {
    "c-all-definitions": GroupedTemplateDefinition(
        "c-all-definitions",
        "Find all C/C++ definitions",
        "Search for all types of definitions (functions, variables, classes, etc.)",
        DEFINITION_PATTERNS,
        C_CPP_EXTS,
        {"--pattern": "SymbolName", "--path": "~/core_repos/"},
        "Searches for all definition types and groups results by category",
    ),
    "c-all-usage": GroupedTemplateDefinition(
        "c-all-usage",
        "Find all C/C++ usage",
        "Search for all types of symbol usage (calls, references)",
        USAGE_PATTERNS,
        C_CPP_EXTS,
        {"--pattern": "SymbolName", "--path": "~/core_repos/"},
        "Searches for all usage types and groups results by category",
    ),
}

# Single search templates (legacy)
TEMPLATES: Dict[str, TemplateDefinition] = {
    "file-name": TemplateDefinition(
        "file-name",
        "Find files by name",
        "Locate files matching a pattern using fd",
        fn_file_name,
        [],
        {"--pattern": "partial_file_name", "--path": "~/core_repos/"},
        "Use --max-depth to limit recursion depth",
    ),
    "c-function-call": TemplateDefinition(
        "c-function-call",
        "Find C/C++ function calls",
        "Search for function invocations in C/C++ code",
        fn_c_function_call,
        C_CPP_EXTS,
        {"--pattern": "FunctionName", "--path": "~/core_repos/"},
        "Combine with --context for call site details",
    ),
}


def get_tool_templates() -> List[ToolTemplate]:
    """Generate examples for CLI help."""
    templates = []

    # Add grouped templates
    for tmpl in GROUPED_TEMPLATES.values():
        args = {"--template": tmpl.key}
        args.update({k: list(v) if isinstance(v, list) else v for k, v in tmpl.default_args.items()})
        templates.append(
            ToolTemplate(
                name=tmpl.display_name,
                extra_description=tmpl.description,
                args=args,
                usage_note=tmpl.usage_note,
            )
        )

    # Add single templates
    for tmpl in TEMPLATES.values():
        args = {"--template": tmpl.key}
        args.update({k: list(v) if isinstance(v, list) else v for k, v in tmpl.default_args.items()})
        templates.append(
            ToolTemplate(
                name=tmpl.display_name,
                extra_description=tmpl.description,
                args=args,
                usage_note=tmpl.usage_note,
            )
        )
    return templates


def parse_args() -> argparse.Namespace:
    all_templates = list(GROUPED_TEMPLATES.keys()) + list(TEMPLATES.keys())
    parser = argparse.ArgumentParser(
        description="Generate ripgrep/fd command templates for code search",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=build_examples_epilog(get_tool_templates(), Path(__file__)),
    )

    parser.add_argument("--template", choices=all_templates, required=True, help="Template to use")
    parser.add_argument("--pattern", default="SYMBOL_NAME", help="Symbol or pattern to search")
    parser.add_argument("--path", default=".", help="Root search path (default: current directory)")
    parser.add_argument("--ignore-case", action="store_true", help="Case-insensitive search")
    parser.add_argument("--regex", action="store_true", help="Treat pattern as regex (default: literal)")
    parser.add_argument("--context", type=int, default=0, help="Lines of context around matches")
    parser.add_argument("--max-depth", type=int, help="Max directory depth for file search")
    parser.add_argument("--no-copy", action="store_true", help="Don't copy to clipboard")

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    template_args = TemplateArgs(
        pattern=args.pattern,
        search_path=Path(args.path).expanduser(),
        ignore_case=args.ignore_case,
        literal=not args.regex,
        context=args.context,
        max_depth=args.max_depth,
    )

    # Check if it's a grouped template
    if args.template in GROUPED_TEMPLATES:
        tmpl = GROUPED_TEMPLATES[args.template]
        results = build_grouped_search(template_args, tmpl.patterns, tmpl.file_exts)

        LOG(f"{LOG_PREFIX_MSG_INFO} {tmpl.display_name}")
        LOG(f"{LOG_PREFIX_MSG_INFO} {tmpl.description}\n")

        # Build combined command with conditional echo statements
        command_parts = []
        for command, category, description in results:
            # This logic captures rg's output and only prints the header if it's not empty.
            conditional_command = (
                f"output=$({command}); "
                f'if [ -n "$output" ]; then '
                f'echo -e "\\n=== {category} ({description}) ==="; '
                'echo "$output"; '
                "fi"
            )
            command_parts.append(conditional_command)

        # Join with semicolons for sequential execution
        full_output = "; ".join(command_parts)

        LOG(f"Combined command:\n{full_output}\n")

        display_content_to_copy(
            full_output,
            purpose="Run all searches in one command",
            is_copy_to_clipboard=not args.no_copy,
            extra_prefix_descriptions=f"{tmpl.display_name}\n{tmpl.description}",
        )

        if tmpl.usage_note:
            LOG(f"{LOG_PREFIX_MSG_INFO} Note: {tmpl.usage_note}")

    # Single template
    elif args.template in TEMPLATES:
        tmpl = TEMPLATES[args.template]
        command, note = tmpl.builder(template_args, tmpl.file_exts)

        LOG(f"{LOG_PREFIX_MSG_INFO} Generated command:\n{command}")

        display_content_to_copy(
            command,
            purpose="Run search command",
            is_copy_to_clipboard=not args.no_copy,
            extra_prefix_descriptions=f"{tmpl.display_name}\n{tmpl.description}",
        )

        notes = [n for n in [tmpl.usage_note, note] if n]
        if notes:
            LOG(f"{LOG_PREFIX_MSG_INFO} Notes:\n- " + "\n- ".join(notes))

    else:
        LOG(f"{LOG_PREFIX_MSG_ERROR} Unknown template '{args.template}'")


if __name__ == "__main__":
    main()
