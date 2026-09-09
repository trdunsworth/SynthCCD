# Per-center calibration library

Ready-made realism starting points derived from published open-data
portals. Each file cites its sources and confidence level in its header.
Pass one with `--config` alongside `--population`:

```
SynthCCD generate --population 521250 \
  --config config/calibrations/kansas_city_mo.yaml \
  --dataset all --include-event-counts ...
```

| Area query | File | 911/1,000/yr | 911 share | 911 abandon | Confidence |
|---|---|---|---|---|---|
| Kansas City, MO | `kansas_city_mo.yaml` | 1,148 | 51.5% | ~10% | measured |
| New York, NY | `new_york_ny.yaml` | 1,200 | ~51% | ~8% | estimated |
| Washington, DC | `washington_dc.yaml` | 1,300 | ~51% | ~12% | measured range |
| Norfolk, VA | `norfolk_va.yaml` | 722 | ~48% | ~15% | measured |
| King County, WA | `king_county_wa.yaml` | 1,100 | ~51% | ~7% | estimated |
| Vermont (rural) | `vermont_rural.yaml` | 360 | ~51% | ~6.5% | measured |
| Albuquerque, NM | `albuquerque_nm.yaml` | 1,000 (tier) | ~51% | ~7% | estimated (staffing spec; volumes from national tiers) |

National tier defaults (no `--config`) are 400 / 650 / 1,000 / 1,100 by
population bracket — see `population_rates` in REALISMGUIDE.md.

To mint a new center file: copy the closest file, replace the
`population_rates` and `phone_metrics` values with the center's published
volumes, cite the portal URL + access date in the header, and validate with
`SynthCCD validate-config <file>`.
