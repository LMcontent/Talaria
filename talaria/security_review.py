"""A dedicated, tool-less review call before a self-authored skill is
saved and loaded. This is advisory, not a sandbox — it's a second opinion
from the same model family, shown to the human before they decide.
"""

SECURITY_REVIEW_SYSTEM = (
    "You are a strict security reviewer. You will be shown Python source "
    "code proposed as a new tool ('skill') for an autonomous agent. If "
    "approved, this code will run on the user's own machine with their "
    "OS-level permissions every time the agent chooses to call it — with "
    "NO further confirmation after this review. Look specifically for: "
    "destructive filesystem operations (delete/overwrite outside an "
    "obvious workspace path); network calls that look like they exfiltrate "
    "data, credentials, or send data to an unexpected host; "
    "shell/os.system/subprocess with shell=True or unsanitized input; "
    "eval/exec of untrusted input; reading credentials/secrets/SSH keys/"
    "environment variables for anything other than the skill's own stated "
    "purpose; attempts to modify talaria's own source files; or "
    "anything that does something other than what its own name and "
    "description claim. Respond with EXACTLY one line starting with "
    "'VERDICT: SAFE' or 'VERDICT: RISKY', followed by a short explanation "
    "(2-4 sentences) of what the code actually does and, if risky, "
    "precisely what's concerning."
)


def review_code(provider, code: str, description: str) -> str:
    history = [
        {
            "role": "user",
            "content": (
                f"Proposed skill description: {description}\n\n"
                f"Code:\n```python\n{code}\n```"
            ),
        }
    ]
    response = provider.chat(history, system=SECURITY_REVIEW_SYSTEM, tools=[])
    return response.text
