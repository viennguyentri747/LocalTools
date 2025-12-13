import argparse
from pathlib import Path
from typing import Any, Callable, Optional
from dev.dev_common.constants import *
from dev.dev_common.format_utils import quote


def add_arg_bool(parser: argparse.ArgumentParser, name: str, default: Optional[bool], help_text: str, true_values: tuple[str, ...] = ("true", "yes"), false_values: tuple[str, ...] = ("false", "no"), ) -> None:
    """
    Add a boolean argument that explicitly accepts true/false style values.

    Example:
        --force-remove-tmp-build true
        --force-remove-tmp-build false
    """

    def _parse_bool(value: str) -> bool:
        value_l = value.lower()
        if value_l in true_values:
            return True
        if value_l in false_values:
            return False
        raise argparse.ArgumentTypeError(
            f"Invalid boolean value '{value}'. Expected one of " f"{', '.join(true_values + false_values)}")

    parser.add_argument(
        name,
        type=_parse_bool,
        default=default,
        required=default is None,
        help=f"{help_text} (true or false). Defaults to {str(default).lower()}."
    )


def add_arg_generic(parser: argparse.ArgumentParser, name: str, *, arg_type: Optional[Callable[[str], Any]] = None, default: Any = None, required: bool = False, choices: Optional[list[Any]] = None, help_text: str = "", metavar: Optional[str] = None, action: Optional[str] = None, ) -> None:
    """
    Generic argparse helper for common argument patterns.
    """

    kwargs: dict[str, Any] = {
        "default": default,
        "required": required,
        "help": help_text,
    }

    if arg_type is not None:
        kwargs["type"] = arg_type

    if choices is not None:
        kwargs["choices"] = choices

    if metavar is not None:
        kwargs["metavar"] = metavar

    if action is not None:
        kwargs["action"] = action
        # argparse forbids type/choices with action
        kwargs.pop("type", None)
        kwargs.pop("choices", None)

    parser.add_argument(name, **kwargs)


def get_arg_value(args, arg_name: str, for_shell: bool = False):
    """Get argument attribute from argparse.Namespace using its CLI name."""
    dest_key = arg_name.lstrip('-').replace('-', '_')
    try:
        value = getattr(args, dest_key)
        FULL_PATH_ARGS = [ARG_PATHS_LONG, ARG_OUTPUT_DIR, ARG_TEMPLATE_PATH, ARG_VAULT_PATH, ARG_TOOLS_DIR]

        if isinstance(value, str) and arg_name in FULL_PATH_ARGS:
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
