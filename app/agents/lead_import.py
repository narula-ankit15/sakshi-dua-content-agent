import csv
import io

# Header aliases, matched case-insensitively/trimmed -- a real-world export
# (Google Sheets, a signup form, a CRM) is never going to spell these
# exactly "name"/"phone"/"email"/"organization"/"remarks".
_FIELD_ALIASES = {
    "name": {"name", "full name", "lead name", "contact name"},
    "phone": {"phone", "phone number", "mobile", "mobile number", "contact number", "contact"},
    "email": {"email", "email id", "email address"},
    "organization": {"organization", "organisation", "company", "org", "company name"},
    "remarks": {"remarks", "notes", "comment", "comments", "remark"},
}


class LeadCsvError(ValueError):
    """Raised when the CSV has no recognizable name column at all -- every
    other field is optional, but a lead needs a name to be worth anything.
    """


def _map_headers(fieldnames: list[str]) -> dict[str, str]:
    """Returns {our_field: actual_csv_header} for whichever of our fields
    this file's header row has a recognizable column for."""
    normalized = {h.strip().lower(): h for h in fieldnames if h}
    mapping = {}
    for field, aliases in _FIELD_ALIASES.items():
        for alias in aliases:
            if alias in normalized:
                mapping[field] = normalized[alias]
                break
    return mapping


def parse_leads_csv(csv_text: str) -> tuple[list[dict], list[dict]]:
    """Returns (valid_rows, skipped) -- valid_rows are dicts ready for
    LeadStore.create(**row); skipped are [{row, reason}] (1-indexed,
    counting the header as row 1, matching what a spreadsheet user sees).
    """
    reader = csv.DictReader(io.StringIO(csv_text))
    if not reader.fieldnames:
        raise LeadCsvError("The CSV file appears to be empty.")

    mapping = _map_headers(reader.fieldnames)
    if "name" not in mapping:
        raise LeadCsvError(
            "Couldn't find a name column -- expected a header like 'Name', 'Full Name', or 'Contact Name'."
        )

    valid: list[dict] = []
    skipped: list[dict] = []
    for i, row in enumerate(reader, start=2):  # row 1 is the header
        name = (row.get(mapping["name"]) or "").strip()
        if not name:
            skipped.append({"row": i, "reason": "Missing name"})
            continue
        valid.append(
            {
                "name": name,
                "phone": (row.get(mapping.get("phone", ""), "") or "").strip(),
                "email": (row.get(mapping.get("email", ""), "") or "").strip(),
                "organization": (row.get(mapping.get("organization", ""), "") or "").strip(),
                "remarks": (row.get(mapping.get("remarks", ""), "") or "").strip(),
            }
        )
    return valid, skipped
