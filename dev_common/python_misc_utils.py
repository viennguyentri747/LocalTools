def get_arg_value(args, arg_name: str):
    """Get argument attribute from argparse.Namespace using its CLI name (e.g., '--folder_pattern')."""
    dest_key = arg_name.lstrip('-').replace('-', '_') #Remove leading - and replace - with _
    try:
        return getattr(args, dest_key)
    except AttributeError:
        print("Available attributes:", dir(args))
        raise