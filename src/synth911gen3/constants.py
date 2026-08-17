"""Default realism constants for synthetic data generation.

Every table here is the built-in default profile of a typical large
American 9-1-1 center. They feed three consumers:

* the generator core (:mod:`synth911gen3.generators.incidents`),
* the hourly phone metrics generator
  (:mod:`synth911gen3.generators.phone_metrics`), and
* :class:`synth911gen3.realism_config.RealismConfig`, which deep-copies
  them into a runtime config that users can override via YAML.

Conventions:

* Weight tables (``AGENCY_WEIGHTS``, ``PRIORITY_WEIGHTS``,
  ``PROBLEM_PROFILES``, ``CALL_RECEPTION_WEIGHTS``,
  ``DISPOSITION_PROFILES``) each sum to 1.0 per scope; the schema and
  regression suites enforce this.
* ``PROBLEM_PROFILES`` is keyed by agency then priority (1 = highest,
  5 = lowest); each entry is a ``(problem_name, weight)`` pair.
* ``SEASONAL_MULTIPLIERS`` and ``PROBLEM_PHONE_MULTIPLIERS`` apply
  per-incident scaling to problem selection weight and call duration
  respectively. Problems without an entry use the ``DEFAULT_*`` fallbacks.
* Priorities are 1-5 integers; seasons are indexed
  0=Winter, 1=Spring, 2=Summer, 3=Fall.

Bump ``DATA_SCHEMA_VERSION`` when generated columns change in a breaking
way; it is embedded in Parquet metadata and the governance manifest.
"""

from __future__ import annotations

import numpy as np

DEFAULT_ROWS = 10_000
DEFAULT_AREA_QUERY = "Kansas City, MO"
DEFAULT_OUTPUT_DIR = "output"
DEFAULT_OUTPUT_STEM = "synthetic_911"
DEFAULT_LOCALE = "en_US"
DEFAULT_COUNTRY = "US"

# Version of the generated incident / phone-metrics data schema. Bump when
# columns change in a breaking way. Embedded in Parquet file metadata and in
# the data-governance manifest so consumers can detect schema drift.
DATA_SCHEMA_VERSION = "1.1"

# When ``max_memory_bytes`` is unset, incident CSV/Parquet generation is
# chunked once the estimated in-memory DataFrame would exceed this budget.
DEFAULT_MAX_MEMORY_BYTES = 2 * 1024**3
# Probe rows used to estimate per-row memory for the budget guard.
MEMORY_PROBE_ROWS = 10_000

# Typical US PSAP calls per 1,000 population per year (NFPA/NAEM data).
# Used when ``population`` is set on the generation request to derive
# phone-metrics volume independently from the incident row count.
CALLS_PER_1000_POPULATION_YEARLY: float = 2_500.0

# Minimum ratio of non-emergency to emergency received calls.
# After independent Poisson draws, non-emergency is floored to at least
# this ratio × emergency so the output always reflects the real-world
# pattern of non-emergency calls exceeding emergency calls.
NON_EMERGENCY_FLOOR_RATIO: float = 1.2

AGENCY_WEIGHTS = {
    "LAW": 0.52,
    "FIRE": 0.20,
    "EMS": 0.28,
}

PRIORITY_WEIGHTS = {
    "LAW": {1: 0.12, 2: 0.18, 3: 0.28, 4: 0.26, 5: 0.16},
    "FIRE": {1: 0.18, 2: 0.24, 3: 0.24, 4: 0.20, 5: 0.14},
    "EMS": {1: 0.16, 2: 0.26, 3: 0.28, 4: 0.18, 5: 0.12},
}

DISPATCH_INIT_FRACTION = {
    1: (0.05, 0.20),
    2: (0.20, 0.50),
    3: (0.40, 0.80),
    4: (0.90, 1.10),
    5: (1.00, 1.30),
}

PROBLEM_PROFILES = {
    "LAW": {
        1: [
            ("Shots Fired", 0.20),
            ("Burglary In Progress", 0.15),
            ("Vehicle Collision w/ Injury", 0.15),
            ("Assault", 0.12),
            ("Reckless Driving", 0.10),
            ("Weapons Violation", 0.08),
            ("DUI / Impaired Driver", 0.08),
            ("Domestic Disturbance", 0.07),
            ("Missing Person", 0.05),
        ],
        2: [
            ("Domestic Disturbance", 0.18),
            ("Assault", 0.15),
            ("Burglary", 0.12),
            ("Drug/Narcotic Violation", 0.10),
            ("Motor Vehicle Theft", 0.10),
            ("DUI / Impaired Driver", 0.10),
            ("Vehicle Collision w/ Injury", 0.10),
            ("Robbery", 0.08),
            ("Disorderly Conduct", 0.07),
        ],
        3: [
            ("Theft Report", 0.20),
            ("Burglary Alarm", 0.15),
            ("Traffic Crash", 0.12),
            ("Fraud", 0.10),
            ("Harassment", 0.09),
            ("Shoplifting", 0.08),
            ("Vandalism", 0.08),
            ("Trespass", 0.06),
            ("Suspicious Person", 0.06),
            ("Welfare Check", 0.06),
        ],
        4: [
            ("Noise Complaint", 0.19),
            ("Traffic Stop", 0.17),
            ("Suspicious Person", 0.15),
            ("Welfare Check", 0.13),
            ("Disorderly Conduct", 0.11),
            ("Animal Complaint", 0.08),
            ("Vandalism", 0.07),
            ("Trespass", 0.05),
            ("Harassment", 0.05),
        ],
        5: [
            ("Noise Complaint", 0.16),
            ("Welfare Check", 0.15),
            ("Found Property", 0.11),
            ("Animal Complaint", 0.08),
            ("Animal Bite", 0.05),
            ("Traffic Stop", 0.08),
            ("Public Assist", 0.08),
            ("Vandalism", 0.06),
            ("Suspicious Person", 0.05),
            ("Assist Fire", 0.08),
            ("Assist EMS", 0.10),
        ],
    },
    "FIRE": {
        1: [
            ("Structure Fire", 0.30),
            ("Rescue Call", 0.15),
            ("Vehicle Fire", 0.15),
            ("Gas Leak", 0.12),
            ("Hazardous Condition", 0.10),
            ("Vehicle Extrication", 0.10),
            ("Water Rescue", 0.08),
        ],
        2: [
            ("Structure Fire", 0.15),
            ("Vehicle Fire", 0.20),
            ("Cooking Fire", 0.15),
            ("Brush/Grass Fire", 0.12),
            ("Gas Leak", 0.10),
            ("CO Investigation", 0.10),
            ("Elevator Rescue", 0.10),
            ("Electrical Wiring Problem", 0.08),
        ],
        3: [
            ("Fire Alarm", 0.22),
            ("Smoke Investigation", 0.18),
            ("Overheat Investigation", 0.12),
            ("Odor Investigation", 0.12),
            ("CO Investigation", 0.10),
            ("Medical Assist", 0.10),
            ("Chimney Fire", 0.08),
            ("Mutual Aid", 0.05),
            ("Brush/Grass Fire", 0.03),
        ],
        4: [
            ("Fire Alarm", 0.30),
            ("Smoke Investigation", 0.20),
            ("Odor Investigation", 0.15),
            ("Overheat Investigation", 0.15),
            ("Medical Assist", 0.10),
            ("Mutual Aid", 0.10),
        ],
        5: [
            ("Fire Alarm", 0.22),
            ("Smoke Investigation", 0.13),
            ("Odor Investigation", 0.13),
            ("Lockout / Public Service", 0.13),
            ("Mutual Aid", 0.13),
            ("Assist Police", 0.09),
            ("Assist EMS", 0.09),
            ("Overheat Investigation", 0.04),
            ("Medical Assist", 0.04),
        ],
    },
    "EMS": {
        1: [
            ("Cardiac Arrest", 0.15),
            ("Choking", 0.10),
            ("Unconscious Person", 0.15),
            ("Difficulty Breathing", 0.15),
            ("Stroke", 0.12),
            ("Hemorrhage / Bleeding", 0.13),
            ("Seizure", 0.10),
            ("Chest Pain", 0.10),
        ],
        2: [
            ("Chest Pain", 0.18),
            ("Difficulty Breathing", 0.15),
            ("Altered Mental Status", 0.12),
            ("Heart Problems", 0.12),
            ("Overdose", 0.12),
            ("Head Injury", 0.10),
            ("Seizure", 0.08),
            ("Allergic Reaction", 0.08),
            ("Traumatic Injury", 0.05),
        ],
        3: [
            ("Fall Injury", 0.18),
            ("Motor Vehicle Crash", 0.15),
            ("Abdominal Pain", 0.12),
            ("Diabetic Problem", 0.10),
            ("Sick Person", 0.10),
            ("Traumatic Injury", 0.10),
            ("Head Injury", 0.08),
            ("Allergic Reaction", 0.07),
            ("Pregnancy / Childbirth", 0.05),
            ("Overdose", 0.05),
        ],
        4: [
            ("Fall Injury", 0.20),
            ("Sick Person", 0.18),
            ("Abdominal Pain", 0.14),
            ("Motor Vehicle Crash", 0.12),
            ("Traumatic Injury", 0.10),
            ("Diabetic Problem", 0.08),
            ("Psychiatric Emergency", 0.08),
            ("Animal Bite", 0.05),
            ("Heat/Cold Exposure", 0.05),
        ],
        5: [
            ("Sick Person", 0.20),
            ("Fall Injury", 0.12),
            ("Animal Bite", 0.10),
            ("Psychiatric Emergency", 0.10),
            ("Heat/Cold Exposure", 0.08),
            ("Traumatic Injury", 0.06),
            ("Abdominal Pain", 0.06),
            ("Diabetic Problem", 0.08),
            ("Assist Police", 0.10),
            ("Assist Fire", 0.10),
        ],
    },
}

CALL_RECEPTION_WEIGHTS = {
    "E-911": 0.33,
    "Phone": 0.38,
    "OFFICER": 0.14,
    "Radio": 0.06,
    "C2C": 0.05,
    "NOT CAPTURED": 0.02,
    "Text": 0.01,
    "CAD2CAD": 0.01,
}

DISPOSITION_PROFILES = {
    "LAW": [
        ("NR-No Report", 0.40),
        ("UNDEFINED", 0.28),
        ("RE-Report", 0.15),
        ("CI-Citation", 0.10),
        ("CN-Cancellation", 0.04),
        ("ACOR-Animal Control", 0.02),
        ("SUP-Supplement", 0.01),
    ],
    "FIRE": [
        ("NR-No Report", 0.45),
        ("UNDEFINED", 0.29),
        ("FALSE-False Alarm", 0.15),
        ("CN-Cancellation", 0.05),
        ("RAF-Reassign FD Call", 0.05),
        ("SUP-Supplement", 0.01),
    ],
    "EMS": [
        ("NR-No Report", 0.45),
        ("UNDEFINED", 0.38),
        ("FALSE-False Alarm", 0.10),
        ("CN-Cancellation", 0.05),
        ("SUP-Supplement", 0.02),
    ],
}

PHONE_METRICS: dict[str, float | list[float]] = {
    "min_hourly_volume": 2.0,
    "nine_one_one_received_fraction": 0.48,
    "non_emergency_received_fraction": 0.58,
    "outbound_calls_fraction": 0.26,
    "nine_one_one_abandonment_rate": 0.02,
    "night_abandonment_increment": 0.03,
    "non_emergency_abandonment_rate": 0.05,
    "max_abandonment_rate": 0.12,
    "weekend_multiplier": 1.12,
    "nine_one_one_answer_time_mu": 1.80,
    "nine_one_one_answer_time_sigma": 0.80,
    "non_emergency_answer_time_mu": 1.70,
    "non_emergency_answer_time_sigma": 0.80,
    "answer_time_thresholds": [10.0, 15.0, 20.0, 40.0],
    "answer_time_load_sensitivity": 0.25,
    "answer_time_mu_noise_sd": 0.05,
}

TIME_PROFILES = {
    "LAW": {
        1: {
            "interview_mean": 12,
            "dispatch_mean": 4,
            "turnout_mean": 10,
            "travel_mean": 220,
            "scene_mean": 1_500,
            "closeout_mean": 240,
            "phone_mean": 170,
        },
        2: {
            "interview_mean": 25,
            "dispatch_mean": 12,
            "turnout_mean": 22,
            "travel_mean": 260,
            "scene_mean": 1_650,
            "closeout_mean": 270,
            "phone_mean": 210,
        },
        3: {
            "interview_mean": 45,
            "dispatch_mean": 25,
            "turnout_mean": 35,
            "travel_mean": 320,
            "scene_mean": 1_920,
            "closeout_mean": 330,
            "phone_mean": 250,
        },
        4: {
            "interview_mean": 70,
            "dispatch_mean": 140,
            "turnout_mean": 55,
            "travel_mean": 410,
            "scene_mean": 2_220,
            "closeout_mean": 360,
            "phone_mean": 300,
        },
        5: {
            "interview_mean": 95,
            "dispatch_mean": 320,
            "turnout_mean": 70,
            "travel_mean": 520,
            "scene_mean": 2_460,
            "closeout_mean": 390,
            "phone_mean": 340,
        },
    },
    "FIRE": {
        1: {
            "interview_mean": 16,
            "dispatch_mean": 6,
            "turnout_mean": 28,
            "travel_mean": 300,
            "scene_mean": 2_100,
            "closeout_mean": 300,
            "phone_mean": 160,
        },
        2: {
            "interview_mean": 30,
            "dispatch_mean": 18,
            "turnout_mean": 40,
            "travel_mean": 340,
            "scene_mean": 2_280,
            "closeout_mean": 330,
            "phone_mean": 190,
        },
        3: {
            "interview_mean": 52,
            "dispatch_mean": 35,
            "turnout_mean": 55,
            "travel_mean": 390,
            "scene_mean": 2_520,
            "closeout_mean": 360,
            "phone_mean": 230,
        },
        4: {
            "interview_mean": 80,
            "dispatch_mean": 170,
            "turnout_mean": 70,
            "travel_mean": 470,
            "scene_mean": 2_760,
            "closeout_mean": 390,
            "phone_mean": 270,
        },
        5: {
            "interview_mean": 105,
            "dispatch_mean": 330,
            "turnout_mean": 84,
            "travel_mean": 560,
            "scene_mean": 3_060,
            "closeout_mean": 420,
            "phone_mean": 320,
        },
    },
    "EMS": {
        1: {
            "interview_mean": 14,
            "dispatch_mean": 5,
            "turnout_mean": 16,
            "travel_mean": 240,
            "scene_mean": 1_380,
            "closeout_mean": 240,
            "phone_mean": 200,
        },
        2: {
            "interview_mean": 28,
            "dispatch_mean": 14,
            "turnout_mean": 28,
            "travel_mean": 280,
            "scene_mean": 1_560,
            "closeout_mean": 270,
            "phone_mean": 230,
        },
        3: {
            "interview_mean": 50,
            "dispatch_mean": 30,
            "turnout_mean": 40,
            "travel_mean": 340,
            "scene_mean": 1_800,
            "closeout_mean": 300,
            "phone_mean": 260,
        },
        4: {
            "interview_mean": 74,
            "dispatch_mean": 155,
            "turnout_mean": 55,
            "travel_mean": 430,
            "scene_mean": 2_040,
            "closeout_mean": 330,
            "phone_mean": 290,
        },
        5: {
            "interview_mean": 100,
            "dispatch_mean": 315,
            "turnout_mean": 70,
            "travel_mean": 520,
            "scene_mean": 2_280,
            "closeout_mean": 360,
            "phone_mean": 330,
        },
    },
}

HOURLY_WEIGHTS = np.array(
    [
        0.030,
        0.025,
        0.022,
        0.020,
        0.022,
        0.028,
        0.038,
        0.048,
        0.052,
        0.055,
        0.058,
        0.060,
        0.062,
        0.060,
        0.058,
        0.058,
        0.055,
        0.052,
        0.050,
        0.048,
        0.045,
        0.042,
        0.038,
        0.034,
    ],
    dtype=float,
)
HOURLY_WEIGHTS /= HOURLY_WEIGHTS.sum()

# Seasonal multipliers for problem types
# Multipliers > 1.0 increase likelihood in that season, < 1.0 decrease
# Seasons: 0=Winter (Dec-Feb), 1=Spring (Mar-May), 2=Summer (Jun-Aug), 3=Fall (Sep-Nov)
SEASONAL_MULTIPLIERS: dict[str, list[float]] = {
    # EMS - Heat/cold related
    "Heat/Cold Exposure": [1.5, 0.8, 2.0, 0.8],
    "Sick Person": [1.2, 1.0, 0.9, 1.1],
    "Fall Injury": [1.3, 0.9, 0.8, 1.1],
    "Motor Vehicle Crash": [1.2, 1.0, 1.1, 1.1],
    "Cardiac Arrest": [1.1, 1.0, 0.9, 1.0],
    "Hypothermia": [3.0, 0.5, 0.1, 1.0],
    "Heat Exhaustion": [0.1, 0.5, 3.0, 0.5],
    # FIRE - Seasonal fire patterns
    "Structure Fire": [1.3, 0.9, 0.8, 1.1],
    "Brush/Grass Fire": [0.3, 1.2, 2.0, 1.5],
    "Cooking Fire": [1.2, 1.0, 0.9, 1.3],
    "Chimney Fire": [2.5, 0.5, 0.1, 1.5],
    "Vehicle Fire": [1.1, 1.0, 1.1, 1.0],
    "Mutual Aid": [1.1, 1.0, 1.2, 1.1],
    # LAW - Seasonal crime/behavior patterns
    "DUI / Impaired Driver": [1.3, 1.0, 1.2, 1.1],
    "Domestic Disturbance": [1.1, 1.0, 1.0, 1.1],
    "Burglary": [1.1, 0.9, 1.0, 1.1],
    "Motor Vehicle Theft": [1.1, 1.0, 1.1, 1.0],
    "Reckless Driving": [1.2, 1.0, 1.1, 1.1],
    "Disorderly Conduct": [1.0, 1.1, 1.2, 1.0],
    "Noise Complaint": [0.8, 1.0, 1.3, 1.1],
    "Suspicious Person": [1.0, 1.0, 1.1, 1.0],
    "Shots Fired": [1.1, 1.0, 1.2, 1.1],
    "Shoplifting": [1.3, 0.9, 0.9, 1.2],
    "Vandalism": [0.9, 1.1, 1.2, 1.1],
    "Trespass": [0.9, 1.0, 1.1, 1.2],
    "Animal Complaint": [0.8, 1.2, 1.3, 1.1],
    "Animal Bite": [0.8, 1.2, 1.3, 1.0],
    "Welfare Check": [1.2, 1.0, 0.9, 1.1],
    "Missing Person": [1.1, 1.0, 1.1, 1.0],
}

# Default multiplier for any problem type not explicitly listed
DEFAULT_SEASONAL_MULTIPLIER = [1.0, 1.0, 1.0, 1.0]

# Geographic zone travel time multipliers
# Applied to base travel_mean from TIME_PROFILES based on address zone
# URBAN: dense city center, shorter travel distances
# SUBURBAN: residential outskirts, moderate travel distances
# RURAL: sparse areas, longer travel distances
ZONE_TRAVEL_MULTIPLIERS = {
    "URBAN": 0.8,
    "SUBURBAN": 1.0,
    "RURAL": 1.5,
}

# Problem-type phone duration multipliers
# Applied to base phone_mean from TIME_PROFILES based on problem nature
# Values > 1.0 increase call duration, < 1.0 decrease call duration
# Default is 1.0 for any problem type not explicitly listed
PROBLEM_PHONE_MULTIPLIERS: dict[str, float] = {
    # LAW - High complexity / long duration
    "Active Shooter": 2.5,
    "Barricaded Subject": 2.0,
    "Hostage Situation": 2.5,
    "Homicide": 1.8,
    "Robbery": 1.4,
    "Shots Fired": 1.6,
    "Burglary In Progress": 1.5,
    "Vehicle Collision w/ Injury": 1.3,
    "Assault": 1.3,
    "Domestic Disturbance": 1.4,
    "Missing Person": 1.4,
    "Weapons Violation": 1.3,
    "Reckless Driving": 1.2,
    "DUI / Impaired Driver": 1.3,
    "Burglary": 1.2,
    "Drug/Narcotic Violation": 1.2,
    "Motor Vehicle Theft": 1.1,
    "Disorderly Conduct": 1.1,
    "Theft Report": 1.1,
    "Burglary Alarm": 1.0,
    "Traffic Crash": 1.2,
    "Fraud": 1.1,
    "Harassment": 1.1,
    "Shoplifting": 1.1,
    "Vandalism": 1.1,
    "Trespass": 1.0,
    "Suspicious Person": 1.1,
    "Welfare Check": 1.2,
    "Noise Complaint": 1.0,
    "Traffic Stop": 1.0,
    "Found Property": 1.0,
    "Animal Complaint": 1.0,
    "Animal Bite": 1.2,
    "Public Assist": 1.0,
    "Assist Fire": 1.2,
    "Assist EMS": 1.2,
    # FIRE - High complexity / long duration
    "Structure Fire": 1.5,
    "Rescue Call": 1.4,
    "Vehicle Fire": 1.3,
    "Gas Leak": 1.4,
    "Hazardous Condition": 1.3,
    "Vehicle Extrication": 1.5,
    "Water Rescue": 1.6,
    "Cooking Fire": 1.1,
    "Brush/Grass Fire": 1.3,
    "CO Investigation": 1.1,
    "Elevator Rescue": 1.2,
    "Electrical Wiring Problem": 1.1,
    "Fire Alarm": 1.0,
    "Smoke Investigation": 1.1,
    "Overheat Investigation": 1.0,
    "Odor Investigation": 1.0,
    "Medical Assist": 1.2,
    "Mutual Aid": 1.2,
    "Lockout / Public Service": 1.0,
    "Assist Police": 1.2,
    # EMS - High complexity / long duration
    "Cardiac Arrest": 1.6,
    "Choking": 1.5,
    "Unconscious Person": 1.4,
    "Difficulty Breathing": 1.3,
    "Stroke": 1.5,
    "Hemorrhage / Bleeding": 1.4,
    "Seizure": 1.3,
    "Chest Pain": 1.3,
    "Altered Mental Status": 1.3,
    "Heart Problems": 1.3,
    "Overdose": 1.4,
    "Head Injury": 1.4,
    "Allergic Reaction": 1.3,
    "Traumatic Injury": 1.3,
    "Fall Injury": 1.2,
    "Motor Vehicle Crash": 1.3,
    "Abdominal Pain": 1.2,
    "Diabetic Problem": 1.2,
    "Sick Person": 1.1,
    "Pregnancy / Childbirth": 1.4,
    "Psychiatric Emergency": 1.3,
    "Heat/Cold Exposure": 1.2,
}

# Default multiplier for any problem type not explicitly listed
DEFAULT_PROBLEM_PHONE_MULTIPLIER = 1.0
