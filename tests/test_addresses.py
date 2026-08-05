from pathlib import Path

import httpx
import overpy
import pytest

from synth911gen3.addresses import (
    OpenStreetMapAddressProvider,
    _build_named_street_query,
    _build_real_address_query,
    _normalize_state,
    _parse_bbox,
)
from synth911gen3.domain import Address
from synth911gen3.exceptions import AddressLookupError


class _FakeResponse:
    def __init__(self, payload, status_code: int = 200, headers: dict | None = None) -> None:
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {}

    def json(self):
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=httpx.Request("GET", "http://fake"), response=self)


class _FakeClient:
    def __init__(self, search_payload=None, reverse_payload=None) -> None:
        self._search_payload = search_payload if search_payload is not None else []
        self._reverse_payload = reverse_payload if reverse_payload is not None else {}
        self.search_calls = 0
        self.reverse_calls = 0

    def get(self, url: str, **kwargs):
        if "reverse" in url:
            self.reverse_calls += 1
            return _FakeResponse(self._reverse_payload)
        self.search_calls += 1
        return _FakeResponse(self._search_payload)

    def post(self, url: str, **kwargs):
        return _FakeResponse({}, 500)


class _SequencedClient:
    """Returns a predefined sequence of responses for search URL GETs."""

    def __init__(self, responses: list[_FakeResponse], reverse_payload=None) -> None:
        self._responses = list(responses)
        self._reverse_payload = reverse_payload if reverse_payload is not None else {}
        self.search_calls = 0
        self.reverse_calls = 0

    def get(self, url: str, **kwargs):
        if "reverse" in url:
            self.reverse_calls += 1
            return _FakeResponse(self._reverse_payload)
        self.search_calls += 1
        if self._responses:
            return self._responses.pop(0)
        return _FakeResponse([], 200)

    def post(self, url: str, **kwargs):
        return _FakeResponse({}, 500)


def _result_from_xml(elements: str) -> overpy.Result:
    xml = b'<osm version="0.6">' + elements.encode("utf-8") + b"</osm>"
    return overpy.Overpass().parse_xml(xml)


def _way(i: int, **tags) -> str:
    tag_xml = "".join(f'<tag k="{k}" v="{v}"/>' for k, v in tags.items())
    return f'<way id="{i}">{tag_xml}</way>'


def _node(i: int, **tags) -> str:
    tag_xml = "".join(f'<tag k="{k}" v="{v}"/>' for k, v in tags.items())
    return f'<node id="{i}">{tag_xml}</node>'


def test_parse_bbox_valid() -> None:
    assert _parse_bbox("39.0,-94.7,39.15,-94.5") == (39.0, -94.7, 39.15, -94.5)


def test_parse_bbox_invalid() -> None:
    assert _parse_bbox("Kansas City, MO") is None
    assert _parse_bbox("a,b,c,d") is None
    assert _parse_bbox("39.0,-94.7,39.15") is None
    assert _parse_bbox("100,-94.7,101,-94.5") is None


def test_normalize_state() -> None:
    assert _normalize_state("MO") == "Missouri"
    assert _normalize_state("mo") == "Missouri"
    assert _normalize_state("Missouri") == "Missouri"


def test_parse_elements_uses_tags_and_dedupes() -> None:
    result = _result_from_xml(
        _way(1, **{"addr:housenumber": "101", "addr:street": "Main St", "addr:state": "MO"})
        + _way(2, **{"addr:housenumber": "101", "addr:street": "Main St", "addr:state": "MO"})
        + _way(3, **{"addr:housenumber": "55", "addr:street": "Oak Ave"})
        + _way(4, **{"addr:street": "No Number Rd"})
    )
    addresses = OpenStreetMapAddressProvider()._parse_elements(result, "Fallback City", "Fallback State")
    assert len(addresses) == 2
    assert Address("101 Main St", "Fallback City", "Missouri") in addresses
    assert Address("55 Oak Ave", "Fallback City", "Fallback State") in addresses


def test_load_addresses_uses_real_addresses(tmp_path: Path) -> None:
    search_payload = [
        {
            "boundingbox": ["38.8", "39.3", "-94.7", "-94.4"],
            "address": {"city": "Kansas City", "state": "Missouri"},
        }
    ]

    def runner(query: str) -> overpy.Result:
        assert "addr:housenumber" in query
        elements = "".join(
            _way(i, **{"addr:housenumber": str(i * 10), "addr:street": f"Street {i}"}) for i in range(1, 11)
        )
        return _result_from_xml(elements)

    provider = OpenStreetMapAddressProvider(
        client=_FakeClient(search_payload=search_payload),
        cache_dir=tmp_path,
        query_runner=runner,
    )
    addresses = provider.load_addresses("Kansas City, MO")

    assert len(addresses) == 10
    assert Address("10 Street 1", "Kansas City", "Missouri") in addresses
    assert not list(tmp_path.iterdir()) == []  # cache written


def test_load_addresses_falls_back_to_named_streets(tmp_path: Path) -> None:
    search_payload = [
        {
            "boundingbox": ["43.0", "44.0", "-104.0", "-103.0"],
            "address": {"county": "Some County", "state": "South Dakota"},
        }
    ]

    def runner(query: str) -> overpy.Result:
        if "addr:housenumber" in query:
            return _result_from_xml("")
        return _result_from_xml(_way(1, name="Capitol Road") + _way(2, name="Main Street"))

    provider = OpenStreetMapAddressProvider(
        client=_FakeClient(search_payload=search_payload),
        cache_dir=tmp_path,
        query_runner=runner,
    )
    addresses = provider.load_addresses("Some County, SD")

    assert len(addresses) >= 5
    street_addresses = {address.street_address for address in addresses}
    assert any("Capitol Road" in address for address in street_addresses)


def test_load_addresses_raises_when_too_few(tmp_path: Path) -> None:
    search_payload = [
        {
            "boundingbox": ["0.0", "1.0", "0.0", "1.0"],
            "address": {"city": "Nowhere", "state": "Nevada"},
        }
    ]

    def runner(query: str) -> overpy.Result:
        return _result_from_xml("")

    provider = OpenStreetMapAddressProvider(
        client=_FakeClient(search_payload=search_payload),
        cache_dir=tmp_path,
        query_runner=runner,
    )
    with pytest.raises(AddressLookupError):
        provider.load_addresses("Nowhere, NV")


def test_load_addresses_caches_results(tmp_path: Path) -> None:
    search_payload = [
        {
            "boundingbox": ["38.8", "39.3", "-94.7", "-94.4"],
            "address": {"city": "Kansas City", "state": "Missouri"},
        }
    ]
    calls = {"count": 0}

    def runner(query: str) -> overpy.Result:
        calls["count"] += 1
        elements = "".join(
            _way(i, **{"addr:housenumber": str(i * 10), "addr:street": f"Street {i}"}) for i in range(1, 6)
        )
        return _result_from_xml(elements)

    provider = OpenStreetMapAddressProvider(
        client=_FakeClient(search_payload=search_payload),
        cache_dir=tmp_path,
        query_runner=runner,
    )
    first = provider.load_addresses("Kansas City, MO")
    second = provider.load_addresses("Kansas City, MO")

    assert first == second
    assert calls["count"] == 1


def test_load_addresses_with_bbox_query(tmp_path: Path) -> None:
    reverse_payload = {"address": {"city": "Midtown", "state": "Kansas"}}

    def runner(query: str) -> overpy.Result:
        elements = "".join(
            _way(i, **{"addr:housenumber": str(200 + i), "addr:street": "Main St"}) for i in range(1, 6)
        )
        return _result_from_xml(elements)

    provider = OpenStreetMapAddressProvider(
        client=_FakeClient(reverse_payload=reverse_payload),
        cache_dir=tmp_path,
        query_runner=runner,
    )
    addresses = provider.load_addresses("39.0,-94.7,39.15,-94.5")

    assert Address("201 Main St", "Midtown", "Kansas") in addresses
    assert provider._client.reverse_calls == 1


def test_nominatim_retries_on_rate_limit(tmp_path: Path, monkeypatch) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr("synth911gen3.addresses.time.sleep", lambda seconds: sleeps.append(float(seconds)))

    search_payload = [
        {
            "boundingbox": ["38.8", "39.3", "-94.7", "-94.4"],
            "address": {"city": "Kansas City", "state": "Missouri"},
        }
    ]
    client = _SequencedClient(
        [_FakeResponse([], status_code=429, headers={"Retry-After": "0"}), _FakeResponse(search_payload, 200)]
    )

    def runner(query: str) -> overpy.Result:
        elements = "".join(
            _way(i, **{"addr:housenumber": str(i * 10), "addr:street": f"Street {i}"}) for i in range(1, 6)
        )
        return _result_from_xml(elements)

    provider = OpenStreetMapAddressProvider(
        client=client,
        cache_dir=tmp_path,
        query_runner=runner,
        nominatim_min_interval=0.0,
    )
    addresses = provider.load_addresses("Kansas City, MO")

    assert client.search_calls == 2
    assert len(addresses) >= 1
    assert sleeps == [0.0]


def test_nominatim_fails_after_exhausting_retries(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("synth911gen3.addresses.time.sleep", lambda seconds: None)

    client = _SequencedClient([_FakeResponse([], status_code=429, headers={"Retry-After": "0"})] * 3)

    def runner(query: str) -> overpy.Result:
        return _result_from_xml("")

    provider = OpenStreetMapAddressProvider(
        client=client,
        cache_dir=tmp_path,
        query_runner=runner,
        max_retries=3,
        nominatim_min_interval=0.0,
    )
    with pytest.raises(AddressLookupError):
        provider.load_addresses("Kansas City, MO")

    assert client.search_calls == 3


def test_nominatim_enforces_min_request_interval(tmp_path: Path, monkeypatch) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr("synth911gen3.addresses.time.sleep", lambda seconds: sleeps.append(float(seconds)))

    search_payload = [
        {
            "boundingbox": ["38.8", "39.3", "-94.7", "-94.4"],
            "address": {"city": "Kansas City", "state": "Missouri"},
        }
    ]
    provider = OpenStreetMapAddressProvider(
        client=_FakeClient(search_payload=search_payload),
        cache_dir=tmp_path,
        nominatim_min_interval=5.0,
    )
    provider._geocode_area("Kansas City, MO")
    provider._geocode_area("Kansas City, MO")

    assert provider._client.search_calls == 2
    assert any(sleep >= 5.0 for sleep in sleeps)


def test_build_queries_contain_bbox() -> None:
    real = _build_real_address_query(39.0, -94.7, 39.15, -94.5, 50)
    assert "39.0,-94.7,39.15,-94.5" in real
    assert "addr:housenumber" in real
    named = _build_named_street_query(39.0, -94.7, 39.15, -94.5, 50)
    assert "39.0,-94.7,39.15,-94.5" in named
    assert "highway" in named
