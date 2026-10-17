# Edit this line to "formal", "casual" or "pirate" before running, per
# this skill's SKILL.md.
style = "casual"

greetings = {
    "formal": "Good day. It is a pleasure to make your acquaintance.",
    "casual": "Hey there!",
    "pirate": "Ahoy, matey!",
}
print(greetings.get(style, greetings["casual"]))
