"""Split Spanish text into the content words worth learning."""

import re

# Common function words that carry little meaning on their own.
STOPWORDS = frozenset({
    "el", "la", "los", "las", "un", "una", "unos", "unas",
    "de", "del", "al", "a", "en", "y", "o", "que", "por", "para", "con",
    "se", "lo", "le", "les", "me", "te", "nos",
    "mi", "tu", "su", "es", "no", "sí", "pero", "como", "más", "muy", "ya",
    "este", "esta", "eso",
})

# Names the Tatoeba corpus uses in thousands of sentences. They aren't Spanish vocabulary.
NAMES = frozenset({"tom", "mary"})

IGNORED = STOPWORDS | NAMES

# Runs of Spanish letters. Punctuation (¿¡.,!?), quotes and digits are not matched.
WORD_PATTERN = re.compile(r"[a-záéíóúüñ]+")


def extract_words(text: str) -> list[str]:
    """Return the lowercase words worth learning in `text`, without duplicates, in order of appearance."""
    tokens = WORD_PATTERN.findall(text.lower())
    content_words = [token for token in tokens if token not in IGNORED]
    return list(dict.fromkeys(content_words))
