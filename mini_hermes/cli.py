import sys

from mini_hermes.agent import Agent
from mini_hermes.config import load_config
from mini_hermes.memory import clear_history, load_history, save_history
from mini_hermes.providers import make_provider
from mini_hermes.tools.registry import build_tools


def main() -> None:
    config = load_config()

    try:
        provider = make_provider(config)
    except RuntimeError as e:
        print(f"Config error: {e}", file=sys.stderr)
        sys.exit(1)

    tools = build_tools(config, provider)
    agent = Agent(provider, tools, max_turns=config.max_turns)

    print(f"mini-hermes ready (provider={config.provider}). Type /exit to quit, /reset to clear history.")

    history = load_history(config.memory_file)
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

        history_len_before = len(history)
        try:
            reply = agent.run(user_input, history=history)
        except Exception as e:
            del history[history_len_before:]  # drop this turn's partial state
            print(f"\n[Ошибка при обращении к модели: {e}]\nПопробуйте ещё раз, история диалога не пострадала.")
            continue

        save_history(config.memory_file, history)
        print(f"\nhermes> {reply}")


if __name__ == "__main__":
    main()
