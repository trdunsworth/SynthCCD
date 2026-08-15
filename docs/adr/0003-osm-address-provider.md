# ADR-0003: OpenStreetMap as the address source, cached as Parquet

- Status: Accepted
- Date: 2026-08-05
- Deciders: Maintainers

## Context

AGENTS.md requires "real addresses using data from Open Street Map" and a
default area of Kansas City, MO. Earlier versions shipped a fixed pool of
hand-picked addresses; that satisfies nobody — every run produces the same few
hundred streets, and there is no geography to map onto (geospatial exports were
a later requirement).

Two OSM services matter: Nominatim (search/reverse geocoding) and the Overpass
API (bulk querying). Both have usage policies: Nominatim caps at ~1 req/s and
expects an identifying User-Agent; Overpass rejects abusive volumes. Corporate
networks with TLS-inspecting proxies break Python's bundled CA store, which is
a real failure mode on the target machine.

## Decision

Build an `OpenStreetMapAddressProvider` with the following shape:

- **Geocoding**: area queries ("Kansas City, MO") resolve via Nominatim search;
  bare bounding boxes skip straight to Overpass. Results carry the region's
  city, state, and ISO country code (used later by ADR-0009).
- **Bulk fetch**: one Overpass query per area
  (`way/node["addr:housenumber"]["addr:street"]` within the bbox, up to 1,000
  results); coordinates come from node lat/lon or way center points so exports
  can carry real geometry.
- **Caching**: fetched addresses are persisted as Parquet in
  `~/.cache/synth911gen3/addresses_{md5(area_query)[:12]}.parquet`, with a
  `.meta.json` sidecar recording the resolved country code. Cache hits are
  instant and offline; a corrupt or below-minimum cache is treated as a miss
  and refetched.
- **Fallbacks**: if real addresses are too few, named street ways
  (`highway` in residential..primary) are used to synthesize house numbers
  deterministically (md5-derived), keeping the address pool plausible.
- **Politeness**: a shared `_nominatim_get()` enforces a 1 s minimum interval,
  retries 429/5xx with `Retry-After`-aware exponential backoff, and always
  sends a descriptive User-Agent. Overpass calls retry with backoff too.
- **TLS**: when `SYNTH911_SYSTEM_TRUST=1`, the dev-only `truststore` package
  verifies against the OS trust store; TLS failures raise errors that tell the
  user exactly what to set (see `tls.py`, `_describe_http_error`).

A `StaticAddressProvider` (in-memory list) exists for previews, schema probes,
and tests, so the pipeline runs without network.

## Consequences

### Positive

- Real, geographically consistent addresses with coordinates, postal codes,
  and country metadata — the basis for geospatial exports and locale-aware
  names.
- The Parquet cache makes repeat runs and CI tests fast and network-free.
- Static provider keeps `--schema`/`--dry-run`/API probes offline and
  deterministic.

### Negative / Costs

- Address quality depends on OSM tagging in the requested area; sparse areas
  fall back to synthesized numbers on real street names.
- Caches are keyed by a truncated md5 of the area query; distinct queries that
  collide on 12 hex chars share a cache file (accepted risk, astronomically
  unlikely, mitigated by treating too-small frames as misses).
- Network access is a hard requirement for real generation; the 1 s Nominatim
  throttle bounds how many distinct areas one run can resolve.

## Alternatives considered

- **Faker addresses.** Not real geography; fails AGENTS.md and breaks
  geospatial exports.
- **A bundled static address dataset per city.** Finite and stale; cannot
  cover arbitrary user area queries.
- **Nominatim search per address (reverse-geocode on demand).** Hundreds of
  requests per incident row — hopeless against the 1 req/s policy. Bulk Overpass
  fetch plus cache is the only viable shape.
