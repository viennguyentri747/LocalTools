def get_arg_value(args, arg_name: str):
    """Get argument attribute from argparse.Namespace using its CLI name (e.g., '--folder_pattern')."""
    dest_key = arg_name.lstrip('-').replace('-', '_')
    return getattr(args, dest_key)
