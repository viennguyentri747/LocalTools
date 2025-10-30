from dev_common.tools_utils import *


def get_tools_metadata() -> ToolFolderMetadata:
    return ToolFolderMetadata(title="MISC HIDDEN Tools", extra_title_description="Automate IESA workflows (build, gen code by ticket, ...)", priority=ToolFolderPriority.iesa_tool, should_ignore=True)
