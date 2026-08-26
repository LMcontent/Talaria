import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    provider: str
    workspace_dir: str
    memory_file: str
    notes_file: str

    claude_api_key: str | None
    claude_model: str
    claude_show_thinking: bool
    claude_effort: str

    openai_compat_base_url: str
    openai_compat_api_key: str | None
    openai_compat_model: str
    openai_compat_dns_pin: bool
    openai_compat_dns_servers: list[str]

    confirm_code_exec: bool
    max_history_turns: int

    default_role: str
    skills_dir: str

    web_host: str
    web_port: int

    max_turns: int = 25
    max_delegate_depth: int = 3

    max_session_tokens: int = 0
    token_price_input_per_m: float = 0.0
    token_price_output_per_m: float = 0.0


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in ("1", "true", "yes", "on")


def _parse_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def load_config() -> Config:
    workspace_dir = os.environ.get("WORKSPACE_DIR", "./workspace")
    return Config(
        provider=os.environ.get("LLM_PROVIDER", "claude").strip().lower(),
        workspace_dir=workspace_dir,
        memory_file=os.environ.get(
            "MEMORY_FILE", os.path.join(workspace_dir, ".history.json")
        ),
        notes_file=os.environ.get(
            "NOTES_FILE", os.path.join(workspace_dir, ".notes.json")
        ),
        claude_api_key=os.environ.get("ANTHROPIC_API_KEY"),
        claude_model=os.environ.get("CLAUDE_MODEL", "claude-opus-5"),
        claude_show_thinking=_parse_bool(os.environ.get("CLAUDE_SHOW_THINKING", "false")),
        claude_effort=os.environ.get("CLAUDE_EFFORT", "").strip().lower(),
        openai_compat_base_url=os.environ.get(
            "OPENAI_COMPAT_BASE_URL", "https://openrouter.ai/api/v1"
        ),
        openai_compat_api_key=os.environ.get("OPENAI_COMPAT_API_KEY"),
        openai_compat_model=os.environ.get(
            "OPENAI_COMPAT_MODEL", "qwen/qwen3.8-27b-free"
        ),
        openai_compat_dns_pin=_parse_bool(os.environ.get("OPENAI_COMPAT_DNS_PIN", "false")),
        openai_compat_dns_servers=_parse_list(
            os.environ.get("OPENAI_COMPAT_DNS_SERVERS", "")
        ),
        confirm_code_exec=_parse_bool(os.environ.get("CONFIRM_CODE_EXEC", "true")),
        max_history_turns=int(os.environ.get("MAX_HISTORY_TURNS", "30")),
        default_role=os.environ.get("DEFAULT_ROLE", "assistant"),
        skills_dir=os.environ.get("SKILLS_DIR", "./skills"),
        web_host=os.environ.get("WEB_HOST", "127.0.0.1"),
        web_port=int(os.environ.get("WEB_PORT", "5000")),
        max_session_tokens=int(os.environ.get("MAX_SESSION_TOKENS", "0")),
        token_price_input_per_m=float(os.environ.get("TOKEN_PRICE_INPUT_PER_M", "0")),
        token_price_output_per_m=float(os.environ.get("TOKEN_PRICE_OUTPUT_PER_M", "0")),
        max_turns=int(os.environ.get("MAX_TURNS", "25")),
        max_delegate_depth=int(os.environ.get("MAX_DELEGATE_DEPTH", "3")),
    )
