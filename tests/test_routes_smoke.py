"""Smoke tests for the content pages (fixtures `client` and `add_sentence` are in conftest.py)."""

import pytest

HAY_QUE = ("Hay que estudiar.", "One must study.")


def test_add_sentence_form_renders(client):
    response = client.get("/sentences/new")
    assert response.status_code == 200
    assert b'name="spanish"' in response.data


def test_adding_a_sentence_redirects_to_its_page(client, add_sentence):
    response = add_sentence(*HAY_QUE)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/sentences/1")

    page = client.get("/sentences/1").get_data(as_text=True)
    assert "Hay que estudiar." in page
    assert "Hay que + infinitive" in page  # automatic grammar note
    assert "estudiar" in page               # word chip
    assert "Added by you" in page


@pytest.mark.parametrize("spanish, english", [("", "Hello"), ("Hola", "")])
def test_missing_text_shows_the_form_again_with_an_error(add_sentence, spanish, english):
    response = add_sentence(spanish, english)
    assert response.status_code == 400
    assert b"required" in response.data


def test_duplicate_sentence_is_rejected(add_sentence):
    add_sentence(*HAY_QUE)
    response = add_sentence(*HAY_QUE)
    assert response.status_code == 400
    assert "already exists" in response.get_data(as_text=True)


def test_sentence_list_shows_added_sentences(client, add_sentence):
    add_sentence(*HAY_QUE)
    page = client.get("/sentences").get_data(as_text=True)
    assert "Hay que estudiar." in page
    assert "(1)" in page


def test_bad_page_number_falls_back_to_page_1(client):
    assert client.get("/sentences?page=abc").status_code == 200


def test_unknown_sentence_is_404(client):
    assert client.get("/sentences/999").status_code == 404


def test_word_meaning_can_be_saved(client, add_sentence):
    add_sentence("El gato come.", "The cat eats.")
    response = client.post("/words/1", data={"meaning": "cat", "page": "1"})
    assert response.status_code == 302
    assert 'value="cat"' in client.get("/words").get_data(as_text=True)


def test_meaning_for_unknown_word_is_404(client):
    assert client.post("/words/999", data={"meaning": "x"}).status_code == 404


def test_user_text_is_escaped(client, add_sentence):
    add_sentence("<script>alert(1)</script> gato", "x")
    page = client.get("/sentences/1").get_data(as_text=True)
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;" in page
