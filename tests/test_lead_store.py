from app.storage.lead_store import LeadStore


def test_create_assigns_id_and_round_trips(tmp_path):
    store = LeadStore(str(tmp_path / "leads.db"))

    lead = store.create(name="Asha Rao", phone="9876543210", email="asha@example.com", organization="Acme Corp", remarks="Met at conference")

    assert lead.id.startswith("lead-")
    listed = store.list()
    assert len(listed) == 1
    assert listed[0].name == "Asha Rao"
    assert listed[0].organization == "Acme Corp"


def test_create_defaults_optional_fields_to_empty_string(tmp_path):
    store = LeadStore(str(tmp_path / "leads.db"))

    lead = store.create(name="Just A Name")

    assert lead.phone == ""
    assert lead.email == ""
    assert lead.organization == ""
    assert lead.remarks == ""


def test_list_orders_newest_first(tmp_path):
    store = LeadStore(str(tmp_path / "leads.db"))
    store.create(name="First")
    store.create(name="Second")
    store.create(name="Third")

    names = [l.name for l in store.list()]

    assert names == ["Third", "Second", "First"]


def test_list_search_matches_name_case_insensitive_substring(tmp_path):
    store = LeadStore(str(tmp_path / "leads.db"))
    store.create(name="Asha Rao")
    store.create(name="Vikram Singh")

    results = store.list(search="asha")

    assert [l.name for l in results] == ["Asha Rao"]


def test_list_search_matches_organization_substring(tmp_path):
    store = LeadStore(str(tmp_path / "leads.db"))
    store.create(name="Asha Rao", organization="Acme Corp")
    store.create(name="Vikram Singh", organization="Globex Inc")

    results = store.list(search="acme")

    assert [l.name for l in results] == ["Asha Rao"]


def test_list_search_matches_phone_substring(tmp_path):
    store = LeadStore(str(tmp_path / "leads.db"))
    store.create(name="Asha Rao", phone="9876543210")
    store.create(name="Vikram Singh", phone="9900112233")

    results = store.list(search="98765")

    assert [l.name for l in results] == ["Asha Rao"]


def test_list_search_matches_remarks_substring(tmp_path):
    store = LeadStore(str(tmp_path / "leads.db"))
    store.create(name="Asha Rao", remarks="Referred by Vikram Singh")
    store.create(name="Neha Kapoor", remarks="Downloaded the brochure")

    results = store.list(search="referred")

    assert [l.name for l in results] == ["Asha Rao"]


def test_list_search_matches_email_substring(tmp_path):
    store = LeadStore(str(tmp_path / "leads.db"))
    store.create(name="Asha Rao", email="asha@acmecorp.com")
    store.create(name="Vikram Singh", email="vikram@globex.com")

    results = store.list(search="acmecorp")

    assert [l.name for l in results] == ["Asha Rao"]


def test_list_search_matching_multiple_fields_does_not_duplicate_rows(tmp_path):
    store = LeadStore(str(tmp_path / "leads.db"))
    store.create(name="Acme Rao", organization="Acme Corp")

    results = store.list(search="acme")

    assert len(results) == 1


def test_get_returns_lead_by_id(tmp_path):
    store = LeadStore(str(tmp_path / "leads.db"))
    lead = store.create(name="Asha Rao", organization="Acme Corp")

    fetched = store.get(lead.id)

    assert fetched.name == "Asha Rao"
    assert fetched.organization == "Acme Corp"


def test_get_missing_id_returns_none(tmp_path):
    store = LeadStore(str(tmp_path / "leads.db"))
    assert store.get("does-not-exist") is None


def test_update_overwrites_fields_and_returns_updated_lead(tmp_path):
    store = LeadStore(str(tmp_path / "leads.db"))
    lead = store.create(name="Asha Rao", organization="Acme Corp")

    updated = store.update(lead.id, name="Asha Mehta", organization="Globex Inc", remarks="Changed org")

    assert updated.name == "Asha Mehta"
    assert updated.organization == "Globex Inc"
    assert updated.remarks == "Changed org"
    assert store.get(lead.id).name == "Asha Mehta"


def test_update_missing_id_returns_none(tmp_path):
    store = LeadStore(str(tmp_path / "leads.db"))
    assert store.update("does-not-exist", name="Someone") is None


def test_delete_removes_lead_and_reports_success(tmp_path):
    store = LeadStore(str(tmp_path / "leads.db"))
    lead = store.create(name="Asha Rao")

    assert store.delete(lead.id) is True
    assert store.list() == []


def test_delete_missing_id_returns_false(tmp_path):
    store = LeadStore(str(tmp_path / "leads.db"))
    assert store.delete("does-not-exist") is False
