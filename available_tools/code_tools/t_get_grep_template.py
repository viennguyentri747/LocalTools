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


TemplateBuilder = Callable[[TemplateArgs], Tuple[str, Optional[str]]]


@dataclass(frozen=True)
class TemplateDefinition:
    """Template configuration."""
    key: str
    display_name: str
    description: str
    builder: TemplateBuilder
    file_exts: List[str]  # Built into template definition
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


# C/C++ Template builder functions
def fn_c_function_definition(args: TemplateArgs, file_exts: List[str]) -> Tuple[str, Optional[str]]:
    symbol = build_symbol_regex(args.pattern, args.literal)
    # Match: return_type function_name(
    # Require at least one word (return type) before the symbol
    # regex = rf"^\s*[\w:<>\[\]\s\*&]+\s+{symbol}\s*\("

    regex = (
        rf"^\s*"
        rf"(?:\[\[[\w\s:]+\]\]\s*)*"  # Attributes like [[nodiscard]]
        rf"(?:(?:static|extern|inline|virtual|explicit|constexpr|friend)\s+)*"  # Storage/function specifiers
        rf"(?:(?:const|volatile)\s+)*"  # CV qualifiers
        rf"[\w:]+"  # Base type (with namespace support)
        rf"(?:\s*<[^>]+>)?"  # Template parameters in return type
        rf"(?:\s*[\*&]+)*"  # Pointers and references
        rf"(?:\s+(?:const|volatile))*"  # Trailing CV qualifiers
        rf"\s+"  # Separator before function name
        rf"{symbol}"  # Function name
        rf"\s*\("  # Opening parenthesis
    )
    return build_rg_command(regex, args, file_exts), "Matches C/C++ function definitions"


def fn_c_function_call(args: TemplateArgs, file_exts: List[str]) -> Tuple[str, Optional[str]]:
    symbol = build_symbol_regex(args.pattern, args.literal)
    regex = rf"{symbol}\s*\("
    return build_rg_command(regex, args, file_exts), "Use --context to see call arguments"


def fn_c_variable_definition(args: TemplateArgs, file_exts: List[str]) -> Tuple[str, Optional[str]]:
    symbol = build_symbol_regex(args.pattern, args.literal)
    # Match variable declarations with common C/C++ keywords/types
    regex = rf"^\s*(const|static|constexpr|extern|volatile|[\w:<>\[\]\s\*&]+)\s+{symbol}\s*(=|;|\[)"
    return build_rg_command(regex, args, file_exts), "Matches C/C++ variable/field declarations"


def fn_c_variable_usage(args: TemplateArgs, file_exts: List[str]) -> Tuple[str, Optional[str]]:
    symbol = build_symbol_regex(args.pattern, args.literal)
    return build_rg_command(symbol, args, file_exts, ["--color=always"]), None


def fn_c_class_struct_definition(args: TemplateArgs, file_exts: List[str]) -> Tuple[str, Optional[str]]:
    symbol = build_symbol_regex(args.pattern, args.literal, word_boundaries=False)
    regex = rf"^\s*(class|struct)\s+{symbol}\b"
    return build_rg_command(regex, args, file_exts), None


def fn_c_macro_definition(args: TemplateArgs, file_exts: List[str]) -> Tuple[str, Optional[str]]:
    symbol = build_symbol_regex(args.pattern, args.literal)
    regex = rf"^\s*#\s*define\s+{symbol}"
    return build_rg_command(regex, args, file_exts), None


def fn_c_typedef_definition(args: TemplateArgs, file_exts: List[str]) -> Tuple[str, Optional[str]]:
    symbol = build_symbol_regex(args.pattern, args.literal)
    regex = rf"^\s*typedef\s+.*\s+{symbol}\s*;"
    return build_rg_command(regex, args, file_exts), "Matches typedef declarations"


def fn_c_enum_definition(args: TemplateArgs, file_exts: List[str]) -> Tuple[str, Optional[str]]:
    symbol = build_symbol_regex(args.pattern, args.literal, word_boundaries=False)
    regex = rf"^\s*enum\s+(class\s+)?{symbol}\b"
    return build_rg_command(regex, args, file_exts), "Matches enum declarations"


# Generic file search
def fn_file_name(args: TemplateArgs, file_exts: List[str]) -> Tuple[str, Optional[str]]:
    return build_fd_command(args.pattern, args), None


# Template definitions
C_CPP_EXTS = ["c", "cpp", "cc", "cxx", "h", "hpp", "hxx"]

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
    "c-function-definition": TemplateDefinition(
        "c-function-definition",
        "Find C/C++ function definitions",
        "Search for function declarations in C/C++ code",
        fn_c_function_definition,
        C_CPP_EXTS,
        {"--pattern": "FunctionName", "--path": "~/core_repos/"},
        "Use --regex for custom patterns",
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
    "c-variable-definition": TemplateDefinition(
        "c-variable-definition",
        "Find C/C++ variable definitions",
        "Locate variable/field declarations in C/C++ code",
        fn_c_variable_definition,
        C_CPP_EXTS,
        {"--pattern": "variableName", "--path": "~/core_repos/"},
    ),
    "c-variable-usage": TemplateDefinition(
        "c-variable-usage",
        "Find C/C++ variable usage",
        "Search for symbol references in C/C++ code",
        fn_c_variable_usage,
        C_CPP_EXTS,
        {"--pattern": "variableName", "--path": "~/core_repos/"},
    ),
    "c-class-struct-definition": TemplateDefinition(
        "c-class-struct-definition",
        "Find C/C++ class/struct definitions",
        "Locate class/struct declarations in C/C++ code",
        fn_c_class_struct_definition,
        C_CPP_EXTS,
        {"--pattern": "ClassName", "--path": "~/core_repos/"},
    ),
    "c-macro-definition": TemplateDefinition(
        "c-macro-definition",
        "Find C/C++ macro definitions",
        "Search for #define statements in C/C++ code",
        fn_c_macro_definition,
        C_CPP_EXTS,
        {"--pattern": "MACRO_NAME", "--path": "~/core_repos/"},
    ),
    "c-typedef-definition": TemplateDefinition(
        "c-typedef-definition",
        "Find C/C++ typedef definitions",
        "Search for typedef declarations in C/C++ code",
        fn_c_typedef_definition,
        C_CPP_EXTS,
        {"--pattern": "TypeName", "--path": "~/core_repos/"},
    ),
    "c-enum-definition": TemplateDefinition(
        "c-enum-definition",
        "Find C/C++ enum definitions",
        "Search for enum declarations in C/C++ code",
        fn_c_enum_definition,
        C_CPP_EXTS,
        {"--pattern": "EnumName", "--path": "~/core_repos/"},
    ),
}


def get_tool_templates() -> List[ToolTemplate]:
    """Generate examples for CLI help."""
    templates = []
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
    parser = argparse.ArgumentParser(
        description="Generate ripgrep/fd command templates for code search",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=build_examples_epilog(get_tool_templates(), Path(__file__)),
    )

    parser.add_argument("--template", choices=list(TEMPLATES.keys()), required=True, help="Template to use")
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
    tmpl = TEMPLATES.get(args.template)
    if not tmpl:
        LOG(f"{LOG_PREFIX_MSG_ERROR} Unknown template '{args.template}'")
        return
    
    template_args = TemplateArgs(
        pattern=args.pattern,
        search_path=Path(args.path).expanduser(),
        ignore_case=args.ignore_case,
        literal=not args.regex,
        context=args.context,
        max_depth=args.max_depth,
    )
    
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


if __name__ == "__main__":
    main()