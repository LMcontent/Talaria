# -*- coding: utf-8 -*-
"""Idea Lab: a visible iteration loop - hypotheses, experiments, pivots.

Promoted from skills/idea_lab.py into core: talaria/autonomous.py's check-in
loop already looks up lab_next by name, so this guarantees it's always
there instead of depending on an optional skill being installed.
"""
import json
import os

from talaria.providers.base import ToolSpec
from talaria.tools.state_lock import STATE_LOCK


def _path(workspace_dir: str) -> str:
    return os.path.join(workspace_dir, ".idea_lab.json")


def _load(workspace_dir: str) -> dict:
    path = _path(workspace_dir)
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                d = json.load(f)
            if isinstance(d, dict):
                d.setdefault("hypotheses", [])
                d.setdefault("experiments", [])
                return d
        except Exception:
            pass
    return {"hypotheses": [], "experiments": []}


def _save(workspace_dir: str, db: dict) -> None:
    path = _path(workspace_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def lab_hyp(workspace_dir: str, idea: str = "", expected: str = "") -> str:
    """Register a new hypothesis (idea + what we expect to see)."""
    idea = str(idea).strip()
    if not idea:
        return "Error: empty idea"
    with STATE_LOCK:
        db = _load(workspace_dir)
        hid = max([h.get("id", 0) for h in db["hypotheses"]], default=0) + 1
        db["hypotheses"].append({
            "id": hid,
            "idea": idea,
            "expected": str(expected).strip(),
            "status": "todo",
        })
        _save(workspace_dir, db)
    return "Hypothesis H{} registered: {}".format(hid, idea)


def lab_exp(workspace_dir: str, hyp_id: str = "", what: str = "", result: str = "", verdict: str = "") -> str:
    """Log an experiment outcome for a hypothesis. Verdict: keep | pivot | drop."""
    try:
        hid = int(str(hyp_id).strip())
    except ValueError:
        return "Error: hyp_id must be an integer."
    v = str(verdict).strip().lower()
    if v not in ("keep", "pivot", "drop"):
        return "Error: verdict must be one of: keep, pivot, drop"
    with STATE_LOCK:
        db = _load(workspace_dir)
        target = next((h for h in db["hypotheses"] if h["id"] == hid), None)
        if target is None:
            return "Error: hypothesis H{} not found.".format(hid)

        eid = max([e.get("id", 0) for e in db["experiments"]], default=0) + 1
        db["experiments"].append({
            "id": eid,
            "hyp_id": hid,
            "what": str(what).strip(),
            "result": str(result).strip(),
            "verdict": v,
        })
        target["status"] = v
        _save(workspace_dir, db)
    msg = "Experiment E{} logged for H{} -> {}".format(eid, hid, v.upper())
    if v == "pivot":
        msg += "\nПодход сменился: зафиксируйте новую гипотезу через lab_hyp()."
    elif v == "keep":
        msg += "\nГипотеза подтверждена - можно развивать решение."
    return msg


def lab_show(workspace_dir: str, key: str = "") -> str:
    """Show the whole lab board: hypotheses and experiment history."""
    db = _load(workspace_dir)
    if not db["hypotheses"]:
        return "(lab is empty - register ideas with lab_hyp)"
    lines = ["== HYPOTHESES =="]
    status_icon = {"todo": "[ ]", "keep": "[OK]", "pivot": "[~]", "drop": "[X]"}
    for h in db["hypotheses"]:
        icon = status_icon.get(h.get("status"), "[?]")
        exp = h.get("expected")
        line = "H{} {}: {}{}".format(h["id"], icon, h["idea"],
                                     " (expect: {})".format(exp) if exp else "")
        lines.append(line)
    if db["experiments"]:
        lines.append("\n== EXPERIMENTS ==")
        for e in db["experiments"]:
            lines.append("E{} (H{}, {}): {} -> {}".format(
                e["id"], e["hyp_id"], e.get("verdict", "?"),
                e.get("what", "")[:80], e.get("result", "")[:80]))
    return "\n".join(lines)


def lab_next(workspace_dir: str) -> str:
    """Analyze failure patterns and suggest the next loop move."""
    db = _load(workspace_dir)
    hs = db["hypotheses"]
    todo = [h for h in hs if h.get("status") == "todo"]
    pivots = [h for h in hs if h.get("status") == "pivot"]
    drops = [h for h in hs if h.get("status") == "drop"]
    keeps = [h for h in hs if h.get("status") == "keep"]

    if not hs:
        return ("Лаборатория пуста. Начните с дивергенции: diverge_stimulus / "
                "diverge_cards, лучшие идеи регистрируйте через lab_hyp.")

    parts = []
    parts.append("Статистика: {} todo, {} подтверждено, {} пивотов, {} отброшено".format(
        len(todo), len(keeps), len(pivots), len(drops)))

    if todo:
        parts.append("Следующий шаг: проверьте H{} ('{}') - это старейшая непроверенная гипотеза.".format(
            todo[0]["id"], todo[0]["idea"]))
        parts.append("Совет: один пакетный эксперимент может проверить сразу 2-3 гипотезы.")
    elif keeps:
        parts.append("Все гипотезы проверены; рабочая база: H{}. Развивайте решение или расширяйте набор через diverge_*.".format(
            ", H".join(str(h["id"]) for h in keeps)))

    if len(drops) + len(pivots) >= 3 and not keeps:
        parts.append("Много провалов подряд: смените рамку - прогоните задачу через diverge_persona "
                     "(чужой домен ломает замкнутый контур).")
    if len(drops) >= 5:
        parts.append("Правило остановки близко: если и следующий заход не даст прогресса, "
                     "эскалируйте пользователю с итогами лаборатории (lab_show).")
    return "\n".join(parts)


def make_idea_lab_tools(workspace_dir: str) -> list[ToolSpec]:
    return [
        ToolSpec(name="lab_hyp",
                 description="Register a new hypothesis in the Idea Lab (iteration-loop journal).",
                 input_schema={"type": "object", "properties": {
                     "idea": {"type": "string", "description": "The hypothesis."},
                     "expected": {"type": "string", "description": "What result would confirm it."}},
                     "required": ["idea"]},
                 handler=lambda idea="", expected="": lab_hyp(workspace_dir, idea, expected)),
        ToolSpec(name="lab_exp",
                 description="Log an experiment result for a hypothesis. Verdict: keep (works), pivot (change approach), drop (wrong path).",
                 input_schema={"type": "object", "properties": {
                     "hyp_id": {"type": "string", "description": "Hypothesis id (e.g. '1')."},
                     "what": {"type": "string", "description": "What you tried."},
                     "result": {"type": "string", "description": "What happened."},
                     "verdict": {"type": "string", "description": "keep | pivot | drop"}},
                     "required": ["hyp_id", "verdict"]},
                 handler=lambda hyp_id="", what="", result="", verdict="": lab_exp(
                     workspace_dir, hyp_id, what, result, verdict)),
        ToolSpec(name="lab_show",
                 description="Show the full Idea Lab board: all hypotheses and experiment history.",
                 input_schema={"type": "object", "properties": {}},
                 handler=lambda: lab_show(workspace_dir)),
        ToolSpec(name="lab_next",
                 description="Analyze failure patterns and suggest the next move of the iteration loop.",
                 input_schema={"type": "object", "properties": {}},
                 handler=lambda: lab_next(workspace_dir)),
    ]
