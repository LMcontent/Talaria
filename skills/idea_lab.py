# -*- coding: utf-8 -*-
"""Idea Lab: a visible iteration loop - hypotheses, experiments, pivots.

Backed by ./state/lab.json so the board survives across code runs and sessions.
"""
import json
import os

from talaria.providers.base import ToolSpec

_LAB_DIR = os.path.join(".", "state")
_LAB_FILE = os.path.join(_LAB_DIR, "lab.json")


def _load():
    if not os.path.isfile(_LAB_FILE):
        return {"hypotheses": [], "experiments": []}
    try:
        with open(_LAB_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
        if not isinstance(d, dict):
            return {"hypotheses": [], "experiments": []}
        d.setdefault("hypotheses", [])
        d.setdefault("experiments", [])
        return d
    except Exception:
        return {"hypotheses": [], "experiments": []}


def _save(db):
    os.makedirs(_LAB_DIR, exist_ok=True)
    tmp = _LAB_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _LAB_FILE)


def lab_hyp(idea: str = "", expected: str = "") -> str:
    """Register a new hypothesis (idea + what we expect to see)."""
    idea = str(idea).strip()
    if not idea:
        return "Error: empty idea"
    db = _load()
    hid = max([h.get("id", 0) for h in db["hypotheses"]], default=0) + 1
    db["hypotheses"].append({
        "id": hid,
        "idea": idea,
        "expected": str(expected).strip(),
        "status": "todo",
    })
    _save(db)
    return "Hypothesis H{} registered: {}".format(hid, idea)


def lab_exp(hyp_id: str = "", what: str = "", result: str = "", verdict: str = "") -> str:
    """Log an experiment outcome for a hypothesis. Verdict: keep | pivot | drop."""
    try:
        hid = int(str(hyp_id).strip())
    except ValueError:
        return "Error: hyp_id must be an integer."
    v = str(verdict).strip().lower()
    if v not in ("keep", "pivot", "drop"):
        return "Error: verdict must be one of: keep, pivot, drop"
    db = _load()
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
    _save(db)
    msg = "Experiment E{} logged for H{} -> {}".format(eid, hid, v.upper())
    if v == "pivot":
        msg += "\nПодход сменился: зафиксируйте новую гипотезу через lab_hyp()."
    elif v == "keep":
        msg += "\nГипотеза подтверждена - можно развивать решение."
    return msg


def lab_show(key: str = "") -> str:
    """Show the whole lab board: hypotheses and experiment history."""
    db = _load()
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


def lab_next() -> str:
    """Analyze failure patterns and suggest the next loop move."""
    db = _load()
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


TOOLS = [
    ToolSpec(name="lab_hyp",
             description="Register a new hypothesis in the Idea Lab (iteration-loop journal).",
             input_schema={"type": "object", "properties": {
                 "idea": {"type": "string", "description": "The hypothesis."},
                 "expected": {"type": "string", "description": "What result would confirm it."}},
                 "required": ["idea"]},
             handler=lab_hyp),
    ToolSpec(name="lab_exp",
             description="Log an experiment result for a hypothesis. Verdict: keep (works), pivot (change approach), drop (wrong path).",
             input_schema={"type": "object", "properties": {
                 "hyp_id": {"type": "string", "description": "Hypothesis id (e.g. '1')."},
                 "what": {"type": "string", "description": "What you tried."},
                 "result": {"type": "string", "description": "What happened."},
                 "verdict": {"type": "string", "description": "keep | pivot | drop"}},
                 "required": ["hyp_id", "verdict"]},
             handler=lab_exp),
    ToolSpec(name="lab_show",
             description="Show the full Idea Lab board: all hypotheses and experiment history.",
             input_schema={"type": "object", "properties": {}},
             handler=lab_show),
    ToolSpec(name="lab_next",
             description="Analyze failure patterns and suggest the next move of the iteration loop.",
             input_schema={"type": "object", "properties": {}},
             handler=lab_next),
]
