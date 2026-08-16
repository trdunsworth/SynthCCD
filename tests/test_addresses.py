"""Tests for address providers (static pool and OpenStreetMap query builders)."""
from pathlib import Path
from typing import Any

import httpx
import overpy
import pandas as pd
import pytest

from synth911gen3.addresses import (
    OpenStreetMapAddressProvider,
    _build_named_street_query,
    _build_real_address_query,
    _normalize_state,
    _parse_bbox,
)
from synth911gen3.domain import Address, parse_address_parts
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
            raise httpx.HTTPStatusError(
                "error", request=httpx.Request("GET", "http://fake"), response=self
            )  # type: ignore[arg-type]


class _FakeClient:
    def __init__(self, search_payload=None, reverse_payload=None) -> None:
        self._search_payload = search_payload if search_payload is not None else []
        self._reverse_payload = reverse_payload if reverse_payload is not None else {}
        self.search_calls = 0
        self.reverse_calls = 0

    def get(self, url: str, **kwargs: Any):
        if "reverse" in url:
            self.reverse_calls += 1
            return _FakeResponse(self._reverse_payload)
        self.search_calls += 1
        return _FakeResponse(self._search_payload)

    def post(self, url: str, **kwargs: Any):
        return _FakeResponse({}, 500)


class _SequencedClient:
    """Returns a predefined sequence of responses for search URL GETs."""

    def __init__(self, responses: list[_FakeResponse], reverse_payload=None) -> None:
        self._responses = list(responses)
        self._reverse_payload = reverse_payload if reverse_payload is not None else {}
        self.search_calls = 0
        self.reverse_calls = 0

    def get(self, url: str, **kwargs: Any):
        if "reverse" in url:
            self.reverse_calls += 1
            return _FakeResponse(self._reverse_payload)
        self.search_calls += 1
        if self._responses:
            return self._responses.pop(0)
        return _FakeResponse([], 200)

    def post(self, url: str, **kwargs: Any):
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


def test_parse_address_parts_number_name_type_prefix_postfix() -> None:
    assert parse_address_parts("101 Main St") == ("101", "Main", "St", "", "")
    assert parse_address_parts("204 E 12th St") == ("204", "12th", "St", "E", "")
    assert parse_address_parts("777 S Broadway Blvd") == ("777", "Broadway", "Blvd", "S", "")
    assert parse_address_parts("890 N Oak Trafficway NW") == (
        "890",
        "Oak",
        "Trafficway",
        "N",
        "NW",
    )
    assert parse_address_parts("55 West 39th Street") == ("55", "39th", "Street", "W", "")
    assert parse_address_parts("Broadway") == ("", "Broadway", "", "", "")
    assert parse_address_parts("12th St") == ("", "12th", "St", "", "")
    assert parse_address_parts("101A State Ave") == ("101A", "State", "Ave", "", "")


def test_address_auto_parses_street_components() -> None:
    address = Address("890 N Oak Trafficway NW", "Kansas City", "Missouri")
    assert address.street_number == "890"
    assert address.street_name == "Oak"
    assert address.street_type == "Trafficway"
    assert address.prefix_directional == "N"
    assert address.postfix_directional == "NW"


def test_address_keeps_explicit_components() -> None:
    address = Address(
        "Main",
        "Kansas City",
        "Missouri",
        street_number="101",
        street_name="Main",
        street_type="St",
        prefix_directional="N",
        postal_code="64105",
    )
    assert address.street_number == "101"
    assert address.street_name == "Main"
    assert address.street_type == "St"
    assert address.prefix_directional == "N"
    assert address.postal_code == "64105"


def test_parse_elements_uses_tags_and_dedupes() -> None:
    result = _result_from_xml(
        _way(1, **{"addr:housenumber": "101", "addr:street": "Main St", "addr:state": "MO"})
        + _way(2, **{"addr:housenumber": "101", "addr:street": "Main St", "addr:state": "MO"})
        + _way(3, **{"addr:housenumber": "55", "addr:street": "Oak Ave"})
        + _way(4, **{"addr:street": "No Number Rd"})
    )
    addresses = OpenStreetMapAddressProvider()._parse_elements(
        result, "Fallback City", "Fallback State"
    )
    assert len(addresses) == 2
    assert Address("101 Main St", "Fallback City", "Missouri") in addresses
    assert Address("55 Oak Ave", "Fallback City", "Fallback State") in addresses


def test_parse_elements_uses_street_components_and_postcode() -> None:
    result = _result_from_xml(
        _way(
            1,
            **{
                "addr:housenumber": "204",
                "addr:street": "E 12th St",
                "addr:state": "MO",
                "addr:postcode": "64105",
            },
        )
        + _way(
            2,
            **{
                "addr:housenumber": "55",
                "addr:street": "Oak Ave",
                "addr:postcode": "64111",
            },
        )
    )
    addresses = OpenStreetMapAddressProvider()._parse_elements(
        result, "Fallback City", "Fallback State"
    )

    first = next(a for a in addresses if a.street_address == "204 E 12th St")
    assert first.street_number == "204"
    assert first.street_name == "12th"
    assert first.street_type == "St"
    assert first.prefix_directional == "E"
    assert first.postal_code == "64105"

    second = next(a for a in addresses if a.street_address == "55 Oak Ave")
    assert second.street_number == "55"
    assert second.street_name == "Oak"
    assert second.postal_code == "64111"


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
            _way(i, **{"addr:housenumber": str(i * 10), "addr:street": f"Street {i}"})
            for i in range(1, 11)
        )
        return _result_from_xml(elements)

    provider = OpenStreetMapAddressProvider(
        client=_FakeClient(search_payload=search_payload),  # type: ignore[arg-type]
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
        client=_FakeClient(search_payload=search_payload),  # type: ignore[arg-type]
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
        client=_FakeClient(search_payload=search_payload),  # type: ignore[arg-type]
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
            _way(i, **{"addr:housenumber": str(i * 10), "addr:street": f"Street {i}"})
            for i in range(1, 6)
        )
        return _result_from_xml(elements)

    provider = OpenStreetMapAddressProvider(
        client=_FakeClient(search_payload=search_payload),  # type: ignore[arg-type]
        cache_dir=tmp_path,
        query_runner=runner,
    )
    first = provider.load_addresses("Kansas City, MO")
    second = provider.load_addresses("Kansas City, MO")

    assert first == second
    assert calls["count"] == 1


def _kansas_provider(tmp_path: Path, runner, query_runner_name: str = "query_runner", **kwargs):
    search_payload = [
        {
            "boundingbox": ["38.8", "39.3", "-94.7", "-94.4"],
            "address": {"city": "Kansas City", "state": "Missouri"},
        }
    ]
    kwargs.setdefault("client", _FakeClient(search_payload=search_payload))
    kwargs.setdefault("cache_dir", tmp_path)
    kwargs[query_runner_name] = runner
    return OpenStreetMapAddressProvider(**kwargs)


def _five_ways() -> overpy.Result:
    return _result_from_xml(
        "".join(
            _way(i, **{"addr:housenumber": str(i * 10), "addr:street": f"Street {i}"})
            for i in range(1, 6)
        )
    )


def _write_cache(provider: OpenStreetMapAddressProvider, area: str, rows: int) -> Path:
    path = provider._cache_path(area)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(
        {
            "street_address": [f"{i * 10} Street {i}" for i in range(1, rows + 1)],
            "city": ["Kansas City"] * rows,
            "state": ["Missouri"] * rows,
            "postal_code": [""] * rows,
        }
    )
    frame.to_parquet(path)
    return path


def test_load_cache_returns_none_for_missing_and_corrupt(tmp_path: Path) -> None:
    provider = _kansas_provider(tmp_path, _five_ways)

    missing = provider._cache_path("Does Not Exist, WV")
    assert provider._load_cache(missing) is None

    corrupt = provider._cache_path("Kansas City, MO")
    corrupt.parent.mkdir(parents=True, exist_ok=True)
    corrupt.write_bytes(b"this is definitely not a parquet file")
    assert provider._load_cache(corrupt) is None


def test_load_cache_returns_none_when_below_min_addresses(tmp_path: Path) -> None:
    provider = OpenStreetMapAddressProvider(cache_dir=tmp_path, min_addresses=5)
    path = provider._cache_path("Some Area")
    small = pd.DataFrame(
        {
            "street_address": ["101 Main St"],
            "city": ["Kansas City"],
            "state": ["Missouri"],
            "postal_code": [""],
        }
    )
    small.to_parquet(path)
    assert provider._load_cache(path) is None


def test_load_addresses_recovers_from_corrupt_cache(tmp_path: Path) -> None:
    calls = {"count": 0}

    def runner(query: str) -> overpy.Result:
        calls["count"] += 1
        return _five_ways()

    provider = _kansas_provider(tmp_path, runner)
    cache_path = provider._cache_path("Kansas City, MO")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_bytes(b"corrupt garbage")

    addresses = provider.load_addresses("Kansas City, MO")

    assert calls["count"] == 1
    assert len(addresses) == 5
    frame = pd.read_parquet(cache_path)
    assert len(frame) == 5


def test_load_addresses_refetches_when_cached_frame_below_min(tmp_path: Path) -> None:
    calls = {"count": 0}

    def runner(query: str) -> overpy.Result:
        calls["count"] += 1
        return _five_ways()

    provider = _kansas_provider(tmp_path, runner)
    _write_cache(provider, "Kansas City, MO", rows=1)

    addresses = provider.load_addresses("Kansas City, MO")

    assert calls["count"] == 1
    assert len(addresses) == 5


def test_load_addresses_with_bbox_query(tmp_path: Path) -> None:
    reverse_payload = {"address": {"city": "Midtown", "state": "Kansas"}}

    def runner(query: str) -> overpy.Result:
        elements = "".join(
            _way(i, **{"addr:housenumber": str(200 + i), "addr:street": "Main St"})
            for i in range(1, 6)
        )
        return _result_from_xml(elements)

    provider = OpenStreetMapAddressProvider(
        client=_FakeClient(reverse_payload=reverse_payload),  # type: ignore[arg-type]
        cache_dir=tmp_path,
        query_runner=runner,
    )
    addresses = provider.load_addresses("39.0,-94.7,39.15,-94.5")

    assert Address("201 Main St", "Midtown", "Kansas") in addresses
    assert provider._client.reverse_calls == 1  # type: ignore[attr-defined]


def test_nominatim_retries_on_rate_limit(tmp_path: Path, monkeypatch) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr(
        "synth911gen3.addresses.time.sleep", lambda seconds: sleeps.append(float(seconds))
    )

    search_payload = [
        {
            "boundingbox": ["38.8", "39.3", "-94.7", "-94.4"],
            "address": {"city": "Kansas City", "state": "Missouri"},
        }
    ]
    client = _SequencedClient(
        [
            _FakeResponse([], status_code=429, headers={"Retry-After": "0"}),
            _FakeResponse(search_payload, 200),
        ]
    )

    def runner(query: str) -> overpy.Result:
        elements = "".join(
            _way(i, **{"addr:housenumber": str(i * 10), "addr:street": f"Street {i}"})
            for i in range(1, 6)
        )
        return _result_from_xml(elements)

    provider = OpenStreetMapAddressProvider(
        client=client,  # type: ignore[arg-type]
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

    client = _SequencedClient(
        [_FakeResponse([], status_code=429, headers={"Retry-After": "0"})] * 3
    )

    def runner(query: str) -> overpy.Result:
        return _result_from_xml("")

    provider = OpenStreetMapAddressProvider(
        client=client,  # type: ignore[arg-type]
        cache_dir=tmp_path,
        query_runner=runner,
        max_retries=3,
        nominatim_min_interval=0.0,
    )
    with pytest.raises(AddressLookupError):
        provider.load_addresses("Kansas City, MO")

    assert client.search_calls == 3


def test_nominatim_tls_error_surfaces_workaround_hint(tmp_path: Path) -> None:
    import ssl

    class _TlsClient:
        def get(self, url: str, **kwargs: Any) -> Any:
            raise httpx.ConnectError(
                "connection failed", request=httpx.Request("GET", url)
            ) from ssl.SSLCertVerificationError(1, "unable to get local issuer certificate")

        def post(self, url: str, **kwargs: Any) -> Any:
            return _FakeResponse({}, 500)

    provider = OpenStreetMapAddressProvider(
        client=_TlsClient(),  # type: ignore[arg-type]
        cache_dir=tmp_path,
        nominatim_min_interval=0.0,
    )
    with pytest.raises(AddressLookupError, match="SYNTH911_SYSTEM_TRUST"):
        provider.load_addresses("Kansas City, MO")


def test_overpass_network_error_raises_address_lookup_error(tmp_path: Path) -> None:
    class _NetworkClient:
        def __init__(self) -> None:
            self._network_error = httpx.ConnectError(
                "connection refused", request=httpx.Request("POST", "https://overpass.example")
            )

        def get(self, url: str, **kwargs: Any) -> Any:
            return _FakeResponse(
                [
                    {
                        "boundingbox": ["38.8", "39.3", "-94.7", "-94.4"],
                        "address": {"city": "Kansas City", "state": "Missouri"},
                    }
                ]
            )

        def post(self, url: str, **kwargs: Any) -> Any:
            raise self._network_error

    provider = OpenStreetMapAddressProvider(
        client=_NetworkClient(),  # type: ignore[arg-type]
        cache_dir=tmp_path,
        nominatim_min_interval=0.0,
    )
    with pytest.raises(AddressLookupError, match="Overpass"):
        provider.load_addresses("Kansas City, MO")


def test_nominatim_enforces_min_request_interval(tmp_path: Path, monkeypatch) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr(
        "synth911gen3.addresses.time.sleep", lambda seconds: sleeps.append(float(seconds))
    )

    search_payload = [
        {
            "boundingbox": ["38.8", "39.3", "-94.7", "-94.4"],
            "address": {"city": "Kansas City", "state": "Missouri"},
        }
    ]
    provider = OpenStreetMapAddressProvider(
        client=_FakeClient(search_payload=search_payload),  # type: ignore[arg-type]
        cache_dir=tmp_path,
        nominatim_min_interval=5.0,
    )
    provider._geocode_area("Kansas City, MO")
    provider._geocode_area("Kansas City, MO")

    assert provider._client.search_calls == 2  # type: ignore[attr-defined]
    assert any(sleep == pytest.approx(5.0, abs=1.0) for sleep in sleeps)


def test_build_queries_contain_bbox() -> None:
    real = _build_real_address_query(39.0, -94.7, 39.15, -94.5, 50)
    assert "39.0,-94.7,39.15,-94.5" in real
    assert "addr:housenumber" in real
    named = _build_named_street_query(39.0, -94.7, 39.15, -94.5, 50)
    assert "39.0,-94.7,39.15,-94.5" in named
    assert "highway" in named


def test_geocode_area_extracts_country_code(tmp_path: Path) -> None:
    search_payload = [
        {
            "boundingbox": ["53.3", "53.4", "-6.3", "-6.2"],
            "address": {"city": "Dublin", "state": "Dublin", "country_code": "ie"},
        }
    ]
    provider = OpenStreetMapAddressProvider(
        client=_FakeClient(search_payload=search_payload),  # type: ignore[arg-type]
        cache_dir=tmp_path,
    )
    area = provider._geocode_area("Dublin, Ireland")

    assert area.country_code == "IE"
    assert provider.resolved_country() is None  # only set during load_addresses


def test_geocode_bbox_extracts_country_code(tmp_path: Path) -> None:
    reverse_payload = {"address": {"city": "Toronto", "state": "Ontario", "country_code": "ca"}}
    provider = OpenStreetMapAddressProvider(
        client=_FakeClient(reverse_payload=reverse_payload),  # type: ignore[arg-type]
        cache_dir=tmp_path,
    )
    area = provider._geocode_bbox((43.6, -79.4, 43.7, -79.3))

    assert area.country_code == "CA"


def test_geocode_area_handles_missing_country_code(tmp_path: Path) -> None:
    search_payload = [
        {
            "boundingbox": ["38.8", "39.3", "-94.7", "-94.4"],
            "address": {"city": "Kansas City", "state": "Missouri"},
        }
    ]
    provider = OpenStreetMapAddressProvider(
        client=_FakeClient(search_payload=search_payload),  # type: ignore[arg-type]
        cache_dir=tmp_path,
    )
    area = provider._geocode_area("Kansas City, MO")

    assert area.country_code == ""


def test_static_provider_has_no_resolved_country() -> None:
    from synth911gen3.addresses import StaticAddressProvider
    from synth911gen3.domain import Address

    provider = StaticAddressProvider([Address("101 N Main St", "Kansas City", "Missouri")])
    assert provider.resolved_country() is None


def test_load_addresses_persists_and_reads_country_meta(tmp_path: Path) -> None:
    search_payload = [
        {
            "boundingbox": ["53.3", "53.4", "-6.3", "-6.2"],
            "address": {"city": "Dublin", "state": "Dublin", "country_code": "ie"},
        }
    ]

    def runner(query: str) -> overpy.Result:
        return _five_ways()

    provider = OpenStreetMapAddressProvider(
        client=_FakeClient(search_payload=search_payload),  # type: ignore[arg-type]
        cache_dir=tmp_path,
        query_runner=runner,
    )
    provider.load_addresses("Dublin, Ireland")

    assert provider.resolved_country() == "IE"
    meta = provider._meta_path("Dublin, Ireland")
    assert meta.is_file()
    assert '"IE"' in meta.read_text(encoding="utf-8")

    # A fresh provider instance recovers the country from the meta file.
    provider2 = OpenStreetMapAddressProvider(
        client=_FakeClient(search_payload=search_payload),  # type: ignore[arg-type]
        cache_dir=tmp_path,
        query_runner=runner,
    )
    provider2.load_addresses("Dublin, Ireland")
    assert provider2.resolved_country() == "IE"


def test_load_addresses_recovers_missing_or_corrupt_meta(tmp_path: Path) -> None:
    search_payload = [
        {
            "boundingbox": ["38.8", "39.3", "-94.7", "-94.4"],
            "address": {"city": "Kansas City", "state": "Missouri", "country_code": "us"},
        }
    ]

    def runner(query: str) -> overpy.Result:
        return _five_ways()

    provider = OpenStreetMapAddressProvider(
        client=_FakeClient(search_payload=search_payload),  # type: ignore[arg-type]
        cache_dir=tmp_path,
        query_runner=runner,
    )
    # First run without country (old cache format): meta missing -> None
    provider.load_addresses("Kansas City, MO")
    meta = provider._meta_path("Kansas City, MO")
    meta.write_text("not json {{{", encoding="utf-8")
    provider.load_addresses("Kansas City, MO")
    assert provider.resolved_country() is None
