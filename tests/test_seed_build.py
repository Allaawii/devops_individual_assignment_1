"""Tests for the offline seed builder (trainer.content.seed_build)."""

import csv
import zipfile

from trainer.content.seed_build import (
    Candidate, Tier, build_seed, deduplicate, difficulty, frequency_ranks, is_suitable,
    parse_line, read_lines, select_tiered, select_varied, spread_evenly, write_seed,
)

ATTRIBUTION = "CC-BY 2.0 (France) Attribution: tatoeba.org #2877 (CM) & #1004 (sabretou)"


def _line(english: str, spanish: str) -> str:
    return f"{english}\t{spanish}\t{ATTRIBUTION}"


def _candidate(spanish: str, english: str = "x") -> Candidate:
    return parse_line(_line(english, spanish))


# ----- parse_line -----

def test_parse_line_reads_all_three_fields():
    candidate = parse_line(_line("The cat eats bread.", "El gato come pan."))
    assert (candidate.english, candidate.spanish, candidate.attribution) == (
        "The cat eats bread.", "El gato come pan.", ATTRIBUTION)
    assert candidate.words == ("gato", "come", "pan")
    assert candidate.length == 4


def test_malformed_lines_are_skipped():
    assert parse_line("no tabs at all") is None
    assert parse_line("Hello\tHola") is None
    assert parse_line(f"Hello\t\t{ATTRIBUTION}") is None


# ----- is_suitable -----

def test_three_to_twelve_tokens_are_kept():
    assert is_suitable(_candidate("El gato come."))
    assert not is_suitable(_candidate("Hola amigo."))
    assert not is_suitable(_candidate("uno dos tres cuatro cinco seis siete ocho nueve diez once doce trece"))


def test_sentences_with_digits_are_dropped():
    assert not is_suitable(_candidate("Tengo 3 gatos en casa."))


def test_sentences_of_only_stopwords_are_dropped():
    assert not is_suitable(_candidate("Es que no."))


# ----- deduplicate -----

def test_deduplicate_keeps_the_first_translation():
    first, second = _candidate("El gato come.", "The cat eats."), _candidate("El gato come.", "The cat is eating.")
    assert deduplicate([first, second]) == [first]


# ----- ranks and difficulty -----

def test_most_common_word_gets_rank_1_and_ties_go_alphabetically():
    ranks = frequency_ranks([_candidate("El gato come."), _candidate("El perro come."), _candidate("Un gato duerme.")])
    assert ranks == {"come": 1, "gato": 2, "duerme": 3, "perro": 4}


def test_difficulty_is_the_rarest_word_rank_then_length():
    candidate = _candidate("El gato come pan.")
    assert difficulty(candidate, {"gato": 2, "come": 1, "pan": 9}) == (9, 4)


# ----- build_seed -----

CORPUS = [
    _line("My cat eats a lot of bread today.", "Mi gato come mucho pan hoy."),
    _line("The dog eats.", "El perro come."),
    _line("The cat drinks water.", "El gato bebe agua."),
    _line("The cat eats bread.", "El gato come pan."),
    "a malformed line",
    _line("I have 2 cats.", "Tengo 2 gatos ahora."),
]


def test_sentences_built_from_common_words_come_first():
    chosen, _ = build_seed(CORPUS, per_level=10)
    assert [c.spanish for c in chosen] == [
        "El gato come pan.", "El gato bebe agua.", "Mi gato come mucho pan hoy.", "El perro come.",
    ]


def test_shorter_sentence_wins_a_tie():
    chosen, _ = build_seed([_line("x", "El gato come el pan."), _line("x", "Gato come pan.")], per_level=10)
    assert [c.spanish for c in chosen] == ["Gato come pan.", "El gato come el pan."]


def test_at_most_three_sentences_share_the_same_rarest_word():
    ranks = {"gato": 1, "come": 2, "pan": 3}
    same_rarest = [_candidate(text) for text in ["Gato come.", "El gato come.", "Un gato come.", "Mi gato come."]]
    new_word = _candidate("Gato come pan.")
    chosen = select_varied(same_rarest + [new_word], ranks)
    assert chosen == same_rarest[:3] + [new_word]   # the 4th "come" sentence is skipped for new vocabulary


def test_per_level_caps_each_tier_and_only_used_words_keep_a_rank():
    chosen, ranks = build_seed(CORPUS, per_level=2)
    assert len(chosen) == 2
    assert set(ranks) == {word for candidate in chosen for word in candidate.words}


# ----- tiers -----

TIER_RANKS = {"gato": 1, "come": 2, "pan": 3, "agua": 4}
SHORT_EASY = _candidate("Gato come.")                      # rarest rank 2, 2 tokens
SHORT_HARDER = _candidate("Gato come pan.")                # rarest rank 3, 3 tokens
LONG_HARDEST = _candidate("El gato come pan con agua.")    # rarest rank 4, 6 tokens
ORDERED = [SHORT_EASY, SHORT_HARDER, LONG_HARDEST]


def test_each_tier_needs_its_rarest_word_rank_and_minimum_length():
    tiers = (Tier(max_rank=2, min_tokens=1), Tier(max_rank=4, min_tokens=5))
    assert select_tiered(ORDERED, TIER_RANKS, per_level=10, tiers=tiers) == [SHORT_EASY, LONG_HARDEST]


def test_sentences_rarer_than_the_last_tier_are_left_out():
    assert select_tiered(ORDERED, TIER_RANKS, per_level=10, tiers=(Tier(3, 1),)) == [SHORT_EASY, SHORT_HARDER]


def test_spread_evenly_keeps_order_and_covers_the_whole_list():
    assert spread_evenly(list(range(10)), 3) == [0, 3, 6]
    assert spread_evenly([1, 2], 5) == [1, 2]


# ----- file input and output -----

def test_read_lines_finds_the_sentence_file_in_the_zip(tmp_path):
    zip_path = tmp_path / "spa-eng.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("_about.txt", "about")
        archive.writestr("spa.txt", _line("Hello.", "¿Qué tal?") + "\n" + _line("Bye.", "Adiós."))
    assert read_lines(zip_path) == [_line("Hello.", "¿Qué tal?"), _line("Bye.", "Adiós.")]


def test_write_seed_produces_tab_separated_files(tmp_path):
    chosen, ranks = build_seed(CORPUS + [_line('He said "no".', 'Él dijo "nunca" ayer.')], per_level=10)
    write_seed(tmp_path, chosen, ranks)

    with open(tmp_path / "sentences.tsv", encoding="utf-8", newline="") as file:
        rows = list(csv.reader(file, delimiter="\t"))
    assert rows[0] == ["El gato come pan.", "The cat eats bread.", ATTRIBUTION]
    assert ["Él dijo \"nunca\" ayer.", 'He said "no".', ATTRIBUTION] in rows

    with open(tmp_path / "words.tsv", encoding="utf-8", newline="") as file:
        words = list(csv.reader(file, delimiter="\t"))
    assert words[0] == ["come", "1"]
    assert [int(rank) for _, rank in words] == sorted(int(rank) for _, rank in words)
