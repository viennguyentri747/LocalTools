from dev_common.tools_utils import ToolFolderMetadata


def get_tools_metadata() -> ToolFolderMetadata:
    return ToolFolderMetadata(title="REMOTE Tools", extra_title_description="Interact with remote environments (run test on ACU, ...)")
