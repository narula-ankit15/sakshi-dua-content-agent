import pytest

from app.agents.lead_import import LeadCsvError, parse_leads_csv


def test_parses_standard_headers():
    csv_text = "Name,Phone,Email,Organization,Remarks\nAsha Rao,9876543210,asha@example.com,Acme Corp,Met at conference\n"

    valid, skipped = parse_leads_csv(csv_text)

    assert valid == [
        {
            "name": "Asha Rao",
            "phone": "9876543210",
            "email": "asha@example.com",
            "organization": "Acme Corp",
            "remarks": "Met at conference",
        }
    ]
    assert skipped == []


def test_matches_alias_headers_case_insensitively():
    csv_text = "full name,mobile,email id,company,notes\nVikram Singh,555-1234,vikram@example.com,Globex,Follow up next week\n"

    valid, skipped = parse_leads_csv(csv_text)

    assert valid[0]["name"] == "Vikram Singh"
    assert valid[0]["phone"] == "555-1234"
    assert valid[0]["organization"] == "Globex"
    assert valid[0]["remarks"] == "Follow up next week"


def test_missing_name_column_raises():
    csv_text = "Phone,Email\n9876543210,asha@example.com\n"

    with pytest.raises(LeadCsvError):
        parse_leads_csv(csv_text)


def test_empty_csv_raises():
    with pytest.raises(LeadCsvError):
        parse_leads_csv("")


def test_row_with_blank_name_is_skipped_with_reason():
    csv_text = "Name,Email\nAsha Rao,asha@example.com\n,noname@example.com\n"

    valid, skipped = parse_leads_csv(csv_text)

    assert len(valid) == 1
    assert valid[0]["name"] == "Asha Rao"
    assert skipped == [{"row": 3, "reason": "Missing name"}]


def test_missing_optional_columns_default_to_empty_string():
    csv_text = "Name\nAsha Rao\n"

    valid, skipped = parse_leads_csv(csv_text)

    assert valid == [{"name": "Asha Rao", "phone": "", "email": "", "organization": "", "remarks": ""}]


def test_whitespace_only_name_is_treated_as_missing():
    csv_text = "Name,Email\n   ,asha@example.com\n"

    valid, skipped = parse_leads_csv(csv_text)

    assert valid == []
    assert skipped == [{"row": 2, "reason": "Missing name"}]
