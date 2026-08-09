from __future__ import annotations

import numpy as np

DEFAULT_ROWS = 10_000
DEFAULT_AREA_QUERY = "Kansas City, MO"
DEFAULT_OUTPUT_DIR = "output"
DEFAULT_OUTPUT_STEM = "synthetic_911"
DEFAULT_LOCALE = "en_US"

# When ``max_memory_bytes`` is unset, incident CSV/Parquet generation is
# chunked once the estimated in-memory DataFrame would exceed this budget.
DEFAULT_MAX_MEMORY_BYTES = 2 * 1024**3
# Probe rows used to estimate per-row memory for the budget guard.
MEMORY_PROBE_ROWS = 10_000

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
            ("Noise Complaint", 0.20),
            ("Welfare Check", 0.18),
            ("Found Property", 0.13),
            ("Animal Complaint", 0.10),
            ("Animal Bite", 0.06),
            ("Traffic Stop", 0.10),
            ("Public Assist", 0.10),
            ("Vandalism", 0.07),
            ("Suspicious Person", 0.06),
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
            ("Fire Alarm", 0.25),
            ("Smoke Investigation", 0.20),
            ("Overheat Investigation", 0.12),
            ("Odor Investigation", 0.12),
            ("CO Investigation", 0.10),
            ("Medical Assist", 0.10),
            ("Mutual Aid", 0.06),
            ("Brush/Grass Fire", 0.05),
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
            ("Fire Alarm", 0.25),
            ("Smoke Investigation", 0.15),
            ("Odor Investigation", 0.15),
            ("Lockout / Public Service", 0.15),
            ("Mutual Aid", 0.15),
            ("Assist Police", 0.10),
            ("Overheat Investigation", 0.05),
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
            ("Sick Person", 0.25),
            ("Fall Injury", 0.15),
            ("Animal Bite", 0.12),
            ("Psychiatric Emergency", 0.12),
            ("Heat/Cold Exposure", 0.10),
            ("Traumatic Injury", 0.08),
            ("Abdominal Pain", 0.08),
            ("Diabetic Problem", 0.10),
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
}

TIME_PROFILES = {
    "LAW": {
        1: {"interview_mean": 12, "dispatch_mean": 4, "turnout_mean": 10, "travel_mean": 220, "scene_mean": 1_500, "closeout_mean": 240, "phone_mean": 170},
        2: {"interview_mean": 25, "dispatch_mean": 12, "turnout_mean": 22, "travel_mean": 260, "scene_mean": 1_650, "closeout_mean": 270, "phone_mean": 210},
        3: {"interview_mean": 45, "dispatch_mean": 25, "turnout_mean": 35, "travel_mean": 320, "scene_mean": 1_920, "closeout_mean": 330, "phone_mean": 250},
        4: {"interview_mean": 70, "dispatch_mean": 140, "turnout_mean": 55, "travel_mean": 410, "scene_mean": 2_220, "closeout_mean": 360, "phone_mean": 300},
        5: {"interview_mean": 95, "dispatch_mean": 320, "turnout_mean": 70, "travel_mean": 520, "scene_mean": 2_460, "closeout_mean": 390, "phone_mean": 340},
    },
    "FIRE": {
        1: {"interview_mean": 16, "dispatch_mean": 6, "turnout_mean": 28, "travel_mean": 300, "scene_mean": 2_100, "closeout_mean": 300, "phone_mean": 160},
        2: {"interview_mean": 30, "dispatch_mean": 18, "turnout_mean": 40, "travel_mean": 340, "scene_mean": 2_280, "closeout_mean": 330, "phone_mean": 190},
        3: {"interview_mean": 52, "dispatch_mean": 35, "turnout_mean": 55, "travel_mean": 390, "scene_mean": 2_520, "closeout_mean": 360, "phone_mean": 230},
        4: {"interview_mean": 80, "dispatch_mean": 170, "turnout_mean": 70, "travel_mean": 470, "scene_mean": 2_760, "closeout_mean": 390, "phone_mean": 270},
        5: {"interview_mean": 105, "dispatch_mean": 330, "turnout_mean": 84, "travel_mean": 560, "scene_mean": 3_060, "closeout_mean": 420, "phone_mean": 320},
    },
    "EMS": {
        1: {"interview_mean": 14, "dispatch_mean": 5, "turnout_mean": 16, "travel_mean": 240, "scene_mean": 1_380, "closeout_mean": 240, "phone_mean": 200},
        2: {"interview_mean": 28, "dispatch_mean": 14, "turnout_mean": 28, "travel_mean": 280, "scene_mean": 1_560, "closeout_mean": 270, "phone_mean": 230},
        3: {"interview_mean": 50, "dispatch_mean": 30, "turnout_mean": 40, "travel_mean": 340, "scene_mean": 1_800, "closeout_mean": 300, "phone_mean": 260},
        4: {"interview_mean": 74, "dispatch_mean": 155, "turnout_mean": 55, "travel_mean": 430, "scene_mean": 2_040, "closeout_mean": 330, "phone_mean": 290},
        5: {"interview_mean": 100, "dispatch_mean": 315, "turnout_mean": 70, "travel_mean": 520, "scene_mean": 2_280, "closeout_mean": 360, "phone_mean": 330},
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
