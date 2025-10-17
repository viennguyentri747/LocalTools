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
GroupedTemplateBuilder = Callable[[TemplateArgs], List[Tuple[str, str, str]]]  # (command, category, description)


@dataclass(frozen=True)
class TemplateDefinition:
    """Template configuration."""
    key: str
    display_name: str
    description: str
    file_exts: List[str]
    default_args: Dict[str, object]
    usage_note: str = ""


@dataclass(frozen=True)
class GroupedTemplateDefinition:
    """Grouped template configuration."""
    key: str
    display_name: str
    description: str
    patterns: List[SearchPattern]
    file_exts: List[str]
    default_args: Dict[str, object]


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


def build_fzf_command(
    description: str, grouped_patterns: List[Tuple[str, str, str]], search_dir: str, file_exts: List[str]
) -> str:
    """Build the fzf command with a search_symbol shell function as a one-liner."""
    rg_file_exts_str = " ".join([f"-g '*.{ext}'" for ext in file_exts])

    command_parts = []
    for rg_command, category, _ in grouped_patterns:
        # Extract regex from the original rg_command
        match = re.search(r"-e\s+'([^']*)'", rg_command)
        if not match:
            continue
        regex = match.group(1)
        
        # Replace the placeholder with the shell variable `${symbol}`
        regex_prefix = regex.replace(r'SYMBOL_PLACEHOLDER', r'${symbol}')

        conditional_command = (
            f'output=$(rg -n {rg_file_exts_str} -e "{regex_prefix}" "{search_dir}" 2>/dev/null); '
            f'if [ -n "$output" ]; then '
            # f'echo "=== {category} ==="; '
            f'echo "$output"; '
            f'fi'
        )
        command_parts.append(conditional_command)

    search_function_body = "; ".join(command_parts)

    # Build as a one-liner without line breaks or escaping
    fzf_command = (
        f'SEARCH_DIR="{search_dir}"; '
        f'search_symbol() {{ '
        f'local symbol="$1"; '
        f'if [ -z "$symbol" ]; then '
        f'echo "Type a symbol name to search..."; '
        f'return; '
        f'fi; '
        f'local output; '
        f'{search_function_body} '
        f'}}; '
        f'export -f search_symbol; '
        f'export SEARCH_DIR; '
        f'echo "" | fzf '
        f'--header "{description}. Type to start searching ..." '
        f'--prompt "Symbol> " '
        f'--print-query '
        f'--bind "change:reload:search_symbol {{q}}" '
        f'--preview-window "up:80%" '
        f'--ansi --disabled --no-sort'
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
        r"\s*\("
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
        r"\b"
    )


def regex_c_macro_definition(symbol: str, literal: bool) -> str:
    sym = build_symbol_regex(symbol, literal)
    return rf"^\s*#\s*define\s+{sym}\b"


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
    "c-fzf-definitions": GroupedTemplateDefinition(
        "c-fzf-definitions",
        "Fzf C/C++ definitions",
        "Interactively search definitions (functions, variables, etc.) using fzf",
        DEFINITION_PATTERNS,
        C_CPP_EXTS,
        {"--path": "~/core_repos/"},
    ),
    "c-fzf-usages": GroupedTemplateDefinition(
        "c-fzf-usages",
        "Fzf C/C++ symbol usages",
        "Interactively search symbol usages (function calls, references, etc.) using fzf",
        USAGE_PATTERNS,
        C_CPP_EXTS,
        {"--path": "~/core_repos/"},
    ),
    "fzf-file-name": GroupedTemplateDefinition(
        "fzf-file-name",
        "Fzf file name",
        "Interactively search for files by name using fd and fzf.",
        [],  # No pre-defined rg patterns
        [],  # Not applicable
        {"--path": "~/core_repos/"},
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
                should_run_now=True
            )
        )
    return templates


def parse_args() -> argparse.Namespace:
    all_templates = list(GROUPED_TEMPLATES.keys())
    parser = argparse.ArgumentParser(
        description="Generate ripgrep/fd command templates for code search",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=build_examples_epilog(get_tool_templates(), Path(__file__)),
    )

    parser.add_argument("--template", choices=all_templates, required=True, help="Template to use")
    parser.add_argument("--path", default=".", help="Root search path (default: current directory)")
    parser.add_argument("--ignore-case", action="store_true", help="Case-insensitive search")
    parser.add_argument("--regex", action="store_true", help="Treat pattern as regex (default: literal)")
    parser.add_argument("--context", type=int, default=0, help="Lines of context around matches")
    parser.add_argument("--max-depth", type=int, help="Max directory depth for file search")
    parser.add_argument("--no-copy", action="store_true", help="Don't copy to clipboard")
    parser.add_argument("pattern", nargs="?", default=None, help="Symbol or pattern to search (optional, used for initial query in some templates)")
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

    # All templates are now grouped/interactive
    if args.template not in GROUPED_TEMPLATES:
        LOG(f"{LOG_PREFIX_MSG_ERROR} Unknown template '{args.template}'")
        return

    tmpl = GROUPED_TEMPLATES[args.template]
    
    if tmpl.key == "fzf-file-name":
        # Handle file search template
        full_output = build_fzf_fd_command(str(template_args.search_path), initial_query=template_args.pattern or "")
    else:
        # Handle symbol search templates
        pattern_for_rg = "SYMBOL_PLACEHOLDER"
        fzf_template_args = TemplateArgs(
            pattern=pattern_for_rg,
            search_path=template_args.search_path,
            ignore_case=template_args.ignore_case,
            literal=template_args.literal,
            context=template_args.context,
            max_depth=template_args.max_depth,
        )
        
        results = build_grouped_search(fzf_template_args, tmpl.patterns, tmpl.file_exts)
        full_output = build_fzf_command(tmpl.display_name, results, str(template_args.search_path), tmpl.file_exts)

    LOG(f"Interactive fzf command:\n{full_output}\n")
    LOG(f"Running interactive fzf command... {full_output}")
    LOG(f"{LINE_SEPARATOR}", show_time=False)
    run_shell(full_output, shell=True,executable='/bin/bash',show_cmd=False)


if __name__ == "__main__":
    main()
