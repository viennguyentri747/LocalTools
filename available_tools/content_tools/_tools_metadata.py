from dev.dev_common.tools_utils import *


def get_tools_metadata() -> ToolFolderMetadata:
    return ToolFolderMetadata(title="Content Tools", extra_title_description="Automate content generation (gen markdown by ticket, gen MR ...)", priority=ToolFolderPriority.content_tool)
