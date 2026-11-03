"""Which predict_yue_coll rules apply to an MC reading.

Mirrors the conditions in yue_reflex (modules/ltc-pron/predict.lua), so the
analysis scripts can attribute each colloquial form to its rule. Keep the
two in sync when a rule changes.
"""

FULLY_VOICED = {3, 7, 11, 15, 17, 20, 22, 25, 27, 30, 33}
GENG_2 = {109, 110, 113, 114, 117, 118, 119, 120}
GENG_34 = {111, 115, 121, 123, 125, 127}

COLLOQUIAL_RULES = {
    "geng2": "梗二 -aang/-aak",
    "geng34": "梗三四 -eng/-ek",
    "de": "德 -aak",
    "tie": "怗 -aap",
    "zhi": "脂心 -ei",
    "voiced_rising": "全濁上 aspirate + 5",
}


def colloquial_rules(cat) -> tuple[str, ...]:
    """Keys of COLLOQUIAL_RULES whose conditions the categories meet."""
    out = []
    if cat.final in GENG_2:
        out.append("geng2")
    if cat.final in GENG_34:
        out.append("geng34")
    if cat.final == 131:
        out.append("de")
    if cat.final == 158:
        out.append("tie")
    if cat.final == 15 and cat.initial == 16:
        out.append("zhi")
    if cat.tone == 2 and cat.initial in FULLY_VOICED:
        out.append("voiced_rising")
    return tuple(out)


def rule_label(cat) -> str | None:
    keys = colloquial_rules(cat)
    return " + ".join(COLLOQUIAL_RULES[k] for k in keys) or None
