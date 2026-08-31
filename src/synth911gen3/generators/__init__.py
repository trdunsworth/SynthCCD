"""Generator package: incident and phone-metrics simulation engines.

- :class:`~synth911gen3.generators.incidents.IncidentGenerator` — CAD
  incident records with agency/priority-weighted timing, address pools,
  and personnel.
- :class:`~synth911gen3.generators.phone_metrics.HourlyCallCountGenerator`
  — hourly center call volumes, abandonments, and answer-time service
  levels.

Both honor a seed, the realism configuration, and the output constraints
from :class:`~synth911gen3.config.GenerationRequest`.
"""

from .incidents import IncidentGenerator, PreparedState
from .phone_metrics import HourlyCallCountGenerator

__all__ = ["HourlyCallCountGenerator", "IncidentGenerator", "PreparedState"]
