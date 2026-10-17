---
name: hello-world
description: A minimal example Agent Skill (the SKILL.md format), showing how Talaria loads and runs one end to end. Use it when asked to demonstrate or test the Agent Skills loader.
license: MIT
---

# Hello World

A tiny example skill, playing the same role `skills/example_time.py` plays
for Talaria's own ToolSpec-based skills: not something you'd actually use
day to day, just a worked example of the mechanics.

## Instructions

1. Work out which greeting style fits the request: `formal`, `casual`, or
   `pirate` (default to `casual` if nothing suggests otherwise).
2. Call `read_skill_file` with this skill's name and `scripts/greet.py` to
   get the script's source.
3. Edit the `style = "casual"` line at the top of that source to the style
   you picked, then run the whole thing with `run_python`.
4. Report back the line it printed.
