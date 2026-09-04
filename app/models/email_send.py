from datetime import datetime

from pydantic import BaseModel


class EmailSendRecord(BaseModel):
    """One row of 'this saved email was sent to this address' -- only
    recorded when the send came from a saved content-library entry, since a
    record only ever makes sense attached to a creative_id.
    """

    to_email: str
    sent_at: datetime
