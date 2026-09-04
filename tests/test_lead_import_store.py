from app.storage.lead_import_store import LeadImportStore


def test_record_assigns_id_and_round_trips(tmp_path):
    store = LeadImportStore(str(tmp_path / "leads.db"))

    batch = store.record(filename="leads.csv", imported_count=3, skipped=[{"row": 4, "reason": "Missing name"}])

    assert batch.id.startswith("import-")
    assert batch.filename == "leads.csv"
    assert batch.imported_count == 3
    assert batch.total_rows == 4
    assert batch.failed_count == 1
    assert batch.status == "error"


def test_record_with_no_skips_has_success_status(tmp_path):
    store = LeadImportStore(str(tmp_path / "leads.db"))

    batch = store.record(filename="leads.csv", imported_count=5, skipped=[])

    assert batch.status == "success"
    assert batch.failed_count == 0
    assert batch.total_rows == 5


def test_list_orders_newest_first(tmp_path):
    store = LeadImportStore(str(tmp_path / "leads.db"))
    store.record(filename="first.csv", imported_count=1, skipped=[])
    store.record(filename="second.csv", imported_count=1, skipped=[])
    store.record(filename="third.csv", imported_count=1, skipped=[])

    filenames = [b.filename for b in store.list()]

    assert filenames == ["third.csv", "second.csv", "first.csv"]


def test_list_respects_limit(tmp_path):
    store = LeadImportStore(str(tmp_path / "leads.db"))
    for i in range(5):
        store.record(filename=f"{i}.csv", imported_count=1, skipped=[])

    assert len(store.list(limit=2)) == 2


def test_get_returns_batch_by_id(tmp_path):
    store = LeadImportStore(str(tmp_path / "leads.db"))
    batch = store.record(filename="leads.csv", imported_count=2, skipped=[{"row": 3, "reason": "Missing name"}])

    fetched = store.get(batch.id)

    assert fetched.filename == "leads.csv"
    assert fetched.skipped == [{"row": 3, "reason": "Missing name"}]


def test_get_missing_id_returns_none(tmp_path):
    store = LeadImportStore(str(tmp_path / "leads.db"))
    assert store.get("does-not-exist") is None
