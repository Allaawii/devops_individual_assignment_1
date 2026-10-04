"""Content pages. Thin: read the request, call ContentService, then render or redirect."""

from flask import Blueprint, abort, redirect, render_template, request, url_for

from trainer.content.service import ContentService


def create_blueprint(content: ContentService) -> Blueprint:
    """Build the 'content' blueprint around the service it should use."""
    bp = Blueprint("content", __name__)

    @bp.get("/sentences/new")
    def new_sentence():
        return render_template("content/sentence_form.html", form={}, error=None)

    @bp.post("/sentences/new")
    def create_sentence():
        form = request.form
        try:
            sentence = content.add_sentence(form.get("spanish", ""), form.get("english", ""),
                                            form.get("grammar_note"))
        except ValueError as error:
            return render_template("content/sentence_form.html", form=form, error=str(error)), 400
        return redirect(url_for("content.sentence_detail", sentence_id=sentence.id))

    @bp.get("/sentences")
    def list_sentences():
        return render_template("content/sentence_list.html", page=content.list_sentences(_page_number()),
                               total=content.count_sentences())

    @bp.get("/sentences/<int:sentence_id>")
    def sentence_detail(sentence_id: int):
        detail = content.get_sentence(sentence_id)
        if detail is None:
            abort(404)
        return render_template("content/sentence_detail.html", detail=detail)

    @bp.get("/words")
    def list_words():
        return render_template("content/word_list.html", page=content.list_words(_page_number()))

    @bp.post("/words/<int:word_id>")
    def save_meaning(word_id: int):
        if content.get_word(word_id) is None:
            abort(404)
        content.set_meaning(word_id, request.form.get("meaning"))
        return redirect(url_for("content.list_words", page=request.form.get("page", 1, type=int)))

    return bp


def _page_number() -> int:
    """The ?page= number from the URL; a missing or non-numeric value means page 1."""
    return request.args.get("page", 1, type=int)
