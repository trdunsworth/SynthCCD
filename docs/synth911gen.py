#!/usr/bin/env python
"""
Core data generation engine for Synth911Gen2.

This module provides the main logic for generating synthetic 911 dispatch data, including problem/priority assignment, agency selection, time calculations, and output formatting. It supports both programmatic and CLI/interactive usage. The module also includes input sanitization utilities and compatibility handling for optional dependencies.
"""

import argparse
import random
import re
import sys
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import polars as pl
from faker import Faker
from faker.providers import DynamicProvider

from shared.constants import DEFAULT_LOCALE, validate_locale

# Try to import PyInquirer, but provide fallback if it's not available
class ValidationError(Exception):
    """
    Custom validation error for input validation.

    Args:
        message (str): The error message to display.
        cursor_position (int): The position in the input where the error occurred.
    """
    def __init__(self, message, cursor_position):
        self.message = message
        self.cursor_position = cursor_position
        super().__init__(message)

try:
    from PyInquirer import prompt, Validator
    PYINQUIRER_AVAILABLE = True
except ImportError:
    print("Warning: PyInquirer is not available. Using command-line arguments instead.")
    PYINQUIRER_AVAILABLE = False

    # Define a dummy Validator base class if PyInquirer is not available
    class Validator(object):
        """
        Dummy Validator base class for CLI fallback when PyInquirer is not available.
        Used to maintain compatibility with code expecting a Validator base class.
        """

    def prompt(*args, **kwargs):
        """
        Dummy prompt function for CLI fallback when PyInquirer is not available.
        Raises a RuntimeError to indicate that interactive prompts are not supported.
        """
        raise RuntimeError("PyInquirer is not available. CLI mode only.")

def sanitize_input(user_input):
    """
    Sanitize user input to allow only letters, numbers, spaces, and hyphens.

    Args:
        user_input (str): The input string to sanitize.

    Returns:
        str: The sanitized input string.

    Raises:
        ValueError: If the input contains invalid characters.
    """
    pattern = r'^[a-zA-Z0-9\s-]+$'
    if not re.match(pattern, user_input):
        raise ValueError("Input contains invalid characters. Only letters, numbers, spaces, and hyphens are allowed.")
    return user_input

def sanitize_cli():
    """
    Utility function to test input sanitization from the command line.
    Parses a command-line argument and prints the sanitized result or error.
    """
    parser = argparse.ArgumentParser(description="Sanitize user input options in synth911gen.py")
    parser.add_argument('--option', type=str, required=True, help='User input option')
    args = parser.parse_args()
    try:
        sanitized_option = sanitize_input(args.option)
        print(f"Sanitized Option: {sanitized_option}")
    except ValueError as e:
        print(e)

# Note: This function is for testing sanitization only
# The actual entry point is at the bottom of the file

# Law enforcement problems with their associated priority levels
# Priority 1: Immediate response, life-threatening
# Priority 2: Urgent response, potential for harm
# Priority 3: Prompt response, no immediate danger
# Priority 4: Routine response, minor issues
# Priority 5: Non-urgent, administrative or delayed response

LAW_PROBLEMS = [
    # Priority 1 (Immediate response, life-threatening)
    ("WEAPON VIOL GUN IN PROG", 1),
    ("ALARM RESIDENTIAL NIGHTIME", 1),
    ("ROBBERY IN PROGRESS", 1),
    ("SHOOTING", 1),
    ("STABBING", 1),
    ("OFFICER NEEDS ASSISTANCE", 1),
    ("HOSTAGE SITUATION", 1),
    ("SUICIDAL SUBJECT", 1),

    # Priority 2 (Urgent response, potential for harm)
    ("DOMESTIC VIOL NO INJ", 2),
    ("DOMESTIC VIOL WITH INJ", 2),
    ("DWI - DRUNK/INTOX DRIVER", 2),
    ("DISORDERLY CONDUCT", 2),
    ("911 HANG UP", 2),
    ("ASSAULT", 2),
    ("BURGLARY IN PROGRESS", 2),
    ("SUSPICIOUS PERSON WITH WEAPON", 2),

    # Priority 3 (Prompt response, no immediate danger)
    ("SUSPICIOUS EVENT", 3),
    ("SUSPICIOUS PERSON", 3),
    ("SUSPICIOUS VEHICLE", 3),
    ("TRESPASSING", 3),
    ("LARCENY IN PROGRESS", 3),
    ("TRAFFIC ACCIDENT NO INJURY", 3),
    ("ALARM COMMERCIAL", 3),

    # Priority 4 (Routine response, minor issues)
    ("NOISE COMPLAINT IN PROG", 4),
    ("NOISE COMPLAINT DELAY", 4),
    ("PARKING COMPLAINT", 4),
    ("TRAFFIC STOP", 4),
    ("DISABLED MOTORIST", 4),
    ("PUBLIC SERVICE - LAW", 4),
    ("ASSIST CITIZEN", 4),

    # Priority 5 (Non-urgent, administrative or delayed)
    ("PROPERTY LOST TRU", 5),
    ("POLICE INFORMATION", 5),
    ("FOLLOW UP", 5),
    ("LARCENY REPORT", 5),
    ("FRAUD REPORT", 5),
    ("VANDALISM REPORT", 5),
    ("MENTAL HEALTH", 5),
    ("DRUG COMPLAINT", 5),
    ("FLAG DOWN", 5),
    ("GLA", 5),
]

# Create the DynamicProvider with just the problem names
law_problem_provider = DynamicProvider(
    provider_name="law_problem",
    elements=[problem for problem, _ in LAW_PROBLEMS]
)

# Fire problems with their associated priority levels
# Priority 1: Immediate response, life-threatening
# Priority 2: Urgent response, potential for harm
# Priority 3: Prompt response, no immediate danger
# Priority 4: Routine response, minor issues
# Priority 5: Non-urgent, administrative or delayed response

FIRE_PROBLEMS = [
    # Priority 1 (Immediate response, life-threatening)
    ("RESIDENTIAL BUILDING FIRE", 1),
    ("HIGHRISE BUILDING FIRE", 1),
    ("COMMERCIAL BUILDING FIRE", 1),
    ("ENTRAPMENT", 1),
    ("MVC SCHOOL BUS", 1),
    ("HAZMAT MAJOR", 1),
    ("STRUCTURE COLLAPSE", 1),

    # Priority 2 (Urgent response, potential for harm)
    ("MVC AUTO", 2),
    ("GAS LEAK", 2),
    ("CO ALARM", 2),
    ("OUTSIDE FIRE", 2),
    ("APPLIANCE FIRE", 2),
    ("MVC MOTORCYCLE", 2),
    ("WIRES DOWN", 2),
    ("HAZMAT", 2),

    # Priority 3 (Prompt response, no immediate danger)
    ("FIRE ALARM", 3),
    ("ELEVATOR", 3),
    ("ODOR OF SMOKE", 3),
    ("WATER LEAK", 3),
    ("SMOKE DETECTOR", 3),

    # Priority 4 (Routine response, minor issues)
    ("PUBLIC SERVICE - FIRE", 4),
    ("LOCKOUT", 4),
    ("ASSIST CITIZEN - FIRE", 4),
    ("ANIMAL RESCUE", 4),

    # Priority 5 (Non-urgent, administrative or delayed)
    ("FIRE INSPECTION", 5),
    ("FIRE PREVENTION", 5),
    ("FIRE EDUCATION", 5),
    ("SMOKE DETECTOR INSTALLATION", 5),
]

# Create the DynamicProvider with just the problem names
fire_problem_provider = DynamicProvider(
    provider_name="fire_problem",
    elements=[problem for problem, _ in FIRE_PROBLEMS]
)

# EMS problems with their associated priority levels
# Priority 1: Immediate response, life-threatening
# Priority 2: Urgent response, potential for harm
# Priority 3: Prompt response, no immediate danger
# Priority 4: Routine response, minor issues
# Priority 5: Non-urgent, administrative or delayed response

EMS_PROBLEMS = [
    # Priority 1 (Immediate response, life-threatening)
    ("CARDIAC ARREST ALS", 1),
    ("UNCONSCIOUS ALS", 1),
    ("ALTERED LOC ALS", 1),
    ("STROKE ALS", 1),
    ("MUTUAL ALS", 1),
    ("ALLERGIC REACTION ALS", 1),
    ("OVERDOSE ALS", 1),
    ("TRAUMATIC INJURY ALS", 1),
    ("DROWNING", 1),

    # Priority 2 (Urgent response, potential for harm)
    ("TROUBLE BREATHING ALS", 2),
    ("CHEST PAIN ALS", 2),
    ("HEART PROBLEMS ALS", 2),
    ("SEIZURE ALS", 2),
    ("DIABETIC EMERGENCY ALS", 2),
    ("ASSAULT ALS", 2),
    ("PSYCHIATRIC EMERGENCY ALS", 2),
    ("ALS EMERGENCY", 2),

    # Priority 3 (Prompt response, no immediate danger)
    ("BLS EMERGENCY", 3),
    ("FALL BLS", 3),
    ("INJURED PERSON BLS", 3),
    ("BACK PAIN BLS", 3),
    ("HEADACHE BLS", 3),
    ("SICK PERSON BLS", 3),

    # Priority 4 (Routine response, minor issues)
    ("PUBLIC SERICE EMS", 4),
    ("MINOR MEDICAL", 4),
    ("ASSIST CITIZEN - EMS", 4),

    # Priority 5 (Non-urgent, administrative or delayed)
    ("MEDICAL ALARM", 5),
    ("ROUTINE TRANSPORT", 5),
    ("MENTAL HEALTH ALS", 5),
    ("WELFARE CHECK", 5),
]

# Create the DynamicProvider with just the problem names
ems_problem_provider = DynamicProvider(
    provider_name="ems_problem",
    elements=[problem for problem, _ in EMS_PROBLEMS]
)

# RESCUE problems with their associated priority levels
# Priority 1: Immediate response, life-threatening
# Priority 2: Urgent response, potential for harm
# Priority 3: Prompt response, no immediate danger
# Priority 4: Routine response, minor issues
# Priority 5: Non-urgent, administrative or delayed response

RESCUE_PROBLEMS = [
    # Priority 1 (Immediate response, life-threatening)
    ("WATER RESCUE IN PROGRESS", 1),
    ("MOUNTAIN RESCUE IN PROGRESS", 1),
    ("VEHICLE EXTRICATION WITH ENTRAPMENT", 1),
    ("CONFINED SPACE RESCUE", 1),
    ("HIGH ANGLE RESCUE", 1),
    ("SEARCH AND RESCUE - MISSING PERSON", 1),
    ("TECHNICAL RESCUE - STRUCTURE COLLAPSE", 1),

    # Priority 2 (Urgent response, potential for harm)
    ("WATER RESCUE STANDBY", 2),
    ("MOUNTAIN RESCUE STANDBY", 2),
    ("VEHICLE EXTRICATION NO ENTRAPMENT", 2),
    ("SEARCH AND RESCUE - NON-CRITICAL", 2),
    ("ANIMAL RESCUE - DANGEROUS SITUATION", 2),

    # Priority 3 (Prompt response, no immediate danger)
    ("ANIMAL RESCUE - NON-URGENT", 3),
    ("PUBLIC ASSIST RESCUE", 3),
    ("STANDBY FOR EVENT", 3),

    # Priority 4 (Routine response, minor issues)
    ("EQUIPMENT CHECK RESCUE", 4),
    ("TRAINING EXERCISE RESCUE", 4),
    ("PUBLIC EDUCATION RESCUE", 4),

    # Priority 5 (Non-urgent, administrative or delayed)
    ("RESCUE REPORT ONLY", 5),
    ("RESCUE INFORMATION", 5),
    ("FOLLOW UP RESCUE", 5),
]

# Create the DynamicProvider with just the problem names
rescue_problem_provider = DynamicProvider(
    provider_name="rescue_problem",
    elements=[problem for problem, _ in RESCUE_PROBLEMS]
)

# List of Dispositions
# These are the final outcomes of a call, which can be used to indicate how the call was resolved.
DISPOSITIONS = [
    "CANCELLED",
    "NO ACTION TAKEN",
    "REFERRED TO OTHER AGENCY",
    "REPORT TAKEN",
    "ARREST MADE",
    "CITATION ISSUED",
    "UNIT CLEARED",
    "TAKEN TO HOSPITAL",
]

# Create a DynamicProvider for dispositions
disposition_provider = DynamicProvider(
    provider_name="disposition",
    elements=DISPOSITIONS
)

# Street address provider will be created in the generate_911_data function
# after Faker is initialized with the specified locale


def filter_agencies(agencies, selected_agencies):
    """
    Filter the list of agencies based on user selection.

    Args:
        agencies (list): List of all available agencies.
        selected_agencies (list): List of agencies selected by the user.

    Returns:
        list: Filtered list of valid agencies.
    """
    if not selected_agencies:
        # If no selection made, return all agencies
        return agencies

    # Validate selected agencies and filter out invalid ones
    invalid_agencies = [agency for agency in selected_agencies if agency not in agencies]
    if invalid_agencies:
        print(f"Warning: The following selected agencies are not valid and will be ignored: {', '.join(invalid_agencies)}")

    # Return only the valid selected agencies
    return [agency for agency in agencies if agency in selected_agencies]

def generate_911_data(num_records=10000, start_date=None, end_date=None, num_names=8, locale=DEFAULT_LOCALE, selected_agencies=None, agency_probabilities=None):
    """
    Generate synthetic 911 dispatch data for a given number of records.

    The generated data includes fields such as call_id, agency, event_time, day_of_year, week_no, hour, day_night, dow, shift, shift_part, problem, address, priority_number, call_taker, call_reception, dispatcher, queue_time, dispatch_time, phone_time, ack_time, enroute_time, on_scene_time, process_time, total_time, and timestamps for various events.

    Args:
        num_records (int, optional): Number of records to generate. Defaults to 10000.
        start_date (str, optional): Start date in YYYY-MM-DD format. Defaults to "2024-01-01".
        end_date (str, optional): End date in YYYY-MM-DD format. Defaults to "2024-12-31".
        num_names (int, optional): Number of names to generate per shift. Defaults to 8.
        locale (str, optional): Faker locale for generating localized data. Defaults to "en_US".
        selected_agencies (list, optional): List of agencies to include. Defaults to None (all agencies).
        agency_probabilities (list, optional): List of probabilities for each agency. Defaults to None.

    Returns:
        tuple: (DataFrame of generated data, dict of call_taker names, dict of dispatcher names)
    """
    # Validate locale before proceeding
    if not validate_locale(locale):
        print(f"Warning: Unsupported locale '{locale}'. Falling back to {DEFAULT_LOCALE}")
        locale = DEFAULT_LOCALE

    # Initialize Faker with the specified locale
    local_fake = Faker(locale)

    # Generate address list with the specified locale
    address_list = [local_fake.unique.street_address() for _ in range(2500)]

    # Create street address provider
    street_address_provider = DynamicProvider(
        provider_name="street_address", elements=address_list
    )

    def generate_names(num_names=8):
        """
        Generate a list of random names using the Faker library in "Last, First" format.

        Args:
            num_names (int, optional): Number of names to generate. Defaults to 8.

        Returns:
            list: List of generated names.
        """
        if local_fake is None:
            raise RuntimeError("Faker instance is not initialized.")
        if not hasattr(local_fake, "last_name") or not hasattr(local_fake, "first_name"):
            raise RuntimeError("Faker missing 'last_name' or 'first_name' provider.")
        return [f"{local_fake.last_name()}, {local_fake.first_name()}" for _ in range(num_names)]

    call_taker_names = {key: generate_names(num_names) for key in ["A", "B", "C", "D"]}
    dispatcher_names = {key: generate_names(num_names) for key in ["A", "B", "C", "D"]}

    # Define the probabilities for each agency
    probabilities = [0.72, 0.15, 0.10, 0.03]  # LAW, EMS, FIRE, RESCUE
    agencies = ["LAW", "EMS", "FIRE", "RESCUE"]

    # Filter agencies based on user selection
    filtered_agencies = filter_agencies(agencies, selected_agencies)

    # Handle user-specified probabilities
    if agency_probabilities is not None:
        if len(agency_probabilities) != len(filtered_agencies):
            raise ValueError("Number of agency probabilities must match number of selected agencies.")
        if not np.isclose(sum(agency_probabilities), 1.0):
            raise ValueError("Agency probabilities must sum to 1.")
        probabilities = agency_probabilities
    elif len(filtered_agencies) < len(agencies):
        probabilities = [1.0 / len(filtered_agencies)] * len(filtered_agencies)
    else:
        probabilities = [0.72, 0.15, 0.10, 0.03]

    # Generate the agency column with the specified distribution
    agency_choices = np.random.choice(filtered_agencies, size=num_records, p=probabilities)

    # Map agency to prefix
    agency_prefix = {"LAW": "L", "EMS": "M", "FIRE": "F", "RESCUE": "R"}

    # Set default start and end dates if not provided
    if start_date is None:
        start_date = "2024-01-01"
    if end_date is None:
        end_date = "2024-12-31"

    # Convert start_date and end_date to datetime objects
    start_date_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_date_dt = datetime.strptime(end_date, "%Y-%m-%d")

    # Get the year from start date for call_id prefix
    year_suffix = str(start_date_dt.year)[-2:]

    # Determine starting numbers for each agency
    def get_start_number():
        if start_date_dt.month == 1 and start_date_dt.day == 1:
            return 1
        else:
            # Generate a random starting number between 1000 and 100000
            return random.randint(1000, 100000)

    # Generate sequential numbers for each agency
    agency_counters = {
        "L": get_start_number(),
        "M": get_start_number(),
        "F": get_start_number(),
        "R": get_start_number()
    }
    call_ids_full = []

    for agency in agency_choices:
        prefix = agency_prefix[agency]
        call_id = f"{year_suffix}-{prefix}{agency_counters[prefix]:06d}"
        call_ids_full.append(call_id)
        agency_counters[prefix] += 1

    # Generate random datetimes within the specified range
    date_range = int((end_date_dt - start_date_dt).total_seconds())
    random_seconds = np.random.randint(0, date_range, size=num_records)
    datetimes_full = [
        start_date_dt + timedelta(seconds=int(sec)) for sec in sorted(random_seconds.tolist())
    ]

    # Create DataFrame
    df_full = pl.DataFrame(
        {
            "call_id": call_ids_full,
            "agency": agency_choices,
            "event_time": datetimes_full,
        }
    )

    # Sort the DataFrame by event_time to ensure chronological order
    if not isinstance(df_full, pl.DataFrame):
        raise TypeError("df_full is not a polars DataFrame!")
    df_full = df_full.sort("event_time")

    # Add various time-based columns
    df_full = df_full.with_columns([
        pl.col("event_time").dt.ordinal_day().alias("day_of_year"),
        pl.col("event_time").dt.week().alias("week_no"),
        pl.col("event_time").dt.hour().alias("hour"),
        pl.col("event_time").dt.strftime("%a").str.to_uppercase().alias("dow"),
    ])

    # Add day_night column based on the hour column
    df_full = df_full.with_columns(
        pl.when(pl.col("hour").is_between(6, 17))
        .then(pl.lit("DAY"))
        .otherwise(pl.lit("NIGHT"))
        .alias("day_night")
    )

    # Define the expression to determine the shift
    shift_expr = pl.when(pl.col("week_no") % 2 == 0).then(
        pl.when((pl.col("day_night") == "DAY") & (pl.col("dow").is_in(["MON", "TUE", "FRI", "SAT"]))).then(pl.lit("A"))
        .when((pl.col("day_night") == "NIGHT") & (pl.col("dow").is_in(["MON", "TUE", "FRI", "SAT"]))).then(pl.lit("C"))
        .when((pl.col("day_night") == "DAY") & (pl.col("dow").is_in(["WED", "THU", "SUN"]))).then(pl.lit("B"))
        .when((pl.col("day_night") == "NIGHT") & (pl.col("dow").is_in(["WED", "THU", "SUN"]))).then(pl.lit("D"))
        .otherwise(pl.lit("UNKNOWN"))
    ).otherwise(
        pl.when((pl.col("day_night") == "DAY") & (pl.col("dow").is_in(["WED", "THU", "SUN"]))).then(pl.lit("A"))
        .when((pl.col("day_night") == "NIGHT") & (pl.col("dow").is_in(["WED", "THU", "SUN"]))).then(pl.lit("C"))
        .when((pl.col("day_night") == "DAY") & (pl.col("dow").is_in(["MON", "TUE", "FRI", "SAT"]))).then(pl.lit("B"))
        .when((pl.col("day_night") == "NIGHT") & (pl.col("dow").is_in(["MON", "TUE", "FRI", "SAT"]))).then(pl.lit("D"))
        .otherwise(pl.lit("UNKNOWN"))
    ).alias("shift")

    df_full = df_full.with_columns(shift_expr)

    # Define the function to determine the shift_part
    def determine_shift_part(hour: Any):
        """
        Determine the shift part (EARLY, MIDS, LATE) based on the hour of the day.

        Args:
            hour (Any): The hour component of the event_time. Can be int, float, numpy type, or other.

        Returns:
            str: Descriptor of the shift part.
        """
        # Accept only integer hours in the range 0-23
        try:
            hour = int(hour)
        except Exception as exc:
            raise ValueError(f"Hour value '{hour}' is not an integer.") from exc
        if hour < 0 or hour > 23:
            raise ValueError(f"Hour value '{hour}' is out of valid range (0-23).")
        if hour in (6, 7, 8, 9, 18, 19, 20, 21):
            return "EARLY"
        elif hour in (10, 11, 12, 13, 22, 23, 0, 1):
            return "MIDS"
        else:
            return "LATE"

    # Apply the function to create the shift_part column
    df_full = df_full.with_columns(
        pl.col("hour").map_elements(determine_shift_part, return_dtype=pl.Utf8).alias("shift_part")
    )

    # Assign problem type based on agency
    def assign_problem(agency):
        """
        Assign a problem type based on the agency type using Faker providers.

        Args:
            agency (str): The agency type (LAW, EMS, FIRE, RESCUE).

        Returns:
            str: A random problem type for the agency.
        """
        if local_fake is None:
            raise RuntimeError("Faker instance is not initialized.")
        if agency == "LAW":
            if not hasattr(local_fake, "law_problem"):
                raise RuntimeError("Faker missing 'law_problem' provider.")
            return local_fake.law_problem()
        elif agency == "FIRE":
            if not hasattr(local_fake, "fire_problem"):
                raise RuntimeError("Faker missing 'fire_problem' provider.")
            return local_fake.fire_problem()
        elif agency == "EMS":
            if not hasattr(local_fake, "ems_problem"):
                raise RuntimeError("Faker missing 'ems_problem' provider.")
            return local_fake.ems_problem()
        elif agency == "RESCUE":
            if not hasattr(local_fake, "rescue_problem"):
                raise RuntimeError("Faker missing 'rescue_problem' provider.")
            return local_fake.rescue_problem()
        else:
            return None

    # Register the dynamic providers with Faker
    local_fake.add_provider(law_problem_provider)
    local_fake.add_provider(fire_problem_provider)
    local_fake.add_provider(ems_problem_provider)
    local_fake.add_provider(disposition_provider)
    local_fake.add_provider(rescue_problem_provider)

    df_full = df_full.with_columns(
        pl.col("agency").map_elements(assign_problem, return_dtype=pl.Utf8).alias("problem")
    )

    # Add address column with a street address
    local_fake.add_provider(street_address_provider)
    addresses = [local_fake.street_address() for _ in range(len(df_full))]
    df_full = df_full.with_columns(pl.Series("address", addresses))


    # Create dictionaries to map problems to their priority numbers
    law_priority_map = {problem: priority for problem, priority in LAW_PROBLEMS}
    fire_priority_map = {problem: priority for problem, priority in FIRE_PROBLEMS}
    ems_priority_map = {problem: priority for problem, priority in EMS_PROBLEMS}
    rescue_priority_map = {problem: priority for problem, priority in RESCUE_PROBLEMS}

    # Function to assign priority number based on agency and problem
    priority_expr = (
        pl.when(pl.col("agency") == "LAW").then(pl.col("problem").replace_strict(law_priority_map, default=3))
        .when(pl.col("agency") == "FIRE").then(pl.col("problem").replace_strict(fire_priority_map, default=3))
        .when(pl.col("agency") == "EMS").then(pl.col("problem").replace_strict(ems_priority_map, default=3))
        .when(pl.col("agency") == "RESCUE").then(pl.col("problem").replace_strict(rescue_priority_map, default=3))
        .otherwise(3)
        .alias("priority_number")
    )
    df_full = df_full.with_columns(priority_expr)

    # Define a function to assign call_taker based on shift
    def assign_call_taker(shift):
        """
        Assign a call_taker name based on the shift.

        Args:
            shift (str): The shift label (A, B, C, D).

        Returns:
            str: The name of the call_taker.
        """
        return random.choice(call_taker_names[shift])

    # Apply the function to create the call_taker column
    df_full = df_full.with_columns(
        pl.col("shift").map_elements(assign_call_taker, return_dtype=pl.Utf8).alias("call_taker")
    )

    # Define the probabilities for each call reception method
    probabilities_reception = [0.55, 0.20, 0.10, 0.10, 0.05]

    # Define the call reception categories
    reception_methods = ["E-911", "PHONE", "OFFICER", "TEXT", "C2C"]

    # Generate the call_reception column with the specified distribution
    reception_choices = np.random.choice(
        reception_methods, size=len(df_full), p=probabilities_reception
    )
    df_full = df_full.with_columns(pl.Series("call_reception", reception_choices))


    # Define a function to assign dispatcher based on shift
    def assign_dispatcher(shift):
        """
        Assign a dispatcher name based on the shift.

        Args:
            shift (str): The shift label (A, B, C, D).

        Returns:
            str: The name of the dispatcher.
        """
        return random.choice(dispatcher_names[shift])

    # Apply the function to create the dispatcher column
    df_full = df_full.with_columns(
        pl.col("shift").map_elements(assign_dispatcher, return_dtype=pl.Utf8).alias("dispatcher")
    )

    mu = 3.5
    sigma = 1.2

    # Generate columns with distributions
    queue_time = np.random.lognormal(
        mean=mu, sigma=sigma, size=len(df_full)
    ).astype(int)
    queue_time = (
        queue_time * 200 / queue_time.mean()
    ).astype(int)
    queue_time = np.clip(queue_time, a_min=0, a_max=90)

    dispatch_time = (
        np.random.chisquare(df=5, size=len(df_full)) * 2
    ).astype(int)
    dispatch_time = np.clip(dispatch_time, a_min=5, a_max=600)

    # More varied phone_time using gamma
    num_fast_calls = int(len(df_full) * 0.8)
    num_slow_calls = len(df_full) - num_fast_calls
    fast_calls = np.random.exponential(scale=80, size=num_fast_calls)
    slow_calls = np.random.gamma(shape=2, scale=200, size=num_slow_calls)
    phone_time = np.concatenate([fast_calls, slow_calls]).astype(int)
    np.random.shuffle(phone_time)

    # ack_time describes the time from the first dispatch to the time the unit marks enroute
    ack_time = np.random.gamma(2.0, 30.0, size=len(df_full)).astype(int)
    ack_time = np.clip(ack_time, a_min=2, a_max=40)

    # More varied enroute_time using gamma with different parameters
    enroute_time = np.random.gamma(6.0, 70.0, size=len(df_full)).astype(
        int
    )
    enroute_time = np.clip(enroute_time, a_min=300, a_max=900)

    # More varied on_scene_time using gamma with heavy tail
    on_scene_time = np.random.gamma(3.0, 800.0, size=len(df_full)).astype(
        int
    )
    on_scene_time = np.clip(on_scene_time, a_min=300, a_max=7200)

    df_full = df_full.with_columns([
        pl.Series("queue_time", queue_time),
        pl.Series("dispatch_time", dispatch_time),
        pl.Series("phone_time", phone_time),
        pl.Series("ack_time", ack_time),
        pl.Series("enroute_time", enroute_time),
        pl.Series("on_scene_time", on_scene_time),
    ])


    # Add process_time and total_time columns
    df_full = df_full.with_columns(
        (pl.col("queue_time") + pl.col("dispatch_time")).alias("process_time"),
    ).with_columns(
        (pl.col("process_time") + pl.col("ack_time") + pl.col("enroute_time") + pl.col("on_scene_time")).alias("total_time")
    )

    # Time stamp columns
    df_full = df_full.with_columns(
        (pl.col("event_time") + pl.duration(seconds=pl.col("queue_time"))).alias("time_call_queued"),
        (pl.col("event_time") + pl.duration(seconds=pl.col("phone_time"))).alias("time_call_disconnected"),
    ).with_columns(
        (pl.col("time_call_queued") + pl.duration(seconds=pl.col("dispatch_time"))).alias("time_call_dispatched")
    ).with_columns(
        (pl.col("time_call_dispatched") + pl.duration(seconds=pl.col("ack_time"))).alias("time_call_acknowledged")
    ).with_columns(
        (pl.col("time_call_acknowledged") + pl.duration(seconds=pl.col("enroute_time"))).alias("time_unit_enroute")
    ).with_columns(
        (pl.col("event_time") + pl.duration(seconds=pl.col("total_time"))).alias("time_call_closed")
    )

    nonlaw_dispositions = [d for d in DISPOSITIONS if d != "ARREST MADE"]

    def assign_disposition(agency):
        """
        Assign a disposition based on the agency type.

        Args:
            agency (str): The agency type (LAW, EMS, FIRE, RESCUE).

        Returns:
            str: The disposition for the call.
        """
        if agency == "LAW":
            if local_fake is None or not hasattr(local_fake, "disposition"):
                raise RuntimeError("Faker instance is not initialized or missing 'disposition' provider.")
            return local_fake.disposition()
        else:
            return random.choice(nonlaw_dispositions)

    # Add disposition column with random dispositions
    df_full = df_full.with_columns(
        pl.col("agency").map_elements(assign_disposition, return_dtype=pl.Utf8).alias("disposition")
    )


    # List all your datetime columns
    datetime_cols = [
        "event_time",
        "time_call_queued",
        "time_call_dispatched",
        "time_call_acknowledged",
        "time_call_disconnected",
        "time_unit_enroute",
        "time_call_closed",
    ]

    # Format each datetime column as 'YYYY-MM-DD HH:mm:ss'
    for col in datetime_cols:
        df_full = df_full.with_columns(pl.col(col).dt.strftime("%Y-%m-%d %H:%M:%S"))
        

    return df_full, call_taker_names, dispatcher_names

# Only define DateValidator if Validator is a valid class (not a dummy object or object itself)
if (
    'Validator' in globals()
    and isinstance(Validator, type)
    and Validator is not object
    and Validator.__name__ != "object"
    and issubclass(Validator, object)  # Ensure Validator is a proper class
):
    class DateValidator(Validator):
        """
        Validator for date input in YYYY-MM-DD format for interactive prompts.
        """
        def validate(self, document):
            try:
                datetime.strptime(document.text, '%Y-%m-%d')
            except ValueError as exc:
                raise ValidationError(
                    message='Please enter a valid date in YYYY-MM-DD format',
                    cursor_position=len(document.text)
                ) from exc

def main():
    """
    Main entry point for the script.

    Provides an interactive command line interface (if PyInquirer is available) or a standard CLI for generating 911 dispatch data and saving it to a CSV file. Handles argument parsing, validation, and output summary.
    """

    if PYINQUIRER_AVAILABLE:
        # Interactive mode with PyInquirer
        questions = [
            {
                'type': 'input',
                'name': 'num_records',
                'message': 'How many records would you like to generate?',
                'default': '10000',
                'validate': lambda val: val.isdigit() and int(val) > 0 or 'Please enter a positive number'
            },
            {
                'type': 'input',
                'name': 'start_date',
                'message': 'Enter start date (YYYY-MM-DD):',
                'default': '2024-01-01',
                'validate': DateValidator
            },
            {
                'type': 'input',
                'name': 'end_date',
                'message': 'Enter end date (YYYY-MM-DD):',
                'default': '2024-12-31',
                'validate': DateValidator
            },
            {
                'type': 'input',
                'name': 'num_names',
                'message': 'How many names would you like to generate per shift?',
                'default': '8',
                'validate': lambda val: val.isdigit() and int(val) > 0 or 'Please enter a positive number'
            },
            {
                'type': 'input',
                'name': 'locale',
                'message': 'Enter the Faker locale (e.g., en_US, en_GB, fr_FR, de_DE):',
                'default': DEFAULT_LOCALE
            },
            {
                'type': 'input',
                'name': 'output_file',
                'message': 'Enter the output file path:',
                'default': 'computer_aided_dispatch.csv'
            },
            {
                'type': 'input',
                'name': 'selected_agencies',
                'message': 'Enter agencies to include (comma-separated, e.g., LAW,FIRE):',
                'default': ''
            },
            {
                'type': 'input',
                'name': 'agency_probabilities',
                'message': 'Enter agency probabilities (comma-separated, e.g., 0.7,0.2,0.1):',
                'default': '',
            },
        ]

        if 'prompt' in globals() and callable(prompt):
            answers = prompt(questions)
        else:
            raise RuntimeError("'prompt' is not available even though PyInquirer is installed.")

        num_records = int(answers['num_records'])
        start_date = answers['start_date']
        end_date = answers['end_date']
        num_names = int(answers['num_names'])
        locale = answers['locale']
        output_file = answers['output_file']
        selected_agencies = answers['selected_agencies'].split(',') if answers['selected_agencies'] else None
        agency_probabilities = None
        if answers.get('agency_probabilities') and isinstance(answers['agency_probabilities'], str):
            agency_prob_str = answers['agency_probabilities'].strip()
            if agency_prob_str.upper() == "NEVER":
                agency_probabilities = None
            elif agency_prob_str:  # Only process if not empty
                try:
                    # Only allow if all values are numeric
                    if agency_prob_str.upper() == "NEVER":
                        agency_probabilities = None
                    else:
                        prob_strings = [x.strip() for x in agency_prob_str.split(',')]
                        if not all(re.match(r'^-?\d+(\.\d+)?$', s) for s in prob_strings):
                            raise ValueError
                        agency_probabilities = [float(x) for x in prob_strings]
                except ValueError:
                    print("Invalid agency probabilities format. Must be comma-separated floats.")
                    sys.exit(1)
        elif answers.get('agency_probabilities') and not isinstance(answers['agency_probabilities'], str):
            print("Invalid agency probabilities input. Must be a comma-separated string of numbers.")
            sys.exit(1)
    else:
        # Command-line argument mode
        parser = argparse.ArgumentParser(description="Generate synthetic 911 dispatch data")
        parser.add_argument('-n', '--num-records', type=int, default=10000,
                            help='Number of records to generate (default: 10000)')
        parser.add_argument('-s', '--start-date', type=str, default='2024-01-01',
                            help='Start date in YYYY-MM-DD format (default: 2024-01-01)')
        parser.add_argument('-e', '--end-date', type=str, default='2024-12-31',
                            help='End date in YYYY-MM-DD format (default: 2024-12-31)')
        parser.add_argument('--num-names', type=int, default=8,
                            help='Number of names to generate per shift (default: 8)')
        parser.add_argument('-l', '--locale', type=str, default=DEFAULT_LOCALE,
                            help=f'Faker locale for generating localized data (default: {DEFAULT_LOCALE})')
        parser.add_argument('-o', '--output-file', type=str, default='computer_aided_dispatch.csv',
                            help='Output file path (default: computer_aided_dispatch.csv)')
        parser.add_argument('-a', '--agencies', type=str, default='',
                            help='Comma-separated list of agencies to include (e.g., LAW,FIRE)')
        parser.add_argument('--agency-probabilities', type=str, default='',
                            help='Comma-separated probabilities for selected agencies (e.g., 0.7,0.2,0.1)')

        args = parser.parse_args()

        # Validate dates
        try:
            datetime.strptime(args.start_date, '%Y-%m-%d')
            datetime.strptime(args.end_date, '%Y-%m-%d')
        except ValueError:
            print("Error: Dates must be in YYYY-MM-DD format")
            sys.exit(1)

        num_records = args.num_records
        start_date = args.start_date
        end_date = args.end_date
        num_names = args.num_names
        locale = args.locale
        output_file = args.output_file
        selected_agencies = args.agencies.split(',') if args.agencies else None
        agency_probabilities = None
        if args.agency_probabilities:
            agency_prob_str = args.agency_probabilities.strip()
            if agency_prob_str.upper() == "NEVER":
                agency_probabilities = None
            elif agency_prob_str:  # Only process if not empty
                try:
                    agency_probabilities = [float(x) for x in agency_prob_str.split(',')]
                except ValueError:
                    print("Invalid agency probabilities format. Must be comma-separated floats.")
                    sys.exit(1)

    # Generate data with specified parameters
    df_full, call_taker_names, dispatcher_names = generate_911_data(
        num_records=num_records,
        start_date=start_date,
        end_date=end_date,
        num_names=num_names,
        locale=locale,
        selected_agencies=selected_agencies,
        agency_probabilities=agency_probabilities
    )

    # Save the DataFrame to a CSV file
    df_full.write_csv(output_file)

    print(f"\nCSV file saved to {output_file}")
    print(f"Total records generated: {len(df_full)}")

    # Quick summary statistics of the new columns
    print("\nSummary Statistics for New Columns:")
    print(df_full.select(["phone_time", "process_time", "total_time"]).describe())

    print("\nCall Taker Names per Shift:")
    for shift, names in call_taker_names.items():
        print(f"Shift {shift}: {names}")

    print("\nDispatcher Names per Shift:")
    for shift, names in dispatcher_names.items():
        print(f"Shift {shift}: {names}")

if __name__ == "__main__":
    main()