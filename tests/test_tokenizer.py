"""Tests for trainer.content.tokenizer.extract_words."""

from trainer.content.tokenizer import STOPWORDS, extract_words


def test_keeps_accents_enye_and_diaeresis():
    assert extract_words("canción niño pingüino") == ["canción", "niño", "pingüino"]


def test_removes_inverted_punctuation():
    assert extract_words("¿Dónde vives? ¡Muy bien!") == ["dónde", "vives", "bien"]


def test_lowercases_everything():
    assert extract_words("MADRID Árbol") == ["madrid", "árbol"]


def test_drops_stopwords():
    assert extract_words("el perro de la casa") == ["perro", "casa"]


def test_removes_duplicates_keeping_first_order():
    assert extract_words("gato perro gato casa perro") == ["gato", "perro", "casa"]


def test_drops_digits():
    assert extract_words("tengo 25 años") == ["tengo", "años"]


def test_empty_text_gives_empty_list():
    assert extract_words("") == []


def test_only_stopwords_gives_empty_list():
    assert extract_words("el de la") == []


def test_stopwords_are_all_lowercase():
    assert all(word == word.lower() for word in STOPWORDS)


def test_corpus_names_are_not_vocabulary():
    assert extract_words("Tom y Mary comen pan.") == ["comen", "pan"]
