from dev.dev_common.tools_utils import *


def get_tools_metadata() -> ToolFolderMetadata:
    return ToolFolderMetadata(title="TEST LOG Tools", extra_title_description="Interact with remote environments (collect + check ELOG, run test on ACU, ...)", priority=ToolFolderPriority.test_tool)
