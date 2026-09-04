import smtplib
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from typing import Optional, Protocol


class EmailSender(Protocol):
    def send(self, *, to: list[str], subject: str, html_body: str) -> dict[str, str]:
        """Sends the same subject/body to each recipient as its own
        individual message (never one message with everyone in the To:
        header -- a workshop announcement isn't a group thread). Returns
        {email: error_message} for recipients that failed; a recipient
        absent from the dict succeeded. Only raises when nothing could be
        attempted at all (e.g. login itself failed)."""
        ...


class GmailSmtpSender:
    """Sends over Gmail's own SMTP server, authenticated as a real Gmail
    address via an App Password (never the account's login password) -- so
    the email genuinely comes from that address and shows up in its own
    Sent folder, not from some anonymous relay.
    """

    def __init__(self, address: str, app_password: str, display_name: str = ""):
        self._address = address
        self._app_password = app_password
        # Without this, Gmail/most clients fall back to showing the raw
        # address (or its local-part) as the sender -- not the trainer's
        # actual name.
        self._from_header = formataddr((display_name, address)) if display_name else address

    def send(self, *, to: list[str], subject: str, html_body: str) -> dict[str, str]:
        failures: dict[str, str] = {}
        # One login, one connection reused across every recipient -- with up
        # to 50 recipients, a fresh SMTP handshake per address would be both
        # slow and needlessly hammer Gmail's connection limits.
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(self._address, self._app_password)
            for recipient in to:
                message = MIMEMultipart("alternative")
                message["Subject"] = subject
                message["From"] = self._from_header
                message["To"] = recipient
                message.attach(MIMEText(html_body, "html"))
                try:
                    server.sendmail(self._address, [recipient], message.as_string())
                except smtplib.SMTPException as e:
                    # One recipient being refused (bad mailbox, etc.) shouldn't
                    # abort delivery to the rest of the list.
                    failures[recipient] = str(e)
        return failures


@dataclass(frozen=True)
class SenderIdentity:
    """Config-agnostic mirror of app.config.EmailSenderIdentity -- kept
    separate so this agent doesn't import the config module; main.py is the
    one place that translates Settings into this shape.
    """

    id: str
    display_name: str
    email: str
    app_password: str


class EmailSenderRegistry:
    """Holds every configured "send as" identity and looks one up by id at
    request time -- the frontend lets the user pick which identity to send
    from per email, so there's no single fixed EmailSender anymore.
    """

    def __init__(self, identities: list[SenderIdentity]):
        self._identities = identities
        self._senders: dict[str, EmailSender] = {
            i.id: GmailSmtpSender(i.email, i.app_password, i.display_name) for i in identities
        }

    def is_configured(self) -> bool:
        return len(self._senders) > 0

    def list_identities(self) -> list[SenderIdentity]:
        return self._identities

    def get(self, sender_id: Optional[str]) -> Optional[EmailSender]:
        if sender_id is not None:
            return self._senders.get(sender_id)
        # No preference given -- fall back to whichever identity is first,
        # so a caller that predates sender selection still works.
        return next(iter(self._senders.values()), None)
