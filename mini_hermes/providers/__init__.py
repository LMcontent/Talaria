from mini_hermes.config import Config
from mini_hermes.providers.base import Provider, ProviderResponse, ToolCall, ToolSpec


def make_provider(config: Config) -> Provider:
    if config.provider == "claude":
        from mini_hermes.providers.claude import ClaudeProvider

        if not config.claude_api_key:
            raise RuntimeError(
                "LLM_PROVIDER=claude but ANTHROPIC_API_KEY is not set (see .env.example)"
            )
        return ClaudeProvider(api_key=config.claude_api_key, model=config.claude_model)

    if config.provider == "openai_compat":
        from mini_hermes.providers.openai_compat import OpenAICompatProvider

        if not config.openai_compat_api_key:
            raise RuntimeError(
                "LLM_PROVIDER=openai_compat but OPENAI_COMPAT_API_KEY is not set "
                "(see .env.example)"
            )
        if config.openai_compat_dns_pin and not config.openai_compat_dns_servers:
            raise RuntimeError(
                "OPENAI_COMPAT_DNS_PIN=true but OPENAI_COMPAT_DNS_SERVERS is empty "
                "(see .env.example)"
            )
        return OpenAICompatProvider(
            api_key=config.openai_compat_api_key,
            base_url=config.openai_compat_base_url,
            model=config.openai_compat_model,
            dns_pin=config.openai_compat_dns_pin,
            dns_servers=config.openai_compat_dns_servers,
        )

    raise ValueError(f"Unknown LLM_PROVIDER: {config.provider!r} (use 'claude' or 'openai_compat')")


__all__ = ["make_provider", "Provider", "ProviderResponse", "ToolCall", "ToolSpec"]
