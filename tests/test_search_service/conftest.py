"""Shared fixtures, mock Elasticsearch, and helpers for Search Service tests."""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from dmr.test import DMRClient

from services.search_service.apps.search.client import (
    reset_elasticsearch_client,
    set_elasticsearch_client,
)
from services.search_service.apps.search.indices import (
    INDEX_COMMENTS,
    INDEX_FORUMS,
    INDEX_POSTS,
    INDEX_PROFILES,
    setup_all_indices,
)
from shared.jwt.tokens import create_access_token, load_private_key


class MockIndicesClient:
    """Mock for es.indices operations."""

    def __init__(self, es: MockElasticsearch) -> None:
        self.es = es

    def exists(self, *, index: str) -> bool:
        return index in self.es.data

    def create(self, *, index: str, mappings: Any = None, settings: Any = None) -> dict[str, Any]:
        if index not in self.es.data:
            self.es.data[index] = {}
        return {"acknowledged": True, "index": index}

    def delete(self, *, index: str) -> dict[str, Any]:
        if index in self.es.data:
            del self.es.data[index]
        return {"acknowledged": True}


class MockElasticsearch:
    """In-memory Elasticsearch mock supporting indexing, updates, and query DSL."""

    def __init__(self) -> None:
        self.data: dict[str, dict[str, dict[str, Any]]] = {
            INDEX_POSTS: {},
            INDEX_FORUMS: {},
            INDEX_PROFILES: {},
            INDEX_COMMENTS: {},
        }
        self.indices = MockIndicesClient(self)

    def index(self, *, index: str, id: str, document: dict[str, Any]) -> dict[str, Any]:
        if index not in self.data:
            self.data[index] = {}
        self.data[index][str(id)] = dict(document)
        return {"_index": index, "_id": str(id), "result": "created"}

    def update(
        self,
        *,
        index: str,
        id: str,
        doc: dict[str, Any] | None = None,
        script: dict[str, Any] | None = None,
        doc_as_upsert: bool = False,
    ) -> dict[str, Any]:
        if index not in self.data:
            self.data[index] = {}
        target_id = str(id)

        if target_id not in self.data[index]:
            if doc_as_upsert and doc is not None:
                self.data[index][target_id] = dict(doc)
                self.data[index][target_id]["id"] = target_id
                return {"_index": index, "_id": target_id, "result": "created"}
            return {"_index": index, "_id": target_id, "result": "noop"}

        target_doc = self.data[index][target_id]
        if doc:
            target_doc.update(doc)

        if script:
            params = script.get("params", {})
            target_doc["upvotes_count"] = max(
                0, target_doc.get("upvotes_count", 0) + params.get("up", 0)
            )
            target_doc["downvotes_count"] = max(
                0, target_doc.get("downvotes_count", 0) + params.get("down", 0)
            )
            target_doc["popularity_score"] = target_doc.get("popularity_score", 0) + params.get(
                "net", 0
            )

        return {"_index": index, "_id": target_id, "result": "updated"}

    def delete(self, *, index: str, id: str, **kwargs: Any) -> dict[str, Any]:
        if index in self.data and str(id) in self.data[index]:
            del self.data[index][str(id)]
            return {"_index": index, "_id": str(id), "result": "deleted"}
        return {"_index": index, "_id": str(id), "result": "not_found"}

    def close(self) -> None:
        pass

    def search(
        self,
        *,
        index: str,
        query: dict[str, Any] | None = None,
        sort: list[dict[str, Any]] | None = None,
        highlight: dict[str, Any] | None = None,
        size: int = 10,
        **kwargs: Any,
    ) -> dict[str, Any]:
        from_offset = kwargs.get("from", 0)
        docs = list(self.data.get(index, {}).values())

        matched_docs: list[dict[str, Any]] = []
        for doc in docs:
            if self._matches_query(doc, query):
                matched_docs.append(dict(doc))

        # Sorting
        if sort:
            for s in reversed(sort):
                for field, order_spec in s.items():
                    order = (
                        order_spec.get("order", "asc") if isinstance(order_spec, dict) else "asc"
                    )
                    rev = order == "desc"
                    if field == "_score":
                        # Simulate relevance score based on keyword presence
                        pass
                    else:
                        matched_docs.sort(
                            key=lambda d: (d.get(field) is not None, d.get(field, 0)),
                            reverse=rev,
                        )

        total_count = len(matched_docs)
        sliced = matched_docs[from_offset : from_offset + size]

        hits: list[dict[str, Any]] = []
        for d in sliced:
            hit_item: dict[str, Any] = {
                "_index": index,
                "_id": str(d.get("id", "")),
                "_score": 1.0,
                "_source": d,
            }
            if highlight:
                hit_item["highlight"] = self._generate_highlights(d, query, highlight)
            hits.append(hit_item)

        return {
            "took": 2,
            "timed_out": False,
            "hits": {
                "total": {"value": total_count, "relation": "eq"},
                "hits": hits,
            },
        }

    def _matches_query(self, doc: dict[str, Any], query: dict[str, Any] | None) -> bool:
        if not query or query == {"match_all": {}}:
            return True

        if "match_all" in query:
            return True

        if "bool" in query:
            bool_q = query["bool"]
            for must_clause in bool_q.get("must", []):
                if not self._matches_query(doc, must_clause):
                    return False
            for filter_clause in bool_q.get("filter", []):
                if not self._matches_query(doc, filter_clause):
                    return False
            should_clauses = bool_q.get("should", [])
            if should_clauses:
                matched_should = any(self._matches_query(doc, c) for c in should_clauses)
                if not matched_should:
                    return False
            for must_not_clause in bool_q.get("must_not", []):
                if self._matches_query(doc, must_not_clause):
                    return False
            return True

        if "term" in query:
            for field, val in query["term"].items():
                if doc.get(field) != val:
                    return False
            return True

        if "terms" in query:
            for field, allowed_vals in query["terms"].items():
                doc_val = doc.get(field, [])
                if isinstance(doc_val, list):
                    if not any(v in allowed_vals for v in doc_val):
                        return False
                else:
                    if doc_val not in allowed_vals:
                        return False
            return True

        if "range" in query:
            for field, bounds in query["range"].items():
                val = doc.get(field)
                if not val:
                    return False
                if "gte" in bounds and val < bounds["gte"]:
                    return False
                if "lte" in bounds and val > bounds["lte"]:
                    return False
            return True

        if "match" in query:
            for field, match_spec in query["match"].items():
                search_term = (
                    match_spec.get("query", match_spec)
                    if isinstance(match_spec, dict)
                    else match_spec
                )
                doc_text = str(doc.get(field, "")).lower()
                terms = str(search_term).lower().split()
                if not any(t in doc_text for t in terms):
                    return False
            return True

        if "multi_match" in query:
            mm = query["multi_match"]
            search_term = str(mm.get("query", "")).lower()
            fields = mm.get("fields", [])
            query_type = mm.get("type", "best_fields")

            doc_texts: list[str] = []
            for f in fields:
                field_name = f.split("^")[0].split(".")[0]
                val = doc.get(field_name)
                if isinstance(val, list):
                    doc_texts.extend([str(x).lower() for x in val])
                elif val:
                    doc_texts.append(str(val).lower())

            combined = " ".join(doc_texts)

            if query_type == "bool_prefix":
                # Prefix match
                prefixes = search_term.split()
                return any(any(w.startswith(p) for w in combined.split()) for p in prefixes)
            else:
                terms = search_term.split()
                return any(t in combined for t in terms)

        return True

    def _generate_highlights(
        self,
        doc: dict[str, Any],
        query: dict[str, Any] | None,
        highlight_spec: dict[str, Any],
    ) -> dict[str, list[str]]:
        hl: dict[str, list[str]] = {}
        q_str = ""
        # Find keyword from query
        if query and "bool" in query:
            for c in query["bool"].get("must", []):
                if "multi_match" in c:
                    q_str = c["multi_match"].get("query", "")
                elif "match" in c:
                    for _, spec in c["match"].items():
                        q_str = spec.get("query", spec) if isinstance(spec, dict) else spec
        elif query and "multi_match" in query:
            q_str = query["multi_match"].get("query", "")
        elif query and "match" in query:
            for _, spec in query["match"].items():
                q_str = spec.get("query", spec) if isinstance(spec, dict) else spec

        if not q_str:
            return hl

        tokens = q_str.strip().split()
        for field in highlight_spec.get("fields", {}):
            val = doc.get(field)
            if val and isinstance(val, str):
                text = val
                for token in tokens:
                    pattern = re.compile(re.escape(token), re.IGNORECASE)
                    text = pattern.sub(f"<b>{token}</b>", text)
                hl[field] = [text]
        return hl


@pytest.fixture(autouse=True)
def mock_es() -> MockElasticsearch:
    """Fixture initializing an in-memory Elasticsearch mock for each test."""
    es = MockElasticsearch()
    setup_all_indices(es)
    set_elasticsearch_client(es)
    yield es
    reset_elasticsearch_client()


@pytest.fixture
def dmr_client() -> DMRClient:
    """Fixture providing DMR test client."""
    return DMRClient()


@pytest.fixture
def make_user_token():
    """Factory fixture generating valid RS256 JWT tokens."""
    private_key_path = Path(__file__).resolve().parent.parent.parent / "keys" / "private_key.pem"
    private_key_pem = load_private_key(private_key_path)

    def _generate(
        user_id: UUID | None = None,
        profile_id: UUID | None = None,
        username: str = "search_tester",
    ) -> tuple[str, UUID, UUID]:
        u_id = user_id or uuid.uuid4()
        p_id = profile_id or uuid.uuid4()
        token = create_access_token(
            user_id=u_id,
            profile_id=p_id,
            username=username,
            roles=["user"],
            private_key_pem=private_key_pem,
        )
        return token, u_id, p_id

    return _generate
