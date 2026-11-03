"""Time helpers: days and weeks are in Québec time, everything stored is UTC.

- A time without a time zone is Québec time (D8).
- A day is a calendar day in Québec, midnight to midnight (D5).
- Weeks are ISO weeks, Monday to Sunday (D5).
"""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

# Québec time. The IANA time zone database has no "America/Quebec": Québec City uses
# the Eastern zone, whose reference city is Toronto (D47).
LOCAL_TZ = ZoneInfo("America/Toronto")


def to_utc(moment: datetime) -> datetime:
    """Convert to UTC; a naive datetime is read as Québec time."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=LOCAL_TZ)
    return moment.astimezone(UTC)


def local_date(moment: datetime) -> date:
    """Calendar day in Québec of a moment (naive = Québec time)."""
    return to_utc(moment).astimezone(LOCAL_TZ).date()


def local_today(now: datetime | None = None) -> date:
    """Today in Québec (`now` lets tests fix the clock)."""
    return local_date(now or datetime.now(UTC))


def start_of_day_utc(day: date) -> datetime:
    """Midnight in Québec at the start of `day`, in UTC (handles daylight saving time)."""
    return datetime.combine(day, time.min, tzinfo=LOCAL_TZ).astimezone(UTC)


def week_start(day: date) -> date:
    """Monday of the ISO week containing `day`."""
    return day - timedelta(days=day.weekday())


def iso_week_label(day: date) -> str:
    """ISO week of `day`, e.g. "2026-W45". The ISO year can differ from the calendar year."""
    year, week, _ = day.isocalendar()
    return f"{year}-W{week:02d}"


@dataclass(frozen=True)
class Period:
    """Inclusive range of Québec calendar days."""

    start: date
    end: date

    def __post_init__(self) -> None:
        if self.start > self.end:
            raise ValueError(f"start ({self.start}) must not be after end ({self.end})")

    @classmethod
    def week_of(cls, day: date) -> "Period":
        """The ISO week (Monday to Sunday) containing `day`."""
        monday = week_start(day)
        return cls(monday, monday + timedelta(days=6))

    @classmethod
    def resolve(cls, start: date | None, end: date | None, today: date) -> "Period":
        """Build a period from optional bounds (D7, D44).

        - neither: the current ISO week;
        - start only: from start to today;
        - end only: refused, since the start would be a guess.
        """
        if start is None and end is None:
            return cls.week_of(today)
        if start is None:
            raise ValueError("an end date needs a start date")
        return cls(start, end if end is not None else today)

    def days(self) -> Iterator[date]:
        day = self.start
        while day <= self.end:
            yield day
            day += timedelta(days=1)

    def contains(self, moment: datetime) -> bool:
        return self.start <= local_date(moment) <= self.end

    def utc_bounds(self) -> tuple[datetime, datetime]:
        """[start, end) in UTC: Québec midnight of the first day to that of the day after."""
        return start_of_day_utc(self.start), start_of_day_utc(self.end + timedelta(days=1))

    def week_starts(self) -> Iterator[date]:
        """Monday of every ISO week overlapping the period."""
        monday = week_start(self.start)
        while monday <= self.end:
            yield monday
            monday += timedelta(days=7)


def counted_days(period: Period, today: date) -> list[date]:
    """Days of the period up to today included: future days do not count (D6)."""
    return [day for day in period.days() if day <= today]


def days_without_entry(period: Period, entry_days: set[date], today: date) -> int:
    """Number of days of the period, up to today, with no entry at all (D6)."""
    return sum(1 for day in counted_days(period, today) if day not in entry_days)
