from talaria.providers.base import ToolSpec

# Стандартные пары (значение, символ) для конвертации с вычитанием
_ROMAN_VALUES = [
    (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
    (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
    (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
]


def to_roman(n: int = 0) -> str:
    """Convert an integer (1-3999) to its Roman numeral representation."""
    try:
        n = int(n)
    except (TypeError, ValueError):
        return "Error: n must be an integer"
    if not 1 <= n <= 3999:
        return "Error: n must be between 1 and 3999"

    parts = []
    for value, symbol in _ROMAN_VALUES:
        count, n = divmod(n, value)
        parts.append(symbol * count)
    return "".join(parts)


TOOLS: list[ToolSpec] = [
    ToolSpec(
        name="to_roman",
        description="Convert an integer (1-3999) into its Roman numeral representation, e.g. 2026 -> MMXXVI.",
        input_schema={
            "type": "object",
            "properties": {
                "n": {
                    "type": "integer",
                    "description": "Integer between 1 and 3999 to convert to Roman numerals.",
                }
            },
            "required": ["n"],
        },
        handler=to_roman,
    )
]
