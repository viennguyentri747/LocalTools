#!/usr/bin/env python3
from __future__ import annotations

import argparse
from time import sleep
import importlib
import os
import re
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

from dev_common.core_utils import LOG
from dev_common.input_utils import PathSearchConfig, prompt_input_with_paths
from dev_common.gui_utils import interactive_select_with_arrows, OptionData
from dev_common.constants import ARG_PATH_SHORT, ARG_TOOL_PREFIX, ARG_TOOL_FOLDER_PATTERN, ARG_TOOL_ROOT_PATH, LINE_SEPARATOR, LINE_SEPARATOR_NO_ENDLINE
from dev_common.tools_utils import ToolEntry, ToolTemplate, discover_tools
from dev_common.python_misc_utils import get_attribute_value


# Helper functions that don't call other functions in this file
def _group_by_folder(tools: List[ToolEntry]) -> List[tuple[str, List[ToolEntry]]]:
    groups: dict[str, List[ToolEntry]] = {}
    order: List[str] = []
    for t in tools:
        if t.folder not in groups:
            groups[t.folder] = []
            order.append(t.folder)
        groups[t.folder].append(t)
    return [(folder, groups[folder]) for folder in order]


def build_template_command(tool, template: ToolTemplate):
    """Build command line for a template"""
    cmd_parts = [sys.executable, str(tool.path)]

    for arg, value in template.args.items():
        if isinstance(value, list):
            # Add arg once followed by all values: arg val1 val2 val3
            cmd_parts.append(arg)
            cmd_parts.extend(str(v) for v in value)
            # for v in value:
            #     cmd_parts.extend([arg, str(v)])
        else:
            # Add arg and single value: arg value
            cmd_parts.extend([arg, str(value)])

    return ' '.join(shlex.quote(p) for p in cmd_parts)


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Discover and run local tool scripts")

    p.add_argument(
        ARG_TOOL_PREFIX,
        default="t_",
        help="Filename prefix for tool scripts (default: t_)",
    )

    p.add_argument(
        ARG_TOOL_FOLDER_PATTERN,
        default=r"^(?!unused_tools$).*_tools$",
        help=r"Regex to match tool folders at project root, excluding 'ignore_tools' (default: ^(?!ignore_tools$).*_tools$)",
    )

    p.add_argument(
        ARG_PATH_SHORT, ARG_TOOL_ROOT_PATH,
        default=Path.cwd(),
        help=f"Root path for fuzzy path search (default:CWD)",
        type=Path,
    )

    return p.parse_args(argv)


def interactive_tool_select(message: str, tools: List[ToolEntry]) -> Optional[ToolEntry]:
    if not tools:
        LOG("No tools available to select.")
        return None
    groups = _group_by_folder(tools)
    if not groups:
        return None
    # Build option_data with headers and indented children
    option_data = []
    for folder, folder_tools in groups:
        option_data.append(OptionData(title=f"{folder.upper()}:", selectable=False))
        for t in folder_tools:
            option_data.append(OptionData(title=f"  {t.filename}", selectable=True, data=t))
        option_data.append(OptionData(title=f"", selectable=False))
    selected = interactive_select_with_arrows(option_data, menu_title=message)
    if selected is None or not selected.selectable:
        return None
    return selected.data


def main(argv: Optional[Iterable[str]] = None) -> int:
    args = parse_args(argv)
    project_root = Path(__file__).resolve().parent
    search_root = get_attribute_value(args, ARG_TOOL_ROOT_PATH)
    tools = discover_tools(project_root, get_attribute_value(
        args, ARG_TOOL_FOLDER_PATTERN), get_attribute_value(args, ARG_TOOL_PREFIX))
    tool = interactive_tool_select(f"Select a tool, search dir: {search_root}", tools)
    if tool is None:
        return 0
    LOG(f"Selected tool: {tool.display} ....")
    # Always show help/info after selection
    # Only show templates for Python tools
    if tool.path.suffix == ".py":
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))
        try:
            module = importlib.import_module(f"{tool.folder}.{tool.stem}")
            if hasattr(module, 'get_tool_templates'):
                templates = module.get_tool_templates()
                if templates:
                    # Build option data with command previews
                    option_data = []
                    # Main code using the helper function
                    for i, t in enumerate(templates, 1):
                        # Build command preview for this template
                        preview_cmd = build_template_command(tool, t)
                        title = f"[{i}] {t.name}: {t.description}\n    → {preview_cmd}"
                        option_data.append(OptionData(title=title, selectable=True, data=t))
                        option_data.append(OptionData(title="", selectable=False)) # Spacer
                    selected = interactive_select_with_arrows(option_data, menu_title=f"Choose a template")
                    if selected and selected.selectable:
                        selected_template: ToolTemplate = selected.data

                        # Build and run final command
                        cmd_line = build_template_command(tool, selected_template)
                        final_cmd = prompt_input_with_paths(
                            prompt_message=f"Enter command",
                            default_input=f"{cmd_line}",
                            config=PathSearchConfig(search_root=search_root, resolve_symlinks=True, max_results=10),
                        )

                        if final_cmd:
                            LOG(f"\n✅ Final command:\n{final_cmd}")
                        return 0
        except ImportError as e:
            LOG(f"Could not import module for templates: {e}", file=sys.stderr)

    LOG("No templates available for this tool.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
