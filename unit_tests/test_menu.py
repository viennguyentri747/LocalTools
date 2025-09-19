#!/home/vien/local_tools/MyVenvFolder/bin/python
from __future__ import annotations

from dev_common.gui_utils import interactive_select_with_arrows, OptionData


def main() -> int:
    # Multi-line title to verify wrapping and rendering
    title = (
        "Test Menu — Multi-line Title Support\n"
        "This line should wrap if it is too long for the terminal width."
    )

    # Build a few sample options, including long text to test wrapping
    options = [
        OptionData(title="Group Header (not selectable)", selectable=False),
        OptionData(title="Short option", selectable=True, data={"id": 1}),
        OptionData(
            title=(
                "This is a much longer option that should wrap across multiple "
                "lines to ensure the highlight and scrolling behave correctly."
            ),
            selectable=True,
            data={"id": 2},
        ),
        OptionData(title="Another option", selectable=True, data={"id": 3}),
    ]

    selected = interactive_select_with_arrows(options, menu_title=title)
    if selected is None:
        print("No selection (cancelled)")
    else:
        print(f"Selected: {selected.title}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

