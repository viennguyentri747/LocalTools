def get_attribute_value(args, attr_name: str):
    """Get argument attribute from argparse.Namespace using its CLI name (e.g., '--folder-pattern')."""
    dest_key = attr_name.lstrip('-').replace('-', '_')
    return getattr(args, dest_key)
