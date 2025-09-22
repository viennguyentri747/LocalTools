from dev_common.tools_utils import *


def get_tools_metadata() -> ToolFolderMetadata:
    return ToolFolderMetadata(title="CODE Tools", extra_title_description="Work with codebase (extract code context, ...)", priority=ToolFolderPriority.code_tool)
