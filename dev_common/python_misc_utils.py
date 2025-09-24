from pathlib import Path
from dev_common.constants import *
from dev_common.format_utils import quote


def get_arg_value(args, arg_name: str, for_shell: bool = False):
    """Get argument attribute from argparse.Namespace using its CLI name."""
    dest_key = arg_name.lstrip('-').replace('-', '_')
    try:
        value = getattr(args, dest_key)
        PATH_ARGS = [ARG_PATHS_LONG, ARG_OUTPUT_DIR_LONG, ARG_TEMPLATE_PATH, ARG_DIR_TO_COPY_TO]
        
        if isinstance(value, str) and arg_name in PATH_ARGS:
            resolve_path = str(Path(value).expanduser().resolve())
            # print(f"Resolved path: {resolve_path} vs original: {value}")
            if for_shell and needs_quoting(resolve_path):
                return quote(resolve_path)
            else:
                return resolve_path
        else:
            return value
    except AttributeError:
        print("Available attributes:", dir(args))
        raise

def needs_quoting(path: str) -> bool:
    """Check if a path needs quoting for shell usage."""
    # Skip if already quoted
    if (path.startswith('"') and path.endswith('"')) or (path.startswith("'") and path.endswith("'")):
        return False

    # Characters that require quoting in shell
    special_chars = r'[ ()&|;$`"\'\\*?<>{}[\]~]'
    return bool(re.search(special_chars, path))
