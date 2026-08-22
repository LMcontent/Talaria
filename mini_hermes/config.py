import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    provider: str
    workspace_dir: str

    claude_api_key: str | None
    claude_model: str

    openai_compat_base_url: str
    openai_compat_api_key: str | None
    openai_compat_model: str

    max_turns: int = 15
    max_delegate_depth: int = 2


def load_config() -> Config:
    return Config(
        provider=os.environ.get("LLM_PROVIDER", "claude").strip().lower(),
        workspace_dir=os.environ.get("WORKSPACE_DIR", "./workspace"),
        claude_api_key=os.environ.get("ANTHROPIC_API_KEY"),
        claude_model=os.environ.get("CLAUDE_MODEL", "claude-opus-5"),
        openai_compat_base_url=os.environ.get(
            "OPENAI_COMPAT_BASE_URL", "https://openrouter.ai/api/v1"
        ),
        openai_compat_api_key=os.environ.get("OPENAI_COMPAT_API_KEY"),
        openai_compat_model=os.environ.get(
            "OPENAI_COMPAT_MODEL", "qwen/qwen3.8-27b-free"
        ),
    )
