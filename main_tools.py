#!/home/vien/local_tools/MyVenvFolder/bin/python
from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path
from typing import Iterable, List, Optional
from dataclasses import dataclass, field
from dev_common import *
from dev_common.tools_utils import ToolFolderMetadata, load_tools_metadata, display_command_to_use


@dataclass
class ToolEntryNode:
    """Represents a node in the tool hierarchy."""
    name: str
    tool: Optional[ToolEntry] = None
    children: List[ToolEntryNode] = field(default_factory=list)
    metadata: Optional[ToolFolderMetadata] = None
    folder_name: Optional[str] = None


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


def discover_and_nest_tools(project_root: Path, folder_pattern: str, tool_prefix: str) -> List[ToolEntryNode]:
    """Discovers tools and organizes them into a hierarchical structure."""
    tools = discover_tools(project_root, folder_pattern, tool_prefix)

    root_nodes: dict[str, ToolEntryNode] = {}

    for tool in tools:
        if tool.folder not in root_nodes:
            folder_path = project_root / tool.folder
            metadata = load_tools_metadata(folder_path)
            root_nodes[tool.folder] = ToolEntryNode(
                name=tool.folder.upper(),
                metadata=metadata,
                folder_name=tool.folder,
            )

        tool_node = ToolEntryNode(name=tool.filename, tool=tool)
        root_nodes[tool.folder].children.append(tool_node)

    # Sort the root nodes based on priority from folder name
    try:
        sorted_nodes = sorted(list(root_nodes.values()), key=lambda node: node.metadata.priority)
        return sorted_nodes
    except ValueError as e:
        LOG(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def build_template_command(tool, template: ToolTemplate):
    """Build command line for a template"""
    cmd_parts = [sys.executable, str(tool.path)]
    for arg, value in template.args.items():
        if isinstance(value, list):
            cmd_parts.append(arg)
            cmd_parts.extend(quote_arg_value_if_need(v) for v in value)  # cmd_parts.extend(str(v) for v in value)
        else:
            cmd_parts.extend([arg, quote_arg_value_if_need(value)])

    quoted_parts = []
    LOG(f"Template command parts: {cmd_parts}")
    for part in cmd_parts:
        # Only quote parts that actually need quoting (contain spaces or special chars that need escaping)
        # if ' ' in part and not (part.startswith('"') and part.endswith('"')):
        #     quoted_parts.append(quote(part))
        # else:
        #     quoted_parts.append(part)
        quoted_parts.append(quote_arg_value_if_need(str(part)))

    return ' '.join(quoted_parts)


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Discover and run local tool scripts")

    p.add_argument(ARG_TOOL_PREFIX, default="t_", help="Filename prefix for tool scripts (default: t_)", )

    p.add_argument(ARG_TOOL_FOLDER_PATTERN, default=r"^(?!misc_tools$).*_tools$",
                   help=r"Regex to match tool folders at project root, excluding 'ignore_tools' (default: ^(?!ignore_tools$).*_tools$)", )

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
    project_root = AVAILABLE_TOOLS_PATH
    # search_root = get_attribute_value(args, ARG_TOOL_ROOT_PATH)
    tool_nodes = discover_and_nest_tools(project_root, get_arg_value(
        args, ARG_TOOL_FOLDER_PATTERN), get_arg_value(args, ARG_TOOL_PREFIX))

    tool = interactive_tool_select(f"Select a tool", tool_nodes)
    if tool is None:
        return 0
    LOG(f"Selected tool: {tool.full_path} ....")
    # Only show templates for Python tools
    if tool.path.suffix == ".py":
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))
        try:
            module = importlib.import_module(f"{tool.folder}.{tool.stem}")
            if hasattr(module, 'get_tool_templates'):
                templates: List[ToolTemplate] = module.get_tool_templates()
                if templates:
                    # Build option data with command previews
                    option_data = []
                    # Main code using the helper function
                    for i, t in enumerate(templates, 1):
                        # Build command preview for this template
                        preview_cmd = build_template_command(tool, t)
                        title = f"[{i}] {t.name}: {t.extra_description}\n    → {preview_cmd}"
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
                            if selected_template.run_now_without_modify:
                                LOG(f"Running template command now")
                                run_shell(final_cmd)
                            else:
                                display_command_to_use(final_cmd, is_copy_to_clipboard=True,
                                                       purpose=f"Run tool {tool.stem}")
                        return 0
        except Exception as e:
            LOG_EXCEPTION(e)

    LOG("No templates available for this tool.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
