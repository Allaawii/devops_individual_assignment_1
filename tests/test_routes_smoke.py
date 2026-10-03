"""Smoke tests for the pages, through Flask's test client against a temporary database."""

import pytest

from trainer import create_app
from trainer.config import Config


@pytest.fixture
def client(tmp_path):
    return create_app(Config(data_dir=str(tmp_path))).test_client()


def _add(client, spanish="Hay que estudiar.", english="One must study.", note=""):
    return client.post("/sentences/new", data={"spanish": spanish, "english": english, "grammar_note": note})


# ----- content pages -----

def test_add_sentence_form_renders(client):
    response = client.get("/sentences/new")
    assert response.status_code == 200
    assert b'name="spanish"' in response.data


def test_adding_a_sentence_redirects_to_its_page(client):
    response = _add(client)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/sentences/1")

    page = client.get("/sentences/1").get_data(as_text=True)
    assert "Hay que estudiar." in page
    assert "Hay que + infinitive" in page  # automatic grammar note
    assert "estudiar" in page               # word chip
    assert "Added by you" in page


@pytest.mark.parametrize("spanish, english", [("", "Hello"), ("Hola", "")])
def test_missing_text_shows_the_form_again_with_an_error(client, spanish, english):
    response = _add(client, spanish, english)
    assert response.status_code == 400
    assert b"required" in response.data


def test_duplicate_sentence_is_rejected(client):
    _add(client)
    response = _add(client)
    assert response.status_code == 400
    assert "already exists" in response.get_data(as_text=True)


def test_sentence_list_shows_added_sentences(client):
    _add(client)
    page = client.get("/sentences").get_data(as_text=True)
    assert "Hay que estudiar." in page
    assert "(1)" in page


def test_bad_page_number_falls_back_to_page_1(client):
    assert client.get("/sentences?page=abc").status_code == 200


def test_unknown_sentence_is_404(client):
    assert client.get("/sentences/999").status_code == 404


def test_word_meaning_can_be_saved(client):
    _add(client, "El gato come.", "The cat eats.")
    response = client.post("/words/1", data={"meaning": "cat", "page": "1"})
    assert response.status_code == 302
    page = client.get("/words").get_data(as_text=True)
    assert 'value="cat"' in page


def test_meaning_for_unknown_word_is_404(client):
    assert client.post("/words/999", data={"meaning": "x"}).status_code == 404


def test_user_text_is_escaped(client):
    _add(client, "<script>alert(1)</script> gato", "x")
    page = client.get("/sentences/1").get_data(as_text=True)
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;" in page
