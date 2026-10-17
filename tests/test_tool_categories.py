from talaria.tool_categories import CATEGORY_ORDER, CONFIRMING_TOOLS, categorize


def test_known_tools_land_in_their_expected_category():
    assert categorize("web_search") == "Web & Browser"
    assert categorize("run_python") == "Documents & Code"
    assert categorize("run_shell") == "Documents & Code"
    assert categorize("goal_add") == "Memory & Planning"
    assert categorize("errbook_lookup") == "Learning suite"
    assert categorize("use_skill") == "Agent Skills (SKILL.md)"
    assert categorize("delegate_task") == "Agent & Delegation"


def test_unknown_tool_falls_back_to_skills():
    # Anything from SKILLS_DIR (a user's own skill, or a repo skill like
    # current_time/to_roman) isn't in the lookup table and must still be
    # shown, not dropped.
    assert categorize("some_future_skill_tool") == "Skills"


def test_every_known_category_is_in_category_order():
    assert categorize("web_search") in CATEGORY_ORDER
    assert "Skills" in CATEGORY_ORDER


def test_confirming_tools_are_exactly_the_ones_with_a_live_confirmation_gate():
    assert CONFIRMING_TOOLS == {"run_python", "run_shell", "install_package", "propose_skill"}
