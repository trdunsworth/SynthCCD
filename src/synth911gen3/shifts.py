"""Shift structures for personnel assignment.

Models how a 9-1-1 center staffs its calltakers and dispatchers over
time: :class:`Shift` is one scheduled work block, :class:`ShiftConfig` is
a full structure combining a crew rotation pattern with the shifts on the
clock. The generator uses :meth:`ShiftConfig.active_shift` to decide which
shift handled each call, which drives the calltaker/dispatcher pools and
the late-shift dispatch penalty.

Built-in presets cover the common center layouts: 2x12h with a 14-day
crew rotation (default), 2x12h, 3x8h, and 4x10h. Custom structures can be
defined through the realism config ``shift_config`` section.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from .exceptions import ValidationError

DEFAULT_SHIFT_PRESET = "2x12h-4shift-14day"

_EPOCH_MONDAY = date(1970, 1, 5)
_MINUTES_PER_DAY = 24 * 60

# 2x12h center pattern: 1 = one crew pairing, 2 = the other. Repeats every
# 14 days (2 weeks) starting Monday: 1,1,2,2,1,1,1,2,2,1,1,2,2,2.
DEFAULT_ROTATION = [1, 1, 2, 2, 1, 1, 1, 2, 2, 1, 1, 2, 2, 2]


@dataclass(frozen=True, slots=True)
class Shift:
    """A single scheduled work block within a shift structure.

    ``start_hour``/``end_hour`` use 24-hour clock hours; an end time earlier
    than the start time indicates a shift that spans midnight. ``rotation`` is
    the crew-group id a shift belongs to so multiple crews can cycle across a
    repeating pattern (e.g. group 1 day + group 1 night). ``calltakers`` and
    ``dispatchers`` are the number of staffed positions on this shift; ``None``
    defers to the generation request's global pool totals.
    """

    name: str
    label: str = "DAY"
    start_hour: int = 6
    start_minute: int = 0
    end_hour: int = 18
    end_minute: int = 0
    rotation: int = 1
    calltakers: int | None = None
    dispatchers: int | None = None

    @property
    def is_overnight(self) -> bool:
        """True when this shift crosses midnight (end time precedes start)."""
        return self._start_minutes() >= self._end_minutes()

    def _start_minutes(self) -> int:
        """Start time as minutes since midnight."""
        return self.start_hour * 60 + self.start_minute

    def _end_minutes(self) -> int:
        """End time as minutes since midnight (before a midnight wrap)."""
        return self.end_hour * 60 + self.end_minute

    def covers(self, moment: datetime) -> bool:
        """Return True if this shift is on duty at ``moment``."""
        t = moment.hour * 60 + moment.minute
        start = self._start_minutes()
        end = self._end_minutes()
        if start < end:
            return start <= t < end
        return t >= start or t < end

    def minutes_since_start(self, moment: datetime) -> int:
        """Minutes elapsed since this shift most recently started."""
        delta = moment.hour * 60 + moment.minute - self._start_minutes()
        return delta if delta >= 0 else delta + _MINUTES_PER_DAY


def _anchor(cycle_start_weekday: int) -> date:
    """First date at or after the epoch that falls on ``cycle_start_weekday``."""
    offset = (cycle_start_weekday - _EPOCH_MONDAY.weekday()) % 7
    return _EPOCH_MONDAY + timedelta(days=offset)


@dataclass(slots=True)
class ShiftConfig:
    """A full shift structure: crew rotations plus the shifts on the clock.

    ``rotation`` is a repeating sequence of crew-group ids, one per calendar
    day. For a given day the active crew group is
    ``rotation[days_since_cycle_start % len(rotation)]`` and the active shift is
    the one in that group whose time window covers the call.
    """

    name: str = "custom"
    shifts: list[Shift] = field(default_factory=list)
    rotation: list[int] = field(default_factory=list)
    cycle_start_weekday: int = 0

    def active_shift(self, moment: datetime) -> Shift:
        """Return the shift on duty at ``moment`` for the active crew group.

        Picks the group scheduled for that calendar day from the rotation,
        then the covering shift with the most recent start; falls back to
        the group's earliest-started shift when no shift window covers the
        moment (e.g. a gap between shifts).
        """
        if not self.shifts:
            raise ValidationError("shift_config has no shifts defined.")
        if not self.rotation:
            raise ValidationError("shift_config has no rotation pattern defined.")
        index = (moment.date() - _anchor(self.cycle_start_weekday)).days % len(self.rotation)
        pairing = self.rotation[index]
        candidates = [shift for shift in self.shifts if shift.rotation == pairing]
        covering = [shift for shift in candidates if shift.covers(moment)]
        if covering:
            return min(covering, key=lambda shift: shift.minutes_since_start(moment))
        if candidates:
            return min(candidates, key=lambda shift: shift.minutes_since_start(moment))
        raise ValidationError(
            f"No shift in rotation group {pairing} is scheduled at {moment:%H:%M}."
        )

    def total_calltakers(self) -> int:
        """Sum of per-shift calltaker staffing (ignores shifts with ``None``)."""
        return sum(shift.calltakers for shift in self.shifts if shift.calltakers is not None)

    def total_dispatchers(self) -> int:
        """Sum of per-shift dispatcher staffing (ignores shifts with ``None``)."""
        return sum(shift.dispatchers for shift in self.shifts if shift.dispatchers is not None)

    def rotation_cycle_offset(self) -> int:
        """Days between the epoch (1970-01-01) and the cycle's day-0 anchor date.

        Used to compute a rotation group id for a day given as days-since-epoch.
        """
        return (_anchor(self.cycle_start_weekday) - date(1970, 1, 1)).days

    def validate(self) -> None:
        """Validate the structure: non-empty shifts/rotation, 24h coverage per group.

        Raises:
            ValidationError: On empty or inconsistent structures, including
                duplicate shift names, unknown rotation groups, negative
                staffing, or groups that do not cover all 24 hours.
        """
        if not self.shifts:
            raise ValidationError("shift_config.shifts must define at least one shift.")
        if not self.rotation:
            raise ValidationError("shift_config.rotation must not be empty.")
        if any(value <= 0 for value in self.rotation):
            raise ValidationError("shift_config.rotation values must be positive.")
        if not (0 <= self.cycle_start_weekday <= 6):
            raise ValidationError("shift_config.cycle_start_weekday must be between 0 and 6.")

        names = [shift.name for shift in self.shifts]
        if len(names) != len(set(names)):
            raise ValidationError("shift_config.shifts must use unique shift names.")

        for shift in self.shifts:
            if shift.calltakers is not None and shift.calltakers < 0:
                raise ValidationError(f"shift {shift.name} calltakers must be non-negative.")
            if shift.dispatchers is not None and shift.dispatchers < 0:
                raise ValidationError(f"shift {shift.name} dispatchers must be non-negative.")

        for pairing in set(self.rotation):
            group = [shift for shift in self.shifts if shift.rotation == pairing]
            if not group:
                raise ValidationError(
                    f"shift_config.shifts missing a shift for rotation group {pairing}."
                )
            if not _covers_full_day(group):
                raise ValidationError(
                    f"Shifts in rotation group {pairing} do not cover all 24 hours."
                )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict for YAML/JSON round-tripping."""
        shifts = []
        for shift in self.shifts:
            entry: dict[str, Any] = {
                "name": shift.name,
                "label": shift.label,
                "start_hour": shift.start_hour,
                "start_minute": shift.start_minute,
                "end_hour": shift.end_hour,
                "end_minute": shift.end_minute,
                "rotation": shift.rotation,
            }
            if shift.calltakers is not None:
                entry["calltakers"] = shift.calltakers
            if shift.dispatchers is not None:
                entry["dispatchers"] = shift.dispatchers
            shifts.append(entry)
        return {
            "name": self.name,
            "cycle_start_weekday": self.cycle_start_weekday,
            "rotation": self.rotation,
            "shifts": shifts,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ShiftConfig:
        """Build a ShiftConfig from a plain dict (YAML ``shift_config`` section)."""
        shifts = [
            Shift(
                name=str(item["name"]),
                label=str(item.get("label", "DAY")),
                start_hour=int(item.get("start_hour", 6)),
                start_minute=int(item.get("start_minute", 0)),
                end_hour=int(item.get("end_hour", 18)),
                end_minute=int(item.get("end_minute", 0)),
                rotation=int(item.get("rotation", 1)),
                calltakers=item.get("calltakers"),
                dispatchers=item.get("dispatchers"),
            )
            for item in data.get("shifts", [])
        ]
        return cls(
            name=str(data.get("name", "custom")),
            shifts=shifts,
            rotation=[int(value) for value in data.get("rotation", [])],
            cycle_start_weekday=int(data.get("cycle_start_weekday", 0)),
        )


def _covers_full_day(shifts: list[Shift]) -> bool:
    """True when the given shifts together cover every minute of the day."""
    covered = [False] * _MINUTES_PER_DAY
    for shift in shifts:
        start = shift._start_minutes()
        end = shift._end_minutes()
        if start < end:
            for minute in range(start, end):
                covered[minute] = True
        else:
            for minute in range(start, _MINUTES_PER_DAY):
                covered[minute] = True
            for minute in range(0, end):
                covered[minute] = True
    return all(covered)


def _shift(name: str, label: str, start: int, end: int, rotation: int) -> Shift:
    """Build a preset shift with the standard 3-calltaker / 2-dispatcher staffing."""
    return Shift(
        name=name,
        label=label,
        start_hour=start,
        end_hour=end,
        rotation=rotation,
        calltakers=3,
        dispatchers=2,
    )


def preset_4shift_14day() -> ShiftConfig:
    """2x12h, four shifts (A/B day, C/D night), 14-day crew rotation."""
    return ShiftConfig(
        name="2x12h-4shift-14day",
        rotation=DEFAULT_ROTATION.copy(),
        cycle_start_weekday=0,
        shifts=[
            _shift("A", "DAY", 6, 18, 1),
            _shift("B", "DAY", 6, 18, 2),
            _shift("C", "NIGHT", 18, 6, 1),
            _shift("D", "NIGHT", 18, 6, 2),
        ],
    )


def preset_2shift_12h() -> ShiftConfig:
    """2x12h, single day and single night shift (no crew cycling)."""
    return ShiftConfig(
        name="2x12h-2shift",
        rotation=[1],
        cycle_start_weekday=0,
        shifts=[
            _shift("A", "DAY", 6, 18, 1),
            _shift("C", "NIGHT", 18, 6, 1),
        ],
    )


def preset_3shift_8h() -> ShiftConfig:
    """3x8h shifts: Morning, Swing, and Midnight."""
    return ShiftConfig(
        name="3x8h-3shift",
        rotation=[1],
        cycle_start_weekday=0,
        shifts=[
            _shift("A", "MORNING", 6, 14, 1),
            _shift("B", "SWING", 14, 22, 1),
            _shift("C", "NIGHT", 22, 6, 1),
        ],
    )


def preset_4shift_10h() -> ShiftConfig:
    """4x10h shifts: Day, Coverage, Evening, and Night with peak overlap."""
    return ShiftConfig(
        name="4x10h-4shift",
        rotation=[1],
        cycle_start_weekday=0,
        shifts=[
            _shift("A", "DAY", 6, 16, 1),
            _shift("B", "COVERAGE", 10, 21, 1),
            _shift("C", "EVENING", 16, 2, 1),
            _shift("D", "NIGHT", 21, 7, 1),
        ],
    )


SHIFT_PRESETS: dict[str, str] = {
    "2x12h-4shift-14day": "2x12h, four shifts (A/B day, C/D night), 14-day crew rotation",
    "2x12h-2shift": "2x12h, single day and single night shift",
    "3x8h-3shift": "3x8h, Morning / Swing / Midnight",
    "4x10h-4shift": "4x10h, Day / Coverage / Evening / Night",
}

_PRESET_FACTORIES: dict[str, Callable[[], ShiftConfig]] = {
    "2x12h-4shift-14day": preset_4shift_14day,
    "2x12h-2shift": preset_2shift_12h,
    "3x8h-3shift": preset_3shift_8h,
    "4x10h-4shift": preset_4shift_10h,
}


def get_default_shift_config() -> ShiftConfig:
    """Return the default 2x12h-4shift-14day structure (fresh instance each call)."""
    return preset_4shift_14day()


def get_preset(name: str) -> ShiftConfig:
    """Build the named preset; raises for unknown names."""
    factory = _PRESET_FACTORIES.get(name)
    if factory is None:
        available = ", ".join(sorted(_PRESET_FACTORIES))
        raise ValidationError(f"Unknown shift preset {name!r}. Available presets: {available}.")
    return factory()


def apply_shift_preset(shift_config: ShiftConfig, preset_name: str | None) -> ShiftConfig:
    """Replace ``shift_config`` with the named preset, or return it unchanged."""
    if preset_name is None:
        return shift_config
    return get_preset(preset_name)
