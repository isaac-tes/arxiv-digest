from __future__ import annotations

import pytest

import zotero_bridge as zb

SAMPLE_ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/1810.04805v2</id>
    <updated>2019-05-24T00:00:00Z</updated>
    <title>BERT: Pre-training of Deep Bidirectional Transformers</title>
    <summary>We introduce a language representation model called BERT.</summary>
    <author><name>Jacob Devlin</name></author>
    <author><name>Ming-Wei Chang</name></author>
    <arxiv:comment>13 pages</arxiv:comment>
    <link href="http://arxiv.org/abs/1810.04805v2" rel="alternate" type="text/html"/>
    <category term="cs.CL"/>
    <arxiv:primary_category term="cs.CL"/>
  </entry>
</feed>
"""


class _MockResponse:
    def __init__(self, content: bytes = b"", text: str = "", status_code: int = 200, json_data=None, headers=None):
        self.content = content
        self.text = text
        self.status_code = status_code
        self._json = json_data
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._json


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("https://arxiv.org/abs/2607.21663", "2607.21663"),
        ("2607.21663", "2607.21663"),
        ("arXiv:2607.21663", "2607.21663"),
        ("https://arxiv.org/pdf/1810.04805v2", "1810.04805"),
        ("https://arxiv.org/abs/cond-mat/0603274", "cond-mat/0603274"),
        ("", ""),
        ("not an arxiv thing", "not an arxiv thing"),
    ],
)
def test_arxiv_id_from_input(raw, expected):
    assert zb.arxiv_id_from_input(raw) == expected


def test_category_tag_maps_subcategory_with_parent_prefix():
    assert zb._category_tag("cond-mat.mes-hall") == "Condensed Matter - Mesoscale and Nanoscale Physics"
    assert zb._category_tag("quant-ph") == "Quantum Physics"
    assert zb._category_tag("cs.CL") == "Computer Science - Computation and Language"


def test_category_tag_falls_back_to_raw_for_unknown():
    assert zb._category_tag("zzz.unknown") == "zzz.unknown"


def test_build_preprint_item_replicates_connector_fields():
    import xml.etree.ElementTree as ET

    root = ET.fromstring(SAMPLE_ATOM)
    entry = root.find("{http://www.w3.org/2005/Atom}entry")
    item = zb.build_preprint_item(entry, version="2")

    assert item["itemType"] == "preprint"
    assert item["title"] == "BERT: Pre-training of Deep Bidirectional Transformers"
    assert item["archiveID"] == "arXiv:1810.04805"
    assert item["DOI"] == "10.48550/arXiv.1810.04805"
    assert item["url"] == "http://arxiv.org/abs/1810.04805"
    assert item["repository"] == "arXiv"
    assert item["publisher"] == "arXiv"
    assert item["number"] == "arXiv:1810.04805"
    assert "version: 2" in item["extra"]
    assert item["creators"] == [
        {"creatorType": "author", "firstName": "Jacob", "lastName": "Devlin"},
        {"creatorType": "author", "firstName": "Ming-Wei", "lastName": "Chang"},
    ]
    assert item["notes"] == [{"note": "Comment: 13 pages"}]
    assert {"tag": "Computer Science - Computation and Language"} in item["tags"]
    assert {"tag": "arxiv-digest"} in item["tags"]
    titles = [a["title"] for a in item["attachments"]]
    assert titles == ["Preprint PDF", "Snapshot"]


def test_fetch_arxiv_atom_returns_none_for_bad_id(monkeypatch):
    def _get(url, *args, **kwargs):
        return _MockResponse(content=b"<feed xmlns='http://www.w3.org/2005/Atom'></feed>")

    monkeypatch.setattr(zb.requests, "get", _get)
    assert zb.fetch_arxiv_atom("9999.99999") is None


def test_fetch_arxiv_atom_parses_entry(monkeypatch):
    def _get(url, *args, **kwargs):
        return _MockResponse(content=SAMPLE_ATOM.encode("utf-8"))

    monkeypatch.setattr(zb.requests, "get", _get)
    entry = zb.fetch_arxiv_atom("1810.04805")
    assert entry is not None
    assert entry.find("{http://www.w3.org/2005/Atom}title").text.startswith("BERT")


def test_zotero_available_true_when_reachable(monkeypatch):
    def _get(url, *args, **kwargs):
        return _MockResponse(text="[]", status_code=200)

    monkeypatch.setattr(zb.requests, "get", _get)
    assert zb.zotero_available() is True


def test_zotero_available_false_when_unreachable(monkeypatch):
    def _get(url, *args, **kwargs):
        raise zb.requests.ConnectionError("refused")

    monkeypatch.setattr(zb.requests, "get", _get)
    assert zb.zotero_available() is False


def test_zotero_write_supported_true_with_server_id(monkeypatch):
    def _get(url, *args, **kwargs):
        return _MockResponse(text="", status_code=200, headers={"Zotero-Server-ID": "srv123"})

    monkeypatch.setattr(zb.requests, "get", _get)
    assert zb.zotero_write_supported() is True


def test_zotero_write_supported_false_without_server_id(monkeypatch):
    def _get(url, *args, **kwargs):
        return _MockResponse(text="", status_code=200, headers={})

    monkeypatch.setattr(zb.requests, "get", _get)
    assert zb.zotero_write_supported() is False


def test_save_to_zotero_success(monkeypatch):
    calls = {}

    def _get(url, *args, **kwargs):
        if "export.arxiv.org" in url:
            return _MockResponse(content=SAMPLE_ATOM.encode("utf-8"))
        # bare /api/ GET returns the server ID (Zotero 10+)
        return _MockResponse(text="", status_code=200, headers={"Zotero-Server-ID": "srv123"})

    def _post(url, *args, **kwargs):
        calls["url"] = url
        calls["headers"] = kwargs.get("headers", {})
        calls["data"] = kwargs.get("data")
        if url.endswith("/local/authorize"):
            return _MockResponse(text="", status_code=200, json_data={"key": "localkey123"})
        return _MockResponse(text="[]", status_code=201, json_data=[{"key": "ABCD1234"}])

    monkeypatch.setattr(zb.requests, "get", _get)
    monkeypatch.setattr(zb.requests, "post", _post)

    result = zb.save_to_zotero("1810.04805")
    assert result["ok"] is True
    assert result["item_key"] == "ABCD1234"
    assert "/users/0/items" in calls["url"]
    assert calls["headers"].get("Zotero-API-Version") == "3"
    assert calls["headers"].get("Zotero-Server-ID") == "srv123"
    assert calls["headers"].get("Zotero-API-Key") == "localkey123"
    assert '"itemType": "preprint"' in calls["data"]


def test_save_to_zotero_returns_error_for_bad_id(monkeypatch):
    def _get(url, *args, **kwargs):
        return _MockResponse(content=b"<feed xmlns='http://www.w3.org/2005/Atom'></feed>")

    monkeypatch.setattr(zb.requests, "get", _get)
    result = zb.save_to_zotero("9999.99999")
    assert result["ok"] is False
    assert "No arXiv paper" in result["error"]


def test_save_to_zotero_pre10_readonly(monkeypatch):
    """Zotero < 10 has no Zotero-Server-ID header -> read-only, clear error."""
    def _get(url, *args, **kwargs):
        if "export.arxiv.org" in url:
            return _MockResponse(content=SAMPLE_ATOM.encode("utf-8"))
        return _MockResponse(text="", status_code=200, headers={})

    monkeypatch.setattr(zb.requests, "get", _get)
    result = zb.save_to_zotero("1810.04805")
    assert result["ok"] is False
    assert "Zotero 10+" in result["error"]


def test_save_to_zotero_handles_401(monkeypatch):
    def _get(url, *args, **kwargs):
        if "export.arxiv.org" in url:
            return _MockResponse(content=SAMPLE_ATOM.encode("utf-8"))
        return _MockResponse(text="", status_code=200, headers={"Zotero-Server-ID": "srv123"})

    def _post(url, *args, **kwargs):
        if url.endswith("/local/authorize"):
            return _MockResponse(text="", status_code=200, json_data={"key": "localkey123"})
        return _MockResponse(text="", status_code=401)

    monkeypatch.setattr(zb.requests, "get", _get)
    monkeypatch.setattr(zb.requests, "post", _post)

    result = zb.save_to_zotero("1810.04805")
    assert result["ok"] is False
    assert "did not authorize" in result["error"]
