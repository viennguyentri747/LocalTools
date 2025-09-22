from dev_common.tools_utils import *


def get_tools_metadata() -> ToolFolderMetadata:
    return ToolFolderMetadata(title="IS Tools", extra_title_description="Manage IS devices (upgrade fw and sdk, decode statuses, etc.)", priority=ToolFolderPriority.inertial_sense_tool)
