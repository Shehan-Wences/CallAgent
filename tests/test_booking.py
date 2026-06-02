import json
from sales_agent.booking import BookingStore

def test_append_creates_file_with_list(tmp_path):
    store = BookingStore(tmp_path / "bookings.json")
    store.append({"record_type": "booking", "lead_name": "Dana"})
    data = json.loads((tmp_path / "bookings.json").read_text())
    assert data == [{"record_type": "booking", "lead_name": "Dana"}]

def test_append_is_additive(tmp_path):
    store = BookingStore(tmp_path / "bookings.json")
    store.append({"record_type": "booking", "lead_name": "Dana"})
    store.append({"record_type": "outcome", "status": "booked"})
    data = json.loads((tmp_path / "bookings.json").read_text())
    assert len(data) == 2
    assert data[1]["status"] == "booked"

def test_creates_parent_dirs(tmp_path):
    store = BookingStore(tmp_path / "nested" / "dir" / "bookings.json")
    store.append({"record_type": "outcome", "status": "no_answer"})
    assert (tmp_path / "nested" / "dir" / "bookings.json").exists()
