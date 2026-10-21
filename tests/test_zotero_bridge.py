from __future__ import annotations

import pytest

import zotero_bridge as zb


@pytest.fixture(autouse=True)
def _reset_zotero_cache():
    zb._CACHE["server_id"] = None
    zb._CACHE["api_key"] = None
    yield
    zb._CACHE["server_id"] = None
    zb._CACHE["api_key"] = None


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
            raise zb.requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self._json


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("https://arxiv.org/abs/2607.21663", "2607.21663"),
        ("2607.21663", "2607.21663"),
        ("arXiv:2607.21663", "2607.21663"),
        ("2607.21663v3", "2607.21663"),
        ("arXiv:2607.21663v1", "2607.21663"),
        ("cond-mat/0603274v2", "cond-mat/0603274"),
        ("https://arxiv.org/pdf/1810.04805v2", "1810.04805"),
        ("https://arxiv.org/abs/cond-mat/0603274", "cond-mat/0603274"),
        ("", ""),
        ("not an arxiv thing", "not an arxiv thing"),
        ("not an arxiv thingv2", "not an arxiv thingv2"),
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
    def _post(url, *args, **kwargs):
        assert url.endswith("/connector/ping")
        return _MockResponse(text="{}", status_code=200)

    monkeypatch.setattr(zb.requests, "post", _post)
    assert zb.zotero_available() is True


def test_zotero_available_false_when_unreachable(monkeypatch):
    def _post(url, *args, **kwargs):
        raise zb.requests.ConnectionError("refused")

    monkeypatch.setattr(zb.requests, "post", _post)
    assert zb.zotero_available() is False


def test_list_collections_parses_keys_and_names(monkeypatch):
    def _get(url, *args, **kwargs):
        return _MockResponse(
            text="",
            status_code=200,
            json_data=[
                {"key": "AAAA1111", "data": {"name": "To Read"}},
                {"key": "BBBB2222", "data": {"name": "Anyon Papers"}},
            ],
        )

    monkeypatch.setattr(zb.requests, "get", _get)
    cols = zb.list_collections()
    assert cols == [
        {"key": "AAAA1111", "name": "To Read"},
        {"key": "BBBB2222", "name": "Anyon Papers"},
    ]


def test_list_collections_empty_on_error(monkeypatch):
    def _get(url, *args, **kwargs):
        raise zb.requests.ConnectionError("refused")

    monkeypatch.setattr(zb.requests, "get", _get)
    assert zb.list_collections() == []


def test_save_to_zotero_skips_when_already_exists(monkeypatch):
    """If the arXiv id already exists in Zotero, no write happens."""
    post_calls = {"n": 0}

    def _get(url, *args, **kwargs):
        if "export.arxiv.org" in url:
            return _MockResponse(content=SAMPLE_ATOM.encode("utf-8"))
        if url.endswith("/users/0/items"):
            return _MockResponse(
                json_data=[
                    {"key": "ABCD1234", "data": {"archiveID": "arXiv:1810.04805"}}
                ]
            )
        if url.endswith("/items/ABCD1234/children"):
            return _MockResponse(
                json_data=[
                    {
                        "key": "PDFKEY1",
                        "data": {
                            "contentType": "application/pdf",
                            "filename": "preprint.pdf",
                        },
                        "links": {"enclosure": {"length": 1024}},
                    }
                ]
            )
        raise AssertionError(f"Unexpected GET: {url}")

    def _post(url, *args, **kwargs):
        post_calls["n"] += 1
        return _MockResponse(text="[]", status_code=201, json_data=[{"key": "ABCD1234"}])

    monkeypatch.setattr(zb.requests, "get", _get)
    monkeypatch.setattr(zb.requests, "post", _post)

    result = zb.save_to_zotero("1810.04805")
    assert result["ok"] is False
    assert result.get("already_exists") is True
    assert post_calls["n"] == 0  # no write attempted


def test_save_to_zotero_returns_error_for_bad_id(monkeypatch):
    def _get(url, *args, **kwargs):
        return _MockResponse(
            content=b"<feed xmlns='http://www.w3.org/2005/Atom'></feed>"
        )

    monkeypatch.setattr(zb.requests, "get", _get)
    result = zb.save_to_zotero("9999.99999")
    assert result["ok"] is False
    assert "No arXiv paper" in result["error"]


def test_save_to_zotero_repairs_existing_item_without_pdf(monkeypatch):
    """A legacy item saved without attachment URLs gets its PDF on retry."""
    pdf_bytes = b"%PDF-1.7\nlegacy item repair"
    posts = []
    authorizations = {"n": 0}
    file_posts = {"n": 0}

    def _get(url, *args, **kwargs):
        if "export.arxiv.org" in url:
            return _MockResponse(content=SAMPLE_ATOM.encode("utf-8"))
        if url.endswith("/users/0/items"):
            return _MockResponse(
                json_data=[
                    {"key": "OLDITEM1", "data": {"archiveID": "arXiv:1810.04805"}}
                ]
            )
        if url.endswith("/items/OLDITEM1/children"):
            return _MockResponse(json_data=[])
        if url.endswith("/pdf/1810.04805v2"):
            return _MockResponse(content=pdf_bytes)
        if url.endswith("/api/"):
            return _MockResponse(headers={"Zotero-Server-ID": "srv123"})
        raise AssertionError(f"Unexpected GET: {url}")

    def _post(url, *args, **kwargs):
        posts.append((url, kwargs))
        if url.endswith("/local/authorize"):
            authorizations["n"] += 1
            return _MockResponse(
                json_data={"key": f"one-time-{authorizations['n']}", "remember": False}
            )
        if url.endswith("/users/0/items"):
            return _MockResponse(
                status_code=200,
                json_data={"successful": {"0": {"key": "ATTACH1"}}},
            )
        if url.endswith("/items/ATTACH1/file"):
            file_posts["n"] += 1
            if file_posts["n"] == 1:
                return _MockResponse(
                    json_data={
                        "url": "http://localhost:23119/api/local/uploads/up1",
                        "uploadKey": "up1",
                    }
                )
            return _MockResponse(status_code=204)
        if url.endswith("/api/local/uploads/up1"):
            assert kwargs["data"] == pdf_bytes
            return _MockResponse(status_code=201)
        raise AssertionError(f"Unexpected POST: {url}")

    monkeypatch.setattr(zb.requests, "get", _get)
    monkeypatch.setattr(zb.requests, "post", _post)

    result = zb.save_to_zotero("1810.04805")

    assert result == {"ok": True, "item_key": "OLDITEM1"}
    assert authorizations["n"] == 3  # one-time keys must not be reused
    create_call = next(
        kwargs for url, kwargs in posts if url.endswith("/users/0/items")
    )
    attachment = create_call["json"][0]
    assert attachment["parentItem"] == "OLDITEM1"
    assert attachment["linkMode"] == "imported_file"


def test_save_to_zotero_reuses_partial_pdf_attachment(monkeypatch):
    """A failed prior repair resumes its PDF attachment instead of duplicating it."""
    pdf_bytes = b"%PDF-1.7\nretry partial upload"
    posts = []
    authorizations = {"n": 0}
    file_posts = {"n": 0}

    def _get(url, *args, **kwargs):
        if "export.arxiv.org" in url:
            return _MockResponse(content=SAMPLE_ATOM.encode("utf-8"))
        if url.endswith("/users/0/items"):
            return _MockResponse(
                json_data=[
                    {"key": "OLDITEM1", "data": {"archiveID": "arXiv:1810.04805"}}
                ]
            )
        if url.endswith("/items/OLDITEM1/children"):
            return _MockResponse(
                json_data=[
                    {
                        "key": "ATTACH1",
                        "data": {
                            "contentType": "application/pdf",
                            "filename": "preprint.pdf",
                            "linkMode": "imported_file",
                        },
                        "links": {"enclosure": {"length": 0}},
                    }
                ]
            )
        if url.endswith("/pdf/1810.04805v2"):
            return _MockResponse(content=pdf_bytes)
        if url.endswith("/api/"):
            return _MockResponse(headers={"Zotero-Server-ID": "srv123"})
        raise AssertionError(f"Unexpected GET: {url}")

    def _post(url, *args, **kwargs):
        posts.append((url, kwargs))
        if url.endswith("/local/authorize"):
            authorizations["n"] += 1
            return _MockResponse(
                json_data={"key": f"one-time-{authorizations['n']}", "remember": False}
            )
        if url.endswith("/items/ATTACH1/file"):
            file_posts["n"] += 1
            if file_posts["n"] == 1:
                return _MockResponse(
                    json_data={
                        "url": "http://localhost:23119/api/local/uploads/up1",
                        "uploadKey": "up1",
                    }
                )
            return _MockResponse(status_code=204)
        if url.endswith("/api/local/uploads/up1"):
            assert kwargs["data"] == pdf_bytes
            return _MockResponse(status_code=201)
        raise AssertionError(f"Unexpected POST: {url}")

    monkeypatch.setattr(zb.requests, "get", _get)
    monkeypatch.setattr(zb.requests, "post", _post)

    result = zb.save_to_zotero("1810.04805")

    assert result == {"ok": True, "item_key": "OLDITEM1"}
    assert authorizations["n"] == 2
    assert not any(url.endswith("/users/0/items") for url, _ in posts)


@pytest.mark.parametrize("failed_endpoint", [None, "saveSingleFile", "saveAttachment"])
def test_save_to_zotero_imports_pdf_through_connector(monkeypatch, failed_endpoint):
    """Saving a paper imports its PDF and snapshot like the Zotero Connector."""
    pdf_bytes = b"%PDF-1.7\nmock PDF bytes"
    page_html = b"<html><title>BERT</title></html>"
    posts = []
    item_reads = {"n": 0}

    def _get(url, *args, **kwargs):
        if "export.arxiv.org" in url:
            return _MockResponse(content=SAMPLE_ATOM.encode("utf-8"))
        if url.endswith("/users/0/collections"):
            return _MockResponse(
                json_data=[
                    {
                        "key": "AAAA1111",
                        "data": {"name": "To Read", "parentCollection": False},
                    }
                ]
            )
        if url.endswith("/users/0/items"):
            item_reads["n"] += 1
            items = [] if item_reads["n"] == 1 else [
                {"key": "NEWITEM1", "data": {"archiveID": "arXiv:1810.04805"}}
            ]
            return _MockResponse(json_data=items)
        if url.endswith("/pdf/1810.04805v2"):
            return _MockResponse(content=pdf_bytes)
        if url.endswith("/abs/1810.04805"):
            return _MockResponse(content=page_html)
        raise AssertionError(f"Unexpected GET: {url}")

    def _post(url, *args, **kwargs):
        posts.append((url, kwargs))
        if url.endswith("/connector/getSelectedCollection"):
            return _MockResponse(
                json_data={
                    "libraryID": 1,
                    "targets": [
                        {"id": "L1", "name": "My Library", "level": 0},
                        {"id": "C23", "name": "To Read", "level": 1},
                    ],
                }
            )
        if failed_endpoint and url.endswith(f"/connector/{failed_endpoint}"):
            return _MockResponse(
                status_code=200, text="Library files are not editable."
            )
        return _MockResponse(status_code=201)

    monkeypatch.setattr(zb.requests, "get", _get)
    monkeypatch.setattr(zb.requests, "post", _post)

    result = zb.save_to_zotero("1810.04805", collection_key="AAAA1111")

    if failed_endpoint:
        expected_error = (
            "Zotero did not save the page snapshot."
            if failed_endpoint == "saveSingleFile"
            else "Zotero did not save the PDF attachment."
        )
        assert result == {"ok": False, "error": expected_error}
        return

    assert result == {"ok": True, "item_key": "NEWITEM1"}
    connector_base = zb.ZOTERO_LOCAL_BASE.removesuffix("/api") + "/connector"
    save_url = f"{connector_base}/saveItems"
    save_payload = next(kwargs["json"] for url, kwargs in posts if url == save_url)
    assert save_payload["items"][0]["itemType"] == "preprint"
    connector_item_id = save_payload["items"][0]["id"]

    update_url = f"{connector_base}/updateSession"
    update_payload = next(kwargs["json"] for url, kwargs in posts if url == update_url)
    assert update_payload["target"] == "C23"
    assert update_payload["sessionID"] == save_payload["sessionID"]

    snapshot_url = f"{connector_base}/saveSingleFile"
    snapshot_payload = next(
        kwargs["json"] for url, kwargs in posts if url == snapshot_url
    )
    assert snapshot_payload["title"] == "Snapshot"
    assert snapshot_payload["url"] == "http://arxiv.org/abs/1810.04805"
    assert snapshot_payload["snapshotContent"] == page_html.decode()
    assert snapshot_payload["items"] == [{"id": connector_item_id}]

    attachment_url = f"{connector_base}/saveAttachment"
    attachment_kwargs = next(kwargs for url, kwargs in posts if url == attachment_url)
    assert attachment_kwargs["data"] == pdf_bytes
    metadata = zb.json.loads(attachment_kwargs["headers"]["X-Metadata"])
    assert metadata == {
        "sessionID": save_payload["sessionID"],
        "parentItemID": connector_item_id,
        "title": "Preprint PDF",
        "url": "http://arxiv.org/pdf/1810.04805v2",
    }
