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

def test_corrupt_json_file_is_reset(tmp_path):
    path = tmp_path / "bookings.json"
    path.write_text("{ this is not valid json")
    store = BookingStore(path)
    store.append({"record_type": "outcome", "status": "booked"})
    data = json.loads(path.read_text())
    assert data == [{"record_type": "outcome", "status": "booked"}]

def test_non_list_json_file_is_reset(tmp_path):
    path = tmp_path / "bookings.json"
    path.write_text('{"some": "object"}')   # valid JSON but not a list
    store = BookingStore(path)
    store.append({"record_type": "booking", "lead_name": "Dana"})
    data = json.loads(path.read_text())
    assert data == [{"record_type": "booking", "lead_name": "Dana"}]
