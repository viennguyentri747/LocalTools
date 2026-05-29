from __future__ import annotations

from dev.dev_iesa.iesa_repo_utils import EnumReplacements

IS_DATASET_ENUM_REPLACEMENTS: EnumReplacements = (
    ("Gps", "Gnss"),
    ("GPS", "GNSS"),
    ("gps", "gnss"),
    ("Gnss", "Gps"),
    ("GNSS", "GPS"),
    ("gnss", "gps"),
)
