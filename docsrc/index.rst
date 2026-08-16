synth911gen3
=============

Synthetic 911 CAD and phone data generator.

Emulates dispatch archival records (incident lifecycle, personnel, addresses)
and hourly call-center phone metrics. Seeded and configurable through a
realism YAML; accessible via the CLI, the TUI, an HTTP API, or directly as a
Python package.

.. toctree::
   :maxdepth: 2
   :caption: API Reference

   api/config
   api/addresses
   api/generation
   api/export
   api/interfaces

.. toctree::
   :maxdepth: 1
   :caption: Guides

   Guides <https://github.com/trdunsworth/synth911gen3/blob/main/USERSGUIDE.md>
   Realism Guide <https://github.com/trdunsworth/synth911gen3/blob/main/REALISMGUIDE.md>

Overview
--------

The package splits into a few cooperating layers:

- **Configuration** — :mod:`synth911gen3.config` (the generation request),
  :mod:`synth911gen3.params` (params files), :mod:`synth911gen3.realism_config`
  (YAML realism tuning), and :mod:`synth911gen3.schema` (pydantic models).
- **Data sources** — :mod:`synth911gen3.addresses` (static and OpenStreetMap
  address providers), :mod:`synth911gen3.names` (personnel names), and
  :mod:`synth911gen3.emergency_numbers`.
- **Generation** — :class:`synth911gen3.app.Synth911Application` orchestrates
  :mod:`synth911gen3.generators.incidents` and
  :mod:`synth911gen3.generators.phone_metrics`.
- **Export** — :mod:`synth911gen3.exporters` (csv/parquet/json/yaml/geo),
  :mod:`synth911gen3.db_exporter` (SQL dialects), and
  :mod:`synth911gen3.manifest`.
- **Interfaces** — :mod:`synth911gen3.cli` (Typer), :mod:`synth911gen3.tui`
  (Textual), and :mod:`synth911gen3.serve` (FastAPI).

Versioning
----------

Generated datasets embed the generator version and realism-config fingerprint
in a manifest (see :mod:`synth911gen3.manifest`). Release history is in
`CHANGELOG.md <https://github.com/trdunsworth/synth911gen3/blob/main/CHANGELOG.md>`_.
