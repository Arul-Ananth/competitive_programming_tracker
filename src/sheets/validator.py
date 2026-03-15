from sheets.detector import SheetLayout


class SheetValidationError(Exception):
    pass


def validate_layout(layout: SheetLayout) -> None:
    required = {"title", "link"}
    missing = [column for column in required if column not in layout.column_map]
    if missing:
        raise SheetValidationError(
            f"Missing required sheet columns: {', '.join(sorted(missing))}"
        )

