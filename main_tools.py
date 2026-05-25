#!/usr/local/bin/local_python
from __future__ import annotations

import argparse
import importlib
import sys
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
from dataclasses import dataclass, field
from dev.dev_common import *
from dev.dev_common.tools_utils import *
from dev.dev_common.constants import SUDO
from dev.dev_common.core_independent_utils import LOG, is_platform_windows


@dataclass
class ToolEntryNode:
    """Represents a node in the tool hierarchy."""
    name: str
    tool: Optional[ToolEntry] = None
    tool_priority: int = 999
    children: List[ToolEntryNode] = field(default_factory=list)
    metadata: Optional[ToolFolderMetadata] = None
    folder_name: Optional[str] = None


DEFAULT_TOOL_PRIORITY = EToolPriority.Level10_Last
_LOG_LEVEL_NAME_TO_TYPE: Dict[str, ELogType] = {
    "debug": ELogType.DEBUG,
    "normal": ELogType.NORMAL,
    "warning": ELogType.WARNING,
    "critical": ELogType.CRITICAL,
}


def _tool_cache_key(tool_path: Path) -> str:
    return str(tool_path.resolve())


def _ensure_tool_import_paths(tools_dir: Path) -> None:
    for path_candidate in (tools_dir, tools_dir.parent):
        path_str = str(path_candidate)
        if path_str not in sys.path:
            sys.path.insert(0, path_str)


def _extract_tool_data_from_module(module: object) -> Optional[ToolData]:
    if hasattr(module, "getToolData"):
        tool_data = module.getToolData()
        if isinstance(tool_data, ToolData):
            return tool_data

    LOG_EXCEPTION_STR("No getToolData() found in module.")
    return None


def _resolve_tool_data(tool: ToolEntry, tools_dir: Path, tool_data_cache: Dict[str, ToolData]) -> ToolData:
    cache_key = _tool_cache_key(tool.path)
    if cache_key in tool_data_cache:
        return tool_data_cache[cache_key]

    default_tool_data = ToolData(tool_templates=[], tool_priority=DEFAULT_TOOL_PRIORITY, hidden=False)
    if tool.path.suffix != ".py":
        tool_data_cache[cache_key] = default_tool_data
        return default_tool_data

    _ensure_tool_import_paths(tools_dir)
    module_path = f"{tool.module_path}.{tool.stem}"
    module = importlib.import_module(module_path)
    tool_data = _extract_tool_data_from_module(module) or default_tool_data
    tool_data_cache[cache_key] = tool_data
    return tool_data


def discover_and_nest_tools(project_root: Path, folder_pattern: str, tool_prefix: str, is_recursive: bool) -> Tuple[List[ToolEntryNode], Dict[str, ToolData]]:
    """Discovers tools and organizes them into a hierarchical structure."""
    tools: List[ToolEntry] = discover_tools(project_root, folder_pattern, tool_prefix, is_recursive)
    root_nodes: dict[str, ToolEntryNode] = {}
    tool_data_cache: Dict[str, ToolData] = {}

    for tool_entry in tools:
        if tool_entry.folder not in root_nodes:
            folder_path = tool_entry.folder_path
            folder_load_start = time.perf_counter()
            metadata: ToolFolderMetadata = load_tools_metadata(folder_path)
            LOG(
                f"Loading tool folder: {tool_entry.folder} with metadata: {metadata} "
                f"(metadata load {time.perf_counter() - folder_load_start:.3f}s)",
                log_type=ELogType.DEBUG,
            )
            root_nodes[tool_entry.folder] = ToolEntryNode(name=tool_entry.folder.upper(), metadata=metadata, folder_name=tool_entry.folder)

        tool_data = _resolve_tool_data(tool_entry, project_root, tool_data_cache)
        if tool_data.hidden:
            LOG(f"Skipping hidden tool '{tool_entry.filename}' from folder '{tool_entry.folder}'.")
            continue
        tool_node = ToolEntryNode(name=tool_entry.filename, tool=tool_entry, tool_priority=tool_data.tool_priority.value)
        root_nodes[tool_entry.folder].children.append(tool_node)

    for node in root_nodes.values():
        node.children.sort(key=lambda child: (child.tool_priority, child.name))

    # Sort the root nodes based on priority from folder name
    sorted_nodes = sorted(list(root_nodes.values()), key=lambda node: node.metadata.priority)
    return sorted_nodes, tool_data_cache


def build_template_run_command(tool_path: Path, template: ToolTemplate) -> str:
    """Build command line for a template"""
    base_cmd = template.override_cmd_invocation.strip() if template.override_cmd_invocation else ""
    cmd_parts: List[str] = []
    cmd_prefix: Optional[str] = None
    if base_cmd:
        cmd_prefix = base_cmd
        LOG(f"Using override command prefix '{base_cmd}' for template '{template.name}'.")
    else:
        # if not overridden, add sudo + default python if need
        LOG(f"Using default python (that running current script) at {sys.executable} for template '{template.name}'.")
        cmd_parts = [sys.executable, str(tool_path)]
        if not is_platform_windows() and template.need_sudo_on_wsl:
            cmd_parts = [SUDO, "--preserve-env=HOME,PATH"] + cmd_parts

    for arg_key, arg_value in template.args.items():
        if isinstance(arg_value, list):
            cmd_parts.append(arg_key)
            LOG(f"Arg list value for {arg_key}: {arg_value}")
            cmd_parts.extend(quote_arg_value_if_need(v) for v in arg_value)
        else:
            cmd_parts.extend([arg_key, quote_arg_value_if_need(arg_value)])

    quoted_parts = [quote_arg_value_if_need(str(part)) for part in cmd_parts]
    suffix = ' '.join(quoted_parts)
    final_cmd = f"{cmd_prefix} {suffix}".rstrip() if cmd_prefix else suffix
    LOG(f"Built template command: {final_cmd}")
    return final_cmd


def diplay_templates(tool_path: Path, templates: List[ToolTemplate]) -> int:
    """
    Display template selection menu and execute the selected template.

    Args:
        tool_path: Path to the tool script
        templates: List of available templates

    Returns:
        Exit code (0 for success)
    """
    if not templates:
        LOG("No templates available for this tool.")
        return 0

    # Build option data with command previews
    option_data = []
    display_counter = 0
    for i, template in enumerate(templates, 1):
        if template.should_hidden:
            continue

        # Build command preview for this template
        display_counter += 1
        preview_cmd = build_template_run_command(tool_path, template)
        note_part = f". Note: {template.extra_description}" if template.extra_description else ""
        title = f"[{display_counter}] {template.name}{note_part}\n→ {preview_cmd}"
        option_data.append(OptionData(title=title, selectable=True, data=template))
        option_data.append(OptionData(title="", selectable=False))  # Spacer
    if not option_data:
        LOG("No templates available for this tool.")
        return 0

    selected = interactive_select_with_arrows(option_data, menu_title=f"Choose a template")
    if not selected or not selected.selectable:
        return 0

    selected_template: ToolTemplate = selected.data
    LOG_LINE_SEPARATOR()
    LOG(f"Selected template: {selected_template.name}")
    # Build and run final command
    cmd_line = build_template_run_command(tool_path, selected_template)

    if selected_template.no_need_live_edit:
        final_cmd = cmd_line
    else:
        search_root = selected_template.search_root if selected_template.search_root else Path.cwd()
        final_cmd = prompt_input_with_paths(
            prompt_message=f"Enter command",
            default_input=f"{cmd_line}",
            config=PathSearchConfig(search_root=search_root, resolve_symlinks=True, max_results=10),
        )

    if selected_template.usage_note:
        LOG(f"Usage note:\n{selected_template.usage_note}")

    if final_cmd:
        if selected_template.should_run_now:
            LOG_LINE_SEPARATOR()
            LOG(f"Running template command now ...")
            run_shell(final_cmd)

        else:
            tool_stem = tool_path.stem
            display_content_to_copy(
                final_cmd,
                is_copy_to_clipboard=True,
                purpose=f"Run tool {tool_stem}",
                extra_prefix_descriptions=f"{selected_template.name}\n{selected_template.extra_description}"
            )

    return 0


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Discover and run local tool scripts")

    p.add_argument(ARG_TOOL_PREFIX, default="t_", help="Filename prefix for tool scripts (default: t_)")
    p.add_argument(
        ARG_TOOL_FOLDER_PATTERN,
        default=r"^.*(?<!hidden)_tools$",
        help=r"Regex to match tool folders at project root, excluding 'ignore_tools' (default: ^(?!ignore_tools$).*_tools$)"
    )
    p.add_argument(
        ARG_TOOLS_DIR,
        default=str(AVAILABLE_TOOLS_PATH),
        help="Root folder that contains tool subdirectories (default: ~/core_repos/local_tools/available_tools)"
    )
    p.add_argument(
        "--log-level", "--log_level",
        choices=list(_LOG_LEVEL_NAME_TO_TYPE.keys()),
        default="normal",
        help="Runtime log verbosity for loader messages (default: normal)",
    )

    return p.parse_args(argv)


def interactive_tool_select(message: str, tool_nodes: List[ToolEntryNode]) -> Optional[ToolEntry]:
    """Recursively builds and displays a collapsible, interactive tool selection menu."""
    if not tool_nodes:
        LOG("No tools available to select.")
        return None

    def build_option_data(nodes: List[ToolEntryNode], level: int = 0) -> List[OptionData]:
        """Recursively converts tool nodes to OptionData for the interactive menu."""
        options = []
        for node in nodes:
            if node.tool:  # It's a tool
                options.append(OptionData(
                    title=f"{'  ' * level}{node.name}",
                    selectable=True,
                    data=node.tool
                ))
            else:  # It's a folder/category
                metadata = node.metadata or ToolFolderMetadata()
                child_options = build_option_data(node.children, level + 1)
                options.append(OptionData(
                    title=f"{'  ' * level}{metadata.get_display_title(fallback_title=node.name)}",
                    selectable=False,
                    children=child_options,
                    collapsed=metadata.is_collapsed()
                ))
        return options

    option_data = build_option_data(tool_nodes)
    selected = interactive_select_with_arrows(option_data, menu_title=message)

    if selected is None or not selected.selectable:
        return None
    return selected.data


def main(argv: Optional[Iterable[str]] = None) -> int:
    args = parse_args(argv)
    set_log_level(_LOG_LEVEL_NAME_TO_TYPE[getattr(args, "log_level", "normal")])
    tools_dir = Path(get_arg_value(args, ARG_TOOLS_DIR))
    load_start = time.perf_counter()
    tool_nodes, tool_data_cache = discover_and_nest_tools(tools_dir, get_arg_value(args, ARG_TOOL_FOLDER_PATTERN), get_arg_value(args, ARG_TOOL_PREFIX), is_recursive=True)
    total_tools = sum(len(node.children) for node in tool_nodes)
    LOG(f"Loaded {len(tool_nodes)} tool folders and {total_tools} tools in {time.perf_counter() - load_start:.3f}s.", log_type=ELogType.DEBUG)

    tool = interactive_tool_select(f"Select a tool", tool_nodes)
    if tool is None:
        return 0
    LOG_LINE_SEPARATOR()
    LOG(f"Selected tool: {tool.full_path} ....")

    tool_data = tool_data_cache.get(_tool_cache_key(tool.path))
    if tool_data is None:
        tool_data = _resolve_tool_data(tool, tools_dir, tool_data_cache)

    templates: List[ToolTemplate] = tool_data.tool_templates
    if templates:
        return diplay_templates(tool.path, templates)

    LOG("No templates available for this tool.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
