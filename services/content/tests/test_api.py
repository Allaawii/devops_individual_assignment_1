"""Tests for the JSON API, through Flask's test client with fake repositories."""

import pytest

from content.placement import LEVELS
from content.service import PAGE_SIZE


@pytest.fixture
def seeded(service):
    """50 seed sentences: enough for a placement quiz (bands of 10)."""
    service.import_seed([(f"Frase número {i}.", f"Sentence {i}.", "tatoeba") for i in range(1, 51)], {})
    return service


def _post_sentence(client, **body):
    return client.post("/sentences", json={"spanish": "El gato come.", "english": "The cat eats.", **body})


# ----- sentences -----

def test_post_sentence_returns_201_and_the_sentence(client):
    response = _post_sentence(client, grammar_note="My note")
    assert response.status_code == 201
    assert response.get_json() == {"id": 1, "spanish_text": "El gato come.", "english_text": "The cat eats.",
                                   "grammar_note": "My note", "source": "user", "created_at": "2026-11-16T10:30:00",
                                   "level": None}


def test_post_duplicate_sentence_is_a_400_with_the_reason(client):
    _post_sentence(client)
    response = _post_sentence(client)
    assert response.status_code == 400
    assert response.get_json()["error"] == "invalid_sentence"
    assert "already exists" in response.get_json()["message"]


@pytest.mark.parametrize("body", [None, {"spanish": "Hola"}, {"spanish": 1, "english": "x"},
                                  {"spanish": "Hola", "english": "Hi", "grammar_note": 5}])
def test_post_sentence_with_a_bad_body_is_a_400(client, body):
    response = client.post("/sentences", json=body) if body is not None else client.post("/sentences", data="x")
    assert response.status_code == 400
    assert response.get_json()["error"] == "invalid_sentence"


def test_list_sentences_is_paged_with_a_total(client, service):
    for i in range(PAGE_SIZE + 1):
        service.add_sentence(f"Frase {i}", f"Sentence {i}")
    first = client.get("/sentences").get_json()
    second = client.get("/sentences?page=2").get_json()
    assert (len(first["items"]), first["page"], first["has_next"], first["total"]) == (PAGE_SIZE, 1, True, 51)
    assert (len(second["items"]), second["page"], second["has_next"]) == (1, 2, False)


def test_non_numeric_page_means_page_1(client):
    assert client.get("/sentences?page=abc").get_json()["page"] == 1


def test_get_sentence_has_its_words_and_key_words(client, service):
    service.import_seed([("El perro come pan aquí.", "The dog eats bread here.", "tatoeba")],
                        {"aquí": 1, "come": 2, "perro": 3, "pan": 4})
    body = client.get("/sentences/1").get_json()
    assert body["sentence"]["spanish_text"] == "El perro come pan aquí."
    assert [w["headword"] for w in body["words"]] == ["aquí", "come", "perro", "pan"]
    assert [w["headword"] for w in body["key_words"]] == ["pan", "perro", "come"]


def test_unknown_sentence_is_a_json_404(client):
    response = client.get("/sentences/99")
    assert response.status_code == 404
    assert response.get_json() == {"error": "not_found", "message": "There is no sentence with id 99."}


# ----- feed -----

def test_feed_lists_sentence_and_word_ids_after_an_id(client, service):
    service.add_sentence("El gato come.", "The cat eats.")
    service.add_sentence("Hola", "Hello")
    assert client.get("/sentences/feed?after_id=1").get_json() == {"items": [{"id": 2, "word_ids": [3]}]}
    assert len(client.get("/sentences/feed?after_id=0&limit=1").get_json()["items"]) == 1
    assert client.get("/sentences/feed?after_id=2").get_json() == {"items": []}


# ----- words -----

def test_list_words(client, service):
    service.add_sentence("El gato come.", "The cat eats.")
    body = client.get("/words").get_json()
    assert [w["headword"] for w in body["items"]] == ["gato", "come"]
    assert (body["page"], body["has_next"]) == (1, False)


def test_get_word_has_example_sentences(client, service):
    service.add_sentence("El gato come.", "The cat eats.")
    body = client.get("/words/1").get_json()
    assert body["word"] == {"id": 1, "headword": "gato", "meaning": None, "frequency_rank": None}
    assert [s["id"] for s in body["examples"]] == [1]


def test_unknown_word_is_a_404(client):
    assert client.get("/words/7").status_code == 404


def test_put_meaning_saves_and_clears_it(client, service):
    service.add_sentence("El gato come.", "The cat eats.")
    assert client.put("/words/1/meaning", json={"meaning": " cat "}).get_json()["meaning"] == "cat"
    assert client.put("/words/1/meaning", json={"meaning": None}).get_json()["meaning"] is None


@pytest.mark.parametrize("body", [{"meaning": 3}, {"meaning": "x" * 501}])
def test_put_bad_meaning_is_a_400(client, service, body):
    service.add_sentence("El gato come.", "The cat eats.")
    response = client.put("/words/1/meaning", json=body)
    assert response.status_code == 400
    assert response.get_json()["error"] == "invalid_meaning"


def test_put_meaning_of_unknown_word_is_a_404(client):
    assert client.put("/words/9/meaning", json={"meaning": "cat"}).status_code == 404


# ----- placement -----

def test_quiz_never_sends_the_answer(client, seeded):
    body = client.get("/placement/quiz").get_json()
    assert body["levels"] == list(LEVELS)
    assert len(body["questions"]) == 8
    assert set(body["questions"][0]) == {"field", "spanish", "options", "level"}


def test_score_returns_level_and_material_to_skip(client, seeded):
    answers = {q.field: q.answer for q in seeded.placement_quiz() if q.level == 0}
    body = client.post("/placement/score", json={"answers": answers}).get_json()
    assert (body["level"], body["level_name"]) == (1, "Beginner")
    assert body["sentence_ids"] == list(range(1, 11))
    assert len(body["word_ids"]) == 2   # frase, número


@pytest.mark.parametrize("body", [{}, {"answers": []}, {"answers": {"q1": 2}}])
def test_score_with_bad_answers_is_a_400(client, body):
    response = client.post("/placement/score", json=body)
    assert response.status_code == 400
    assert response.get_json()["error"] == "invalid_answers"
