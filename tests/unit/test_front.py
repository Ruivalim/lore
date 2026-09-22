"""Front matter: parsing do subconjunto YAML suportado."""

import pytest

from lore.front import FrontMatterError, parse, split_front_matter


def test_parse_scalars():
    front = parse("id: x\ncount: 3\nflag: true\nnothing: null\n")
    assert front == {"id": "x", "count": 3, "flag": True, "nothing": None}


def test_parse_list_of_scalars():
    front = parse("tags:\n  - a\n  - b\n")
    assert front == {"tags": ["a", "b"]}


def test_parse_list_of_maps():
    front = parse("sources:\n  - kind: personal\n    description: homelab\n")
    assert front == {
        "sources": [{"kind": "personal", "description": "homelab"}]
    }


def test_parse_empty_list():
    assert parse("sources: []\n") == {"sources": []}


def test_duplicate_key_fails():
    with pytest.raises(FrontMatterError):
        parse("id: a\nid: b\n")


def test_split_ok():
    front, body = split_front_matter("---\nid: a\n---\n\n# T\n")
    assert front == {"id": "a"}
    assert body.strip() == "# T"


def test_split_missing_open_fails():
    with pytest.raises(FrontMatterError):
        split_front_matter("id: a\n---\n")


def test_split_missing_close_fails():
    with pytest.raises(FrontMatterError):
        split_front_matter("---\nid: a\n")
