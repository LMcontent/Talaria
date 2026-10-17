"""Groups tool names into display categories for the web UI's Tools
panel (talaria/web.py's /api/tools) — purely a presentation concern, not
part of ToolSpec itself. Keeping it here, as a name->category lookup
table, means adding a tool never requires touching providers/base.py or
any of the make_*_tools factories; a name this table doesn't know about
(any skill from SKILLS_DIR, or a future core tool nobody updated this
for) falls into the catch-all "Skills" category instead of being dropped
or erroring.
"""

CATEGORY_ORDER = [
    "Web & Browser",
    "Documents & Code",
    "Memory & Planning",
    "Learning suite",
    "Agent Skills (SKILL.md)",
    "Agent & Delegation",
    "Skills",
]

_CATEGORY_BY_NAME = {
    "web_search": "Web & Browser",
    "web_fetch": "Web & Browser",
    "browser_open": "Web & Browser",
    "browser_click": "Web & Browser",
    "browser_type": "Web & Browser",
    "browser_scroll": "Web & Browser",
    "browser_back": "Web & Browser",
    "browser_state": "Web & Browser",
    "browser_screenshot": "Web & Browser",
    "browser_network_log": "Web & Browser",
    "browser_reset": "Web & Browser",
    "read_document": "Documents & Code",
    "write_document": "Documents & Code",
    "edit_document": "Documents & Code",
    "list_files": "Documents & Code",
    "run_python": "Documents & Code",
    "install_package": "Documents & Code",
    "run_shell": "Documents & Code",
    "shell_reset": "Documents & Code",
    "remember": "Memory & Planning",
    "recall": "Memory & Planning",
    "forget": "Memory & Planning",
    "goal_add": "Memory & Planning",
    "goal_update": "Memory & Planning",
    "goal_list": "Memory & Planning",
    "goal_focus": "Memory & Planning",
    "checkpoint_save": "Memory & Planning",
    "checkpoint_restore": "Memory & Planning",
    "checkpoint_list": "Memory & Planning",
    "checkpoint_discard": "Memory & Planning",
    "cron_add": "Memory & Planning",
    "cron_list": "Memory & Planning",
    "cron_remove": "Memory & Planning",
    "cron_toggle": "Memory & Planning",
    "errbook_add": "Learning suite",
    "errbook_lookup": "Learning suite",
    "errbook_list": "Learning suite",
    "lab_hyp": "Learning suite",
    "lab_exp": "Learning suite",
    "lab_show": "Learning suite",
    "lab_next": "Learning suite",
    "feedback_rate": "Learning suite",
    "feedback_report": "Learning suite",
    "cache_put": "Learning suite",
    "cache_get": "Learning suite",
    "cache_list": "Learning suite",
    "cache_clear": "Learning suite",
    "list_agent_skills": "Agent Skills (SKILL.md)",
    "use_skill": "Agent Skills (SKILL.md)",
    "read_skill_file": "Agent Skills (SKILL.md)",
    "delegate_task": "Agent & Delegation",
    "run_procedure": "Agent & Delegation",
    "propose_skill": "Agent & Delegation",
}

# Tools that ask for a live y/N confirmation in the terminal before doing
# anything (see talaria/tools/confirmation.py) — flagged in the UI since
# these are the ones actually worth noticing in an 80-tool list.
CONFIRMING_TOOLS = {"run_python", "run_shell", "install_package", "propose_skill"}


def categorize(name: str) -> str:
    return _CATEGORY_BY_NAME.get(name, "Skills")
