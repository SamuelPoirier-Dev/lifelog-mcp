"""Québec time, UTC storage, periods, ISO weeks and days without entry."""

from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from lifelog.timeutils import (
    Period,
    counted_days,
    days_without_entry,
    iso_week_label,
    local_date,
    to_utc,
    week_start,
)


def test_naive_time_is_quebec_time():
    # November 3rd, after the switch to standard time (UTC-5).
    assert to_utc(datetime(2026, 11, 3, 0, 30)) == datetime(2026, 11, 3, 5, 30, tzinfo=UTC)


def test_aware_time_is_converted_to_utc():
    paris = timezone(timedelta(hours=1))
    assert to_utc(datetime(2026, 11, 3, 12, 0, tzinfo=paris)) == datetime(
        2026, 11, 3, 11, 0, tzinfo=UTC
    )


def test_half_past_midnight_belongs_to_the_next_day():
    # 05:30 UTC = 00:30 on November 3rd in Québec; 04:59 UTC = 23:59 on November 2nd.
    assert local_date(datetime(2026, 11, 3, 5, 30, tzinfo=UTC)) == date(2026, 11, 3)
    assert local_date(datetime(2026, 11, 3, 4, 59, tzinfo=UTC)) == date(2026, 11, 2)


@pytest.mark.parametrize(
    ("day", "hours"),
    [
        (date(2026, 3, 8), 23),  # daylight saving time starts: a 23-hour day
        (date(2026, 11, 1), 25),  # daylight saving time ends: a 25-hour day
        (date(2026, 11, 2), 24),
    ],
)
def test_period_bounds_follow_daylight_saving_time(day: date, hours: int):
    start, end = Period(day, day).utc_bounds()
    assert end - start == timedelta(hours=hours)


def test_week_runs_monday_to_sunday():
    period = Period.week_of(date(2026, 11, 5))  # a Thursday
    assert (period.start, period.end) == (date(2026, 11, 2), date(2026, 11, 8))


@pytest.mark.parametrize(
    ("day", "label"),
    [
        (date(2026, 11, 5), "2026-W45"),
        (date(2027, 1, 1), "2026-W53"),  # a Friday: still the last week of 2026
        (date(2027, 1, 4), "2027-W01"),
    ],
)
def test_iso_week_label(day: date, label: str):
    assert iso_week_label(day) == label


def test_week_start_across_years():
    assert week_start(date(2027, 1, 1)) == date(2026, 12, 28)


class TestResolvePeriod:
    today = date(2026, 11, 5)

    def test_defaults_to_the_current_week(self):
        assert Period.resolve(None, None, self.today) == Period(
            date(2026, 11, 2), date(2026, 11, 8)
        )

    def test_start_only_runs_until_today(self):
        assert Period.resolve(date(2026, 10, 1), None, self.today) == Period(
            date(2026, 10, 1), self.today
        )

    def test_end_only_is_refused(self):
        with pytest.raises(ValueError, match="needs a start"):
            Period.resolve(None, date(2026, 10, 1), self.today)

    def test_start_after_end_is_refused(self):
        with pytest.raises(ValueError, match="must not be after"):
            Period.resolve(date(2026, 11, 10), date(2026, 11, 1), self.today)


def test_week_starts_cover_partial_weeks():
    period = Period(date(2026, 10, 28), date(2026, 11, 3))  # Wednesday to next Tuesday
    assert list(period.week_starts()) == [date(2026, 10, 26), date(2026, 11, 2)]


def test_future_days_are_not_counted():
    period = Period(date(2026, 11, 2), date(2026, 11, 8))
    assert counted_days(period, today=date(2026, 11, 4)) == [
        date(2026, 11, 2),
        date(2026, 11, 3),
        date(2026, 11, 4),
    ]


def test_days_without_entry():
    period = Period(date(2026, 11, 2), date(2026, 11, 8))
    entry_days = {date(2026, 11, 3), date(2026, 11, 7)}  # the 7th is after today
    assert days_without_entry(period, entry_days, today=date(2026, 11, 5)) == 3


def test_period_entirely_in_the_future_counts_no_day():
    period = Period(date(2026, 12, 1), date(2026, 12, 7))
    assert days_without_entry(period, set(), today=date(2026, 11, 5)) == 0
