#!/home/vien/local_tools/MyVenvFolder/bin/python
from __future__ import annotations

import argparse
import importlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Iterable, List, Optional

from dev_common import LOG, LOG_EXCEPTION
from main_tools import diplay_templates


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Invoke a tool's templates by providing the tool path."
    )
    parser.add_argument(
        "tool_path",
        help="Path to the tool script (e.g. available_tools/code_tools/t_example.py)"
    )
    return parser.parse_args(argv)


def resolve_tool_path(path_str: str) -> Path:
    return Path(path_str).expanduser().resolve()


def find_available_tools_root(tool_path: Path) -> Optional[Path]:
    for parent in tool_path.parents:
        if parent.name == "available_tools":
            return parent
    return None


def ensure_sys_path(tool_path: Path, tools_root: Optional[Path]) -> None:
    candidates: List[Path] = []
    if tools_root:
        candidates.append(tools_root)
        if tools_root.parent:
            candidates.append(tools_root.parent)
    candidates.append(tool_path.parent)

    for candidate in candidates:
        if candidate and str(candidate) not in sys.path:
            sys.path.insert(0, str(candidate))


def import_tool_module(tool_path: Path, tools_root: Optional[Path]) -> Optional[ModuleType]:
    ensure_sys_path(tool_path, tools_root)

    module_name: Optional[str] = None
    if tools_root:
        try:
            relative_path = tool_path.relative_to(tools_root)
            module_parts = list(relative_path.with_suffix("").parts)
            if module_parts:
                module_name = ".".join(module_parts)
        except ValueError:
            module_name = None

    if module_name:
        try:
            return importlib.import_module(module_name)
        except Exception as exc:
            LOG(f"Failed to import module '{module_name}' via standard import: {exc}")

    spec = importlib.util.spec_from_file_location(tool_path.stem, tool_path)
    if spec and spec.loader:
        module = importlib.util.module_from_spec(spec)
        try:
            sys.modules[spec.name or tool_path.stem] = module
            spec.loader.exec_module(module)
            return module
        except Exception as exc:
            LOG_EXCEPTION(exc, msg=f"Failed to load module from path '{tool_path}'", exit=False)
            return None
    LOG(f"Unable to create module spec for '{tool_path}'")
    return None


def main(argv: Optional[Iterable[str]] = None) -> int:
    args = parse_args(argv)
    tool_path = resolve_tool_path(args.tool_path)

    if not tool_path.exists():
        LOG(f"Tool path does not exist: {tool_path}")
        return 1

    if not tool_path.is_file():
        LOG(f"Tool path is not a file: {tool_path}")
        return 1

    if tool_path.suffix != ".py":
        LOG(f"Templates are only supported for Python tools. Received: {tool_path}")
        return 1

    tools_root = find_available_tools_root(tool_path)
    module = import_tool_module(tool_path, tools_root)
    if module is None:
        LOG(f"Unable to load module for tool: {tool_path}")
        return 1

    if not hasattr(module, "get_tool_templates"):
        LOG(f"No 'get_tool_templates' found for tool {tool_path}")
        return 0

    try:
        templates = module.get_tool_templates()
    except Exception as exc:
        LOG_EXCEPTION(exc, msg=f"Error retrieving templates from {tool_path}", exit=False)
        return 1

    if not isinstance(templates, list):
        LOG(f"Invalid templates returned from {tool_path}: expected a list.")
        return 1

    return diplay_templates(tool_path, templates)


if __name__ == "__main__":
    sys.exit(main())
