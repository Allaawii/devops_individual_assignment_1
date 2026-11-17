"""Tests for content.grammar_rules: one matching and one non-matching sentence per rule."""

import pytest

from content.grammar_rules import RULES, tag_grammar

# (sentence that should match, similar sentence that should not, fragment of the expected note)
CASES = [
    ("Ojalá llueva mañana.", "Espero que llueva mañana.", "Ojalá"),
    ("Hay que estudiar mucho.", "Hay un gato en la casa.", "Hay que"),
    ("Tengo que trabajar hoy.", "Tengo un perro.", "Tener que"),
    ("Vamos a comer pronto.", "Vamos a la playa.", "Ir a"),
    ("Estoy comiendo una manzana.", "Estoy cansado hoy.", "Estar + gerund"),
    ("Me gustan los perros.", "Te quiero mucho.", "Gustar"),
    ("Acabo de llegar a casa.", "Acabo el trabajo pronto.", "Acabar de"),
    ("Vivo aquí hace dos años.", "Hace calor hoy.", "Hace + time"),
    ("He comido paella.", "Comí paella ayer.", "present perfect"),
    ("Si tuviera dinero, viajaría.", "Si tengo dinero, viajo.", "hypothetical"),
    ("Estudio para aprender.", "Este regalo es para ti.", "in order to"),
    ("Deberías descansar más.", "Debes descansar más.", "should"),
    ("Suelo caminar por la mañana.", "El suelo está mojado.", "usually"),
]


def test_every_rule_has_a_test_case():
    assert len(CASES) == len(RULES)


@pytest.mark.parametrize("positive, negative, fragment", CASES)
def test_rule_matches_positive_example(positive, negative, fragment):
    assert fragment in (tag_grammar(positive) or "")


@pytest.mark.parametrize("positive, negative, fragment", CASES)
def test_rule_ignores_negative_example(positive, negative, fragment):
    assert fragment not in (tag_grammar(negative) or "")


def test_matching_ignores_case():
    assert "Ojalá" in tag_grammar("OJALÁ LLUEVA")


def test_several_matches_are_joined_in_rule_order():
    notes = tag_grammar("Hay que estudiar porque vamos a viajar.").split("; ")
    assert len(notes) == 2
    assert notes[0].startswith("Hay que")
    assert notes[1].startswith("Ir a")


def test_no_match_returns_none():
    assert tag_grammar("El perro come.") is None
