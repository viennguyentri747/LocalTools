from dev.dev_common.custom_structures import ToolData, EToolPriority


def getToolData() -> ToolData:
    return ToolData(tool_templates=[], tool_priority=EToolPriority.Level10_Last, hidden=False)
