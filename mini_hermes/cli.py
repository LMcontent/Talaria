import sys

from mini_hermes.agent import Agent
from mini_hermes.compaction import compact_history
from mini_hermes.config import load_config
from mini_hermes.memory import clear_history, load_history, save_history
from mini_hermes.providers import make_provider
from mini_hermes.roles import DEFAULT_ROLE, ROLES
from mini_hermes.tools.registry import build_tools


def main() -> None:
    config = load_config()

    try:
        provider = make_provider(config)
    except RuntimeError as e:
        print(f"Config error: {e}", file=sys.stderr)
        sys.exit(1)

    tools = build_tools(config, provider)
    current_role = config.default_role if config.default_role in ROLES else DEFAULT_ROLE
    agent = Agent(provider, tools, system=ROLES[current_role]["system"], max_turns=config.max_turns)

    print(
        f"mini-hermes ready (provider={config.provider}, role={current_role}). "
        "Commands: /exit, /reset, /role [name], /tools."
    )

    history = compact_history(load_history(config.memory_file), config.max_history_turns)
    if history:
        print(f"(loaded {len(history)} saved messages from {config.memory_file})")

    while True:
        try:
            user_input = input("\nyou> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not user_input:
            continue
        if user_input in ("/exit", "/quit"):
            break
        if user_input == "/reset":
            history = []
            clear_history(config.memory_file)
            print("(history cleared)")
            continue
        if user_input == "/tools":
            print("Available tools:")
            for t in tools:
                print(f"  - {t.name}: {t.description}")
            continue
        if user_input == "/role" or user_input.startswith("/role "):
            arg = user_input[len("/role"):].strip()
            if not arg:
                print("Available roles:")
                for name, info in ROLES.items():
                    marker = "*" if name == current_role else " "
                    print(f"  {marker} {name} — {info['description']}")
            elif arg in ROLES:
                current_role = arg
                agent.system = ROLES[arg]["system"]
                print(f"(role switched to {arg})")
            else:
                print(f"Unknown role {arg!r}. Type /role to see the list.")
            continue

        history_len_before = len(history)
        print("\nhermes> ", end="", flush=True)
        try:
            agent.run(user_input, history=history)
        except Exception as e:
            del history[history_len_before:]  # drop this turn's partial state
            print(f"\n[Ошибка при обращении к модели: {e}]\nПопробуйте ещё раз, история диалога не пострадала.")
            continue

        history = compact_history(history, config.max_history_turns)
        save_history(config.memory_file, history)
        print()  # newline after the streamed reply


if __name__ == "__main__":
    main()
