"""Attach grammar notes to Spanish sentences using a hand-written list of regex rules.

The rules are deliberately conservative: missing a note is acceptable, a wrong note is not.
Adding a rule means adding one entry to RULES; no other code changes.
"""

import re

Rule = tuple[re.Pattern[str], str]


def _rule(pattern: str, note: str) -> Rule:
    """Compile a case-insensitive rule so sentence-initial capitals still match."""
    return re.compile(pattern, re.IGNORECASE), note


RULES: list[Rule] = [
    _rule(r"\bojalá\b",
          "Ojalá is followed by the subjunctive"),
    _rule(r"\bhay que\b",
          "Hay que + infinitive = one must / it's necessary to"),
    _rule(r"\btener que\b|\b(tengo|tienes|tiene|tenemos|tienen) que\b",
          "Tener que + infinitive = to have to"),
    _rule(r"\b(voy|vas|va|vamos|van) a [a-záéíóú]+(ar|er|ir)\b",
          "Ir a + infinitive = near future"),
    _rule(r"\b(estoy|estás|está|estamos|están) [a-záéíóú]+(ando|iendo)\b",
          "Estar + gerund = action in progress"),
    _rule(r"\b(me|te|le|nos|les) gustan?\b",
          "Gustar: the thing liked is the subject"),
    _rule(r"\bacab(o|as|a|amos|an) de\b",
          "Acabar de + infinitive = to have just done"),
    _rule(r"\bhace \w+ (que|años|días|meses)\b",
          "Hace + time = ago / for"),

    # --- DRAFT rules: not from the plan. Check each one; delete any you disagree with. ---
    _rule(r"\b(he|has|ha|hemos|habéis|han) [a-záéíóú]+(ado|ido)\b",
          "Haber + past participle = present perfect (have done)"),
    _rule(r"\bsi (tuviera|fuera|pudiera|hubiera|quisiera|supiera)\b",
          "Si + imperfect subjunctive = hypothetical condition"),
    _rule(r"\bpara [a-záéíóú]+(ar|er|ir)\b",
          "Para + infinitive = in order to"),
    _rule(r"\bdeber(ía|ías|íamos|ían)\b",
          "Debería + infinitive = should (advice)"),
    _rule(r"\b(suelo|sueles|suele|solemos|suelen) [a-záéíóú]+(ar|er|ir)\b",
          "Soler + infinitive = to usually do"),
]


def tag_grammar(text: str) -> str | None:
    """Return every matching note joined by '; ', or None if no rule matches."""
    notes = [note for pattern, note in RULES if pattern.search(text)]
    return "; ".join(notes) if notes else None
