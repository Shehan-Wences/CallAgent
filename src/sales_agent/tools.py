from __future__ import annotations
from datetime import datetime, timezone
from typing import Callable
from agents import function_tool
from .booking import BookingStore

Clock = Callable[[], str]

def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

def record_booking(store: BookingStore, now: Clock, *, lead_name: str,
                  contact: str, preferred_time: str, notes: str = "") -> str:
    store.append({
        "record_type": "booking",
        "timestamp": now(),
        "lead_name": lead_name,
        "contact": contact,
        "preferred_time": preferred_time,
        "notes": notes,
    })
    return f"Booked a follow-up for {lead_name or 'the lead'} at {preferred_time}."

def record_outcome(store: BookingStore, now: Clock, *, status: str, notes: str = "") -> str:
    store.append({
        "record_type": "outcome",
        "timestamp": now(),
        "status": status,
        "notes": notes,
    })
    return "Outcome recorded."

def build_tools(store: BookingStore, now: Clock = _utc_now) -> list:
    @function_tool
    def book_slot(lead_name: str, contact: str, preferred_time: str, notes: str = "") -> str:
        """Book a follow-up call/demo. Use when the person agrees to a follow-up.

        Args:
            lead_name: The person's name.
            contact: Their phone number or email for the follow-up.
            preferred_time: The date/time they asked for, in their own words.
            notes: Any short note about what they want.
        """
        return record_booking(store, now, lead_name=lead_name, contact=contact,
                             preferred_time=preferred_time, notes=notes)

    @function_tool
    def log_outcome(status: str, notes: str = "") -> str:
        """Record how the call ended. Call this before the call ends, every time.

        Args:
            status: One of booked, interested, not_interested, callback_requested, no_answer.
            notes: One-line summary of the call outcome.
        """
        return record_outcome(store, now, status=status, notes=notes)

    return [book_slot, log_outcome]
