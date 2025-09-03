#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional
from dev_common.interactive_menu import interactive_select_with_arrows


@dataclass
class ToolEntry:
    folder: str
    filename: str
    path: Path

    @property
    def display(self) -> str:
        return f"{self.folder}/{self.filename}"

    @property
    def stem(self) -> str:
        return Path(self.filename).stem


def discover_tool_folders(root: Path, folder_pattern: str) -> List[Path]:
    pattern = re.compile(folder_pattern)
    folders: List[Path] = []
    for p in sorted(root.iterdir()):
        if p.is_dir() and pattern.match(p.name):
            folders.append(p)
    return folders


def is_tool_file(path: Path, prefix: str) -> bool:
    name = path.name
    if not name.startswith(prefix):
        return False
    if path.suffix == ".py":
        return True
    # Allow any executable file
    return os.access(str(path), os.X_OK)


def discover_tools(root: Path, folder_pattern: str, prefix: str) -> List[ToolEntry]:
    tools: List[ToolEntry] = []
    for folder in discover_tool_folders(root, folder_pattern):
        for child in sorted(folder.iterdir()):
            if child.is_file() and is_tool_file(child, prefix):
                tools.append(ToolEntry(folder=folder.name, filename=child.name, path=child))
    return tools


def _group_by_folder(tools: List[ToolEntry]) -> List[tuple[str, List[ToolEntry]]]:
    groups: dict[str, List[ToolEntry]] = {}
    order: List[str] = []
    for t in tools:
        if t.folder not in groups:
            groups[t.folder] = []
            order.append(t.folder)
        groups[t.folder].append(t)
    return [(folder, groups[folder]) for folder in order]


def print_tools(tools: List[ToolEntry]) -> None:
    if not tools:
        print("No tools found.")
        return
    total = len(tools)
    width = len(str(total))
    idx = 1
    for folder, items in _group_by_folder(tools):
        print(f"\n{folder}:")
        for t in items:
            print(f"  [{str(idx).rjust(width)}] {t.filename}")
            idx += 1
    print("")


def resolve_tool_by_name(tools: List[ToolEntry], query: str) -> Optional[ToolEntry]:
    # Support queries like "folder/name", "name", or "name.py"
    q = query.strip()
    q_folder = None
    q_name = q
    if "/" in q:
        q_folder, q_name = q.split("/", 1)
    q_stem = Path(q_name).stem

    candidates = []
    for t in tools:
        if q_folder and t.folder != q_folder:
            continue
        if t.stem == q_stem or t.filename == q_name:
            candidates.append(t)

    if not candidates:
        # fallback to contains match on stem
        for t in tools:
            if q_folder and t.folder != q_folder:
                continue
            if q_stem in t.stem:
                candidates.append(t)

    if len(candidates) == 1:
        return candidates[0]
    elif len(candidates) > 1:
        print("Multiple matches:", ", ".join(t.display for t in candidates), file=sys.stderr)
        return None
    return None


def run_tool(tool: ToolEntry, extra_args: List[str]) -> int:
    # If Python script, run with current interpreter; else execute directly
    if tool.path.suffix == ".py":
        cmd = [sys.executable, str(tool.path), *extra_args]
    else:
        cmd = [str(tool.path), *extra_args]
    print(f"Running: {' '.join(shlex.quote(c) for c in cmd)}")
    try:
        completed = subprocess.run(cmd)
        return completed.returncode
    except FileNotFoundError:
        print(f"Error: file not found: {tool.path}", file=sys.stderr)
        return 127
    except PermissionError:
        print(f"Error: permission denied: {tool.path}", file=sys.stderr)
        return 126


def get_tool_help_output(tool: ToolEntry) -> Optional[str]:
    # Prefer running the tool with -h to get accurate argparse help.
    if tool.path.suffix == ".py":
        cmd = [sys.executable, str(tool.path), "-h"]
    else:
        cmd = [str(tool.path), "-h"]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
        out = res.stdout.strip()
        err = res.stderr.strip()
        text = out or err
        if text:
            return text
    except Exception:
        pass
    # Fallback: try --help
    try:
        if tool.path.suffix == ".py":
            cmd = [sys.executable, str(tool.path), "--help"]
        else:
            cmd = [str(tool.path), "--help"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        out = res.stdout.strip()
        err = res.stderr.strip()
        text = out or err
        if text:
            return text
    except Exception:
        pass
    return None


def extract_top_docstring(path: Path) -> Optional[str]:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            src = f.read()
    except Exception:
        return None
    # Naive extraction of a top-level triple-quoted string
    for quote in ('"""', "'''"):
        start = src.find(quote)
        if start != -1:
            # Ensure it's near the start (allow shebang and blanks)
            head = src[:start]
            stripped_head = "\n".join(line for line in head.splitlines() if line.strip() and not line.startswith("#"))
            if stripped_head:
                continue
            end = src.find(quote, start + 3)
            if end != -1:
                return src[start + 3:end].strip()
    return None


def show_tool_info(root: Path, tool: ToolEntry) -> None:
    print(f"\n=== Help: {tool.display} ===")
    help_text = get_tool_help_output(tool)
    if help_text:
        print(help_text)
    else:
        doc = extract_top_docstring(tool.path)
        if doc:
            print(doc)
        else:
            print("(No help available)")


def interactive_select(tools: List[ToolEntry]) -> Optional[ToolEntry]:
    if not tools:
        print("No tools available to select.")
        return None
    groups = _group_by_folder(tools)
    if not groups:
        return None
    # Build options with headers and indented children
    options = []
    selectables = []
    tool_list = []
    for folder, folder_tools in groups:
        options.append(f"{folder}:")
        selectables.append(False)
        for t in folder_tools:
            options.append(f"  {t.filename}")
            selectables.append(True)
            tool_list.append(t)
    idx = interactive_select_with_arrows(options, title="Select a tool", selectables=selectables)
    if idx is None:
        return None
    # Find the corresponding tool
    tool_idx = 0
    for i in range(len(options)):
        if selectables[i]:
            if i == idx:
                return tool_list[tool_idx]
            tool_idx += 1
    return None


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Discover and run local tool scripts")
    p.add_argument(
        "--prefix",
        default="t_",
        help="Filename prefix for tool scripts (default: t_)",
    )
    p.add_argument(
        "--folder-pattern",
        default=r".*_tools$",
        help=r"Regex to match tool folders at project root (default: .*_tools$)",
    )
    p.add_argument(
        "--list",
        action="store_true",
        help="List available tools and exit",
    )
    p.add_argument(
        "--run",
        metavar="NAME",
        help="Run a specific tool by name (e.g., 'iesa_tools/t_foo' or 't_foo')",
    )
    p.add_argument(
        "--help-of",
        metavar="NAME",
        help="Show help/examples for a specific tool and exit",
    )
    p.add_argument(
        "--",
        dest="sep",
        nargs=argparse.REMAINDER,
        help=argparse.SUPPRESS,
    )
    return p.parse_args(argv)


def main(argv: Optional[Iterable[str]] = None) -> int:
    args = parse_args(argv)
    project_root = Path(__file__).resolve().parent
    tools = discover_tools(project_root, args.folder_pattern, args.prefix)

    if args.list:
        print_tools(tools)
        return 0

    if args.help_of:
        tool = resolve_tool_by_name(tools, args.help_of)
        if not tool:
            print("Tool not found or ambiguous. Use --list to see options.", file=sys.stderr)
            return 2
        show_tool_info(project_root, tool)
        return 0

    extra_args = []
    if args.sep:
        # drop the leading '--' from extra args if present
        extra_args = [a for a in args.sep if a != "--"]

    if args.run:
        tool = resolve_tool_by_name(tools, args.run)
        if not tool:
            print("Tool not found or ambiguous. Use --list to see options.", file=sys.stderr)
            return 2
        return run_tool(tool, extra_args)

    tool = interactive_select(tools)
    if tool is None:
        return 0

    # Always show help/info after selection
    show_tool_info(project_root, tool)

    if not extra_args:
        # Offer to enter arguments interactively
        try:
            line = input("Optional args for tool (leave blank for none): ").strip()
        except EOFError:
            line = ""
        if line:
            extra_args = shlex.split(line)
    # Confirm run
    try:
        proceed = input("Run this tool now? [y/N]: ").strip().lower()
    except EOFError:
        proceed = "n"
    if proceed not in {"y", "yes"}:
        return 0

    return run_tool(tool, extra_args)


if __name__ == "__main__":
    sys.exit(main())
