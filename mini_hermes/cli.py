import sys

from mini_hermes.agent import Agent
from mini_hermes.compaction import compact_history
from mini_hermes.config import load_config
from mini_hermes.memory import clear_history, load_history, save_history
from mini_hermes.notes import format_notes_for_prompt, load_notes
from mini_hermes.providers import make_provider
from mini_hermes.roles import DEFAULT_ROLE, ROLES
from mini_hermes.tools.registry import build_tools
from mini_hermes.tools.skill_authoring import make_propose_skill_tool


def build_system(role: str, notes_file: str) -> str:
    base = ROLES[role]["system"]
    notes_block = format_notes_for_prompt(load_notes(notes_file))
    return f"{base}\n\n{notes_block}" if notes_block else base


def main() -> None:
    config = load_config()

    try:
        provider = make_provider(config)
    except RuntimeError as e:
        print(f"Config error: {e}", file=sys.stderr)
        sys.exit(1)

    tools = build_tools(config, provider)
    current_role = config.default_role if config.default_role in ROLES else DEFAULT_ROLE
    agent = Agent(
        provider, tools, system=build_system(current_role, config.notes_file), max_turns=config.max_turns
    )
    # propose_skill needs a live reference to `agent` to register whatever it
    # approves, so it's added after construction rather than via build_tools
    # — and only on the top-level agent, never on delegate_task sub-agents.
    agent.add_tools([make_propose_skill_tool(provider, config.skills_dir, agent)])

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
            for t in agent.tools:
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
                print(f"(role switched to {arg})")
            else:
                print(f"Unknown role {arg!r}. Type /role to see the list.")
            continue

        agent.system = build_system(current_role, config.notes_file)

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
