"""Example skill.

Any *.py file dropped in this directory that defines a top-level TOOLS
list is picked up automatically on startup — no changes to Talaria
itself needed. This one adds a current_time tool, since the model
otherwise has no idea what "now" is.
"""

from datetime import datetime, timezone

from talaria.providers.base import ToolSpec


def current_time(tz: str = "UTC") -> str:
    if tz.upper() != "UTC":
        return f"Error: this example skill only supports tz='UTC' (got {tz!r})."
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


TOOLS = [
    ToolSpec(
        name="current_time",
        description="Get the current date and time.",
        input_schema={
            "type": "object",
            "properties": {
                "tz": {
                    "type": "string",
                    "description": "Timezone — currently only 'UTC' is supported.",
                }
            },
            "required": [],
        },
        handler=lambda tz="UTC": current_time(tz),
    ),
]
