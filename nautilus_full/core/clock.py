"""
Clock implementations.

TestClock  — deterministic clock for backtesting (manually advanced).
LiveClock  — real-time clock using time.time_ns().

All timestamps are nanoseconds since UNIX epoch (int).
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass(order=True)
class TimeEvent:
    """A time event fired when the clock reaches a registered alarm time."""
    ts_event: int                        # nanoseconds
    name: str = field(compare=False)
    event_id: str = field(compare=False)
    callback: Optional[Callable] = field(default=None, compare=False)

    def __post_init__(self) -> None:
        if not self.event_id:
            self.event_id = str(uuid.uuid4())


@dataclass(order=True)
class _Timer:
    fire_at: int          # nanoseconds timestamp
    name: str = field(compare=False)
    callback: Optional[Callable] = field(default=None, compare=False)
    interval_ns: int = field(default=0, compare=False)  # 0 = one-shot
    repeat: bool = field(default=False, compare=False)


class Clock:
    """Abstract base clock."""

    def timestamp_ns(self) -> int:
        raise NotImplementedError

    def timestamp(self) -> float:
        return self.timestamp_ns() / 1e9

    def utc_now(self):
        import datetime
        return datetime.datetime.utcfromtimestamp(self.timestamp())


class TestClock(Clock):
    """
    Deterministic simulation clock.

    Time only advances when ``set_time()`` or ``advance_time()`` is called.
    Registered timers and alarms fire when the clock passes their target time.
    """

    def __init__(self, start_ns: int = 0) -> None:
        self._time_ns: int = start_ns
        self._timers: list[_Timer] = []  # sorted by fire_at

    # ── Time queries ───────────────────────────────────────────────────────

    def timestamp_ns(self) -> int:
        return self._time_ns

    # ── Time control ───────────────────────────────────────────────────────

    def set_time(self, ts_ns: int) -> None:
        """Directly set the clock to ``ts_ns`` (no events fired)."""
        self._time_ns = ts_ns

    def advance_time(self, ts_ns: int) -> list[TimeEvent]:
        """
        Advance the clock to ``ts_ns``, firing all timers that fall in
        the interval ``(current_time, ts_ns]``.

        Returns the list of fired TimeEvent objects in chronological order.
        """
        events: list[TimeEvent] = []
        to_remove: list[_Timer] = []
        to_add: list[_Timer] = []

        for timer in sorted(self._timers):
            if timer.fire_at <= ts_ns:
                te = TimeEvent(
                    ts_event=timer.fire_at,
                    name=timer.name,
                    event_id=str(uuid.uuid4()),
                    callback=timer.callback,
                )
                events.append(te)
                if timer.callback:
                    timer.callback(te)

                if timer.repeat and timer.interval_ns > 0:
                    # Reschedule
                    new_timer = _Timer(
                        fire_at=timer.fire_at + timer.interval_ns,
                        name=timer.name,
                        callback=timer.callback,
                        interval_ns=timer.interval_ns,
                        repeat=True,
                    )
                    to_add.append(new_timer)

                to_remove.append(timer)

        for t in to_remove:
            self._timers.remove(t)
        self._timers.extend(to_add)

        self._time_ns = ts_ns
        return sorted(events)

    # ── Timer registration ─────────────────────────────────────────────────

    def set_time_alert(
        self,
        name: str,
        alert_time_ns: int,
        callback: Optional[Callable] = None,
    ) -> None:
        """Register a one-shot alarm at ``alert_time_ns``."""
        self._timers.append(_Timer(
            fire_at=alert_time_ns,
            name=name,
            callback=callback,
            repeat=False,
        ))

    def set_timer(
        self,
        name: str,
        interval_ns: int,
        start_ns: Optional[int] = None,
        callback: Optional[Callable] = None,
        repeat: bool = True,
    ) -> None:
        """Register a repeating timer firing every ``interval_ns`` ns."""
        start = start_ns if start_ns is not None else self._time_ns + interval_ns
        self._timers.append(_Timer(
            fire_at=start,
            name=name,
            callback=callback,
            interval_ns=interval_ns,
            repeat=repeat,
        ))

    def cancel_timer(self, name: str) -> None:
        self._timers = [t for t in self._timers if t.name != name]

    def cancel_all_timers(self) -> None:
        self._timers.clear()

    @property
    def timer_names(self) -> list[str]:
        return [t.name for t in self._timers]


class LiveClock(Clock):
    """
    Real-time clock backed by ``time.time_ns()``.
    Timers are not supported in the backtesting context.
    """

    def timestamp_ns(self) -> int:
        return time.time_ns()
