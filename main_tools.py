#!/home/vien/local_tools/MyVenvFolder/bin/python
from __future__ import annotations

import argparse
from time import sleep
import importlib
import shlex
import sys
from pathlib import Path
from typing import Iterable, List, Optional
from dev_common import *


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
            cmd_parts.append(arg)
            cmd_parts.extend(str(v) for v in value)
        else:
            cmd_parts.extend([arg, str(value)])

    quoted_parts = []
    for part in cmd_parts:
        # Only quote parts that actually need quoting (contain spaces or special chars that need escaping)
        if ' ' in part and not (part.startswith('"') and part.endswith('"')):
            quoted_parts.append(shlex.quote(part))
        else:
            quoted_parts.append(part)

    return ' '.join(quoted_parts)


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Discover and run local tool scripts")

    p.add_argument(ARG_TOOL_PREFIX, default="t_", help="Filename prefix for tool scripts (default: t_)", )

    p.add_argument(ARG_TOOL_FOLDER_PATTERN, default=r"^(?!misc_tools$).*_tools$",
                   help=r"Regex to match tool folders at project root, excluding 'ignore_tools' (default: ^(?!ignore_tools$).*_tools$)", )
    # p.add_argument(
    #     ARG_PATH_SHORT, ARG_TOOL_ROOT_PATH,
    #     default=Path.cwd(),
    #     help=f"Root path for fuzzy path search (default:CWD)",
    #     type=Path,
    # )

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
    # search_root = get_attribute_value(args, ARG_TOOL_ROOT_PATH)
    tools = discover_tools(project_root, get_arg_value(
        args, ARG_TOOL_FOLDER_PATTERN), get_arg_value(args, ARG_TOOL_PREFIX))
    tool = interactive_tool_select(f"Select a tool", tools)
    if tool is None:
        return 0
    LOG(f"Selected tool: {tool.display} ....")
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
                        option_data.append(OptionData(title="", selectable=False))  # Spacer
                    selected = interactive_select_with_arrows(option_data, menu_title=f"Choose a template")
                    if selected and selected.selectable:
                        selected_template: ToolTemplate = selected.data

                        # Build and run final command
                        cmd_line = build_template_command(tool, selected_template)
                        if selected_template.no_need_live_edit:
                            final_cmd = cmd_line
                        else:
                            search_root = selected_template.search_root if selected_template.search_root else Path.cwd()  # Default to CWD
                            final_cmd = prompt_input_with_paths(
                                prompt_message=f"Enter command",
                                default_input=f"{cmd_line}",
                                config=PathSearchConfig(search_root=search_root, resolve_symlinks=True, max_results=10),
                            )

                        if selected_template.usage_note:
                            LOG(f"Usage note:\n{selected_template.usage_note}")
                        if final_cmd:
                            LOG(f"\n✅ Final command:\n{final_cmd}")
                        return 0
        except ImportError as e:
            LOG(f"Could not import module for templates: {e}", file=sys.stderr)

    LOG("No templates available for this tool.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
