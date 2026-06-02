import json
from sales_agent.booking import BookingStore
from sales_agent.tools import record_booking, record_outcome, build_tools

def _store(tmp_path):
    return BookingStore(tmp_path / "bookings.json")

def test_record_booking_writes_record_and_confirms(tmp_path):
    store = _store(tmp_path)
    msg = record_booking(store, lambda: "2026-06-02T10:00:00Z",
                         lead_name="Dana", contact="dana@x.com",
                         preferred_time="Tue 3pm", notes="keen")
    data = json.loads((tmp_path / "bookings.json").read_text())
    assert data[0]["record_type"] == "booking"
    assert data[0]["lead_name"] == "Dana"
    assert data[0]["preferred_time"] == "Tue 3pm"
    assert data[0]["timestamp"] == "2026-06-02T10:00:00Z"
    assert "Tue 3pm" in msg

def test_record_outcome_writes_status(tmp_path):
    store = _store(tmp_path)
    record_outcome(store, lambda: "2026-06-02T10:05:00Z",
                  status="booked", notes="done")
    data = json.loads((tmp_path / "bookings.json").read_text())
    assert data[0]["record_type"] == "outcome"
    assert data[0]["status"] == "booked"
    assert data[0]["timestamp"] == "2026-06-02T10:05:00Z"

def test_build_tools_returns_two_named_tools(tmp_path):
    tools = build_tools(_store(tmp_path), lambda: "t")
    names = {t.name for t in tools}
    assert names == {"book_slot", "log_outcome"}
