from __future__ import annotations

import numpy as np

DEFAULT_ROWS = 10_000
DEFAULT_AREA_QUERY = "Kansas City, MO"
DEFAULT_OUTPUT_DIR = "output"
DEFAULT_OUTPUT_STEM = "synthetic_911"
DEFAULT_LOCALE = "en_US"

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

PROBLEM_PROFILES = {
    "LAW": [
        ("Noise Complaint", 0.16),
        ("Suspicious Person", 0.14),
        ("Domestic Disturbance", 0.12),
        ("Traffic Crash", 0.12),
        ("Burglary Alarm", 0.11),
        ("Welfare Check", 0.11),
        ("Theft Report", 0.10),
        ("Disorderly Conduct", 0.08),
        ("Shots Fired", 0.06),
    ],
    "FIRE": [
        ("Fire Alarm", 0.22),
        ("Structure Fire", 0.14),
        ("Vehicle Fire", 0.10),
        ("Gas Leak", 0.10),
        ("Smoke Investigation", 0.16),
        ("Rescue Call", 0.10),
        ("Hazardous Condition", 0.10),
        ("Mutual Aid", 0.08),
    ],
    "EMS": [
        ("Chest Pain", 0.16),
        ("Difficulty Breathing", 0.15),
        ("Fall Injury", 0.13),
        ("Unconscious Person", 0.12),
        ("Motor Vehicle Crash", 0.10),
        ("Seizure", 0.10),
        ("Overdose", 0.08),
        ("Psychiatric Emergency", 0.08),
        ("Sick Person", 0.08),
    ],
}

CALL_RECEPTION_WEIGHTS = {
    "911": 0.38,
    "Phone": 0.31,
    "Radio": 0.16,
    "Walk In": 0.09,
    "Flag Down": 0.06,
}

DISPOSITION_PROFILES = {
    "LAW": [
        ("Report Issued", 0.34),
        ("No Report Issued", 0.26),
        ("Cancelled", 0.18),
        ("No Action Taken", 0.22),
    ],
    "FIRE": [
        ("Report Issued", 0.49),
        ("No Report Issued", 0.18),
        ("Cancelled", 0.14),
        ("No Action Taken", 0.19),
    ],
    "EMS": [
        ("Report Issued", 0.44),
        ("No Report Issued", 0.23),
        ("Cancelled", 0.12),
        ("No Action Taken", 0.21),
    ],
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
