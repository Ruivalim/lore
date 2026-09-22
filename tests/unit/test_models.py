"""Validação de front matter e máquina de estados."""

import pytest

from lore.models import TYPES, Doc, can_transition, parse_doc, transition, validate


def _front(**over):
    base = {
        "id": "teste-doc",
        "title": "Teste",
        "type": "note",
        "status": "draft",
        "tags": ["x"],
        "created_at": "2026-01-01",
        "updated_at": "2026-01-02",
        "sources": [],
    }
    base.update(over)
    return base


def test_valid_note_empty_sources():
    assert validate(_front(), "# T\n\ncorpo\n") == []


def test_missing_required():
    front = _front()
    del front["id"]
    errors = validate(front, "corpo")
    assert any("id" in err for err in errors)


def test_bad_id():
    for bad in ("Maiusculo", "-lider", "com espaco", "under_score"):
        errors = validate(_front(id=bad), "corpo")
        assert errors, bad


def test_bad_type():
    errors = validate(_front(type="email"), "corpo")
    assert any("type" in err for err in errors)


def test_bad_status():
    errors = validate(_front(status="rascunho"), "corpo")
    assert any("status" in err for err in errors)


def test_verified_requires_verified_at():
    errors = validate(_front(status="verified"), "corpo")
    assert any("verified_at" in err for err in errors)
    assert validate(_front(status="verified", verified_at="2026-01-03"), "corpo") == []


def test_empty_sources_only_note_or_personal():
    assert any(
        "sources" in err for err in validate(_front(type="howto"), "corpo")
    )
    front = _front(type="howto", sources=[{"kind": "personal", "description": "lab"}])
    assert validate(front, "corpo") == []


def test_personal_source_requires_description():
    front = _front(type="howto", sources=[{"kind": "personal"}])
    assert any("description" in err for err in validate(front, "corpo"))


def test_external_source_requires_url():
    front = _front(type="research", sources=[{"title": "sem url"}])
    assert any("url" in err for err in validate(front, "corpo"))


def test_bad_dates():
    for key in ("created_at", "updated_at"):
        errors = validate(_front(**{key: "01-01-2026"}), "corpo")
        assert any(key in err for err in errors), key


def test_empty_body():
    assert any("corpo" in err for err in validate(_front(), "   \n"))


def test_all_transitions_covered():
    assert can_transition("draft", "verified")
    assert can_transition("draft", "archived")
    assert not can_transition("draft", "stale")
    assert can_transition("verified", "stale")
    assert can_transition("verified", "archived")
    assert not can_transition("verified", "draft")
    assert can_transition("stale", "verified")
    assert not can_transition("archived", "draft")


def test_promote_requires_human():
    doc = Doc(front=_front(), body="corpo")
    assert transition(doc, "verified") != []
    assert doc.status == "draft"
    assert transition(doc, "verified", human=True) == []
    assert doc.status == "verified"


def test_forbidden_transition():
    doc = Doc(front=_front(), body="corpo")
    assert transition(doc, "stale", human=True) != []
    assert doc.status == "draft"


def test_parse_doc_never_raises():
    doc = parse_doc("sem front matter", "x.md")
    assert not doc.valid
    assert doc.errors


def test_parse_doc_invalid_reports():
    from tests.conftest import INVALID_NO_ID

    doc = parse_doc(INVALID_NO_ID, "sem-id.md")
    assert not doc.valid
    assert any("id" in err for err in doc.errors)


@pytest.mark.parametrize("doc_type", TYPES)
def test_all_types_accepted(doc_type):
    sources = [] if doc_type == "note" else [{"url": "https://example.org"}]
    assert validate(_front(type=doc_type, sources=sources), "corpo") == []
