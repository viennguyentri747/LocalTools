from dataclasses import dataclass
import importlib.util
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import List, Dict, Any, Optional
from enum import IntEnum, auto
import pyperclip
from dev_common.constants import CMD_WSLPATH, LINE_SEPARATOR, CMD_EXPLORER, WSL_SELECT_FLAG
from dev_common.core_utils import LOG


class ToolFolderPriority(IntEnum):
    TOP = 0
    code_tool = auto()
    iesa_tool = auto()
    inertial_sense_tool = auto()
    remote_tool = auto()
    # TODO: Add more priorities
    LAST = 999


@dataclass
class ToolTemplate:
    name: str
    extra_description: str
    args: Dict[str, Any]  # {arg_name: arg_value}
    search_root: Optional[Path]
    no_need_live_edit: bool
    usage_note: str = ""
    run_now_without_modify: bool = False

    def __init__(self, name: str, extra_description: str = "", args: Dict[str, Any] = {}, search_root: Optional[Path] = None, no_need_live_edit: bool = True, usage_note: str = "", should_run_now: bool = False):
        self.name = name
        self.extra_description = extra_description
        self.args = args
        self.search_root = search_root
        self.no_need_live_edit = no_need_live_edit
        self.usage_note = usage_note
        self.run_now_without_modify = should_run_now


@dataclass
class ToolEntry:
    folder: str
    filename: str
    path: Path

    @property
    def full_path(self) -> str:
        return f"{self.folder}/{self.filename}"

    @property
    def stem(self) -> str:
        return Path(self.filename).stem


@dataclass
class ToolFolderMetadata:
    """Metadata describing how a tool folder should be displayed."""

    title: Optional[str] = None
    extra_title_description: str = ""
    always_expand: bool = False
    start_collapsed: Optional[bool] = None
    priority: ToolFolderPriority = ToolFolderPriority.LAST

    def get_display_title(self, fallback_title: str) -> str:
        base = self.title or fallback_title
        if self.extra_title_description:
            return f"{base} - {self.extra_title_description}"
        return base

    def is_collapsed(self) -> bool:
        if self.always_expand:
            return False
        if self.start_collapsed is not None:
            return self.start_collapsed
        return True


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
        LOG(f"Error getting help output for tool: {tool.full_path}")


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


def load_tools_metadata(folder: Path) -> ToolFolderMetadata:
    """Load metadata customizations for a tools folder if present."""
    metadata_file_name = "_tools_metadata.py"
    metadata_path = folder / f"{metadata_file_name}"
    if not metadata_path.exists():
        return ToolFolderMetadata()

    spec = importlib.util.spec_from_file_location(f"{folder.name}_tools_metadata", metadata_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Failed to create module spec for {folder.name}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    metadata_factory = getattr(module, "get_tools_metadata", None)
    if metadata_factory is None:
        raise AttributeError(f"No get_tools_metadata function found in {folder.name}")

    metadata = metadata_factory()

    if isinstance(metadata, ToolFolderMetadata):
        return metadata

    if isinstance(metadata, dict):
        return ToolFolderMetadata(**metadata)

    raise TypeError(f"Unsupported metadata type {type(metadata)} for {folder.name}")


def display_content_to_copy(content: str, purpose: str = "", is_copy_to_clipboard: bool = True, extra_prefix_descriptions: Optional[str] = None) -> None:
    """
    Handles the final command display and clipboard copying.
    """
    purpose_text = f" to {purpose}" if purpose else ""

    # Try to copy to clipboard first
    clipboard_status = ""
    if is_copy_to_clipboard:
        try:
            pyperclip.copy(content)
            clipboard_status = " (copied to clipboard)"
        except Exception as e:
            clipboard_status = f" (clipboard failed: {e})"
    LOG(f"\n", show_time=False)
    if extra_prefix_descriptions:
        LOG(f"{extra_prefix_descriptions}", show_time=False)
    LOG(f"\n", show_time=False)
    LOG(f"✅ Content{purpose_text}{clipboard_status}:", show_time=False)
    LOG(f"{LINE_SEPARATOR}", show_time=False)
    LOG(f"{content}", show_time=False)
    LOG(f"{LINE_SEPARATOR}", show_time=False)


def open_explorer_to_file(file_path: Path) -> None:
    """
    Open Windows Explorer and highlight the specified file (WSL only).
    """
    try:
        # Convert WSL path to Windows path
        result = subprocess.run(
            [CMD_WSLPATH, "-w", str(file_path)],
            capture_output=True,
            text=True,
            check=True
        )
        windows_path = result.stdout.strip()

        # Open Explorer with file selected
        subprocess.run([CMD_EXPLORER, WSL_SELECT_FLAG, windows_path], check=False)
        LOG(f"Opened Explorer to highlight '{file_path}'")
    except Exception as e:
        LOG(f"Failed to open Explorer: {e}")
