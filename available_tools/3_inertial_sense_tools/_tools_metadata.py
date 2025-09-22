from dev_common.tools_utils import ToolFolderMetadata


def get_tools_metadata() -> ToolFolderMetadata:
    return ToolFolderMetadata(title="IS Tools", extra_title_description="Manage IS devices (upgrade fw and sdk, decode statuses, etc.)")
