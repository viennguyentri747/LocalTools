from dataclasses import dataclass
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import List, Dict, Any, Optional

from dev_common.core_utils import LOG


@dataclass
class ToolTemplate:
    name: str
    extra_description: str
    args: Dict[str, Any]  # {arg_name: arg_value}
    search_root: Optional[Path]
    no_need_live_edit: bool
    usage_note: str = ""

    def __init__(self, name: str, extra_description: str = "", args: Dict[str, Any] = {}, search_root: Optional[Path] = None, no_need_live_edit: bool = True, usage_note: str = ""):
        self.name = name
        self.extra_description = extra_description
        self.args = args
        self.search_root = search_root
        self.no_need_live_edit = no_need_live_edit
        self.usage_note = usage_note


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


def discover_tools(root: Path, folder_pattern: str, prefix: str) -> List[ToolEntry]:
    tools: List[ToolEntry] = []
    for folder in discover_tool_folders(root, folder_pattern):
        for child in sorted(folder.iterdir()):
            if child.is_file() and is_tool_file(child, prefix):
                tools.append(ToolEntry(folder=folder.name, filename=child.name, path=child))
    return tools


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


def get_tool_templates() -> List[ToolTemplate]:
    """
    Returns a list of common templates for the tool.
    Each template contains preset arguments and their values.
    """
    return []


def get_python_tool_help_output(tool: ToolEntry) -> Optional[str]:
    cmd = [sys.executable, str(tool.path), "-h"]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
        out = res.stdout.strip()
        err = res.stderr.strip()
        text = out or err
        if text:
            return text
    except Exception:
        LOG(f"Error getting help output for tool: {tool.display}")


def build_examples_epilog(templates: List[ToolTemplate], script_path: Path) -> str:
    """
    Build a help epilog string from a list of ToolTemplate entries.
        Each example line shows a runnable command using the current script path.
    """
    if not templates:
        return ""

    lines: List[str] = ["Examples:"]
    script_str = str(script_path)
    for i, t in enumerate(templates, 1):
        # Build argument string
        arg_parts: List[str] = []
        for arg, value in t.args.items():
            if isinstance(value, list):
                # arg then multiple values
                part = " ".join([arg] + [str(v) for v in value])
                arg_parts.append(part)
            elif isinstance(value, bool):
                # flags: include only when True
                if value:
                    arg_parts.append(str(arg))
            else:
                arg_parts.append(f"{arg} {value}")

        cmd = f"{script_str} {' '.join(arg_parts)}".rstrip()
        lines.append("")
        lines.append(f"# Example {i}: {t.name}")
        if t.extra_description:
            lines.append(f"# {t.extra_description}")
        lines.append(cmd)

    return "\n".join(lines)
