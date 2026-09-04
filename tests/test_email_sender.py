from unittest.mock import MagicMock, patch

from app.agents.email_sender import EmailSenderRegistry, GmailSmtpSender, SenderIdentity


@patch("smtplib.SMTP")
def test_send_authenticates_and_sends_via_gmail_smtp(mock_smtp_class):
    mock_server = MagicMock()
    mock_smtp_class.return_value.__enter__.return_value = mock_server

    sender = GmailSmtpSender("me@gmail.com", "app-password-1234")
    failures = sender.send(to=["recipient@example.com"], subject="Hello", html_body="<p>Hi there</p>")

    mock_smtp_class.assert_called_once_with("smtp.gmail.com", 587)
    mock_server.starttls.assert_called_once()
    mock_server.login.assert_called_once_with("me@gmail.com", "app-password-1234")

    assert failures == {}
    assert mock_server.sendmail.call_count == 1
    from_addr, to_addrs, raw_message = mock_server.sendmail.call_args[0]
    assert from_addr == "me@gmail.com"
    assert to_addrs == ["recipient@example.com"]
    assert "Hello" in raw_message
    assert "Hi there" in raw_message


@patch("smtplib.SMTP")
def test_send_sends_each_recipient_as_its_own_individual_message_over_one_connection(mock_smtp_class):
    mock_server = MagicMock()
    mock_smtp_class.return_value.__enter__.return_value = mock_server

    sender = GmailSmtpSender("me@gmail.com", "app-password-1234")
    recipients = ["a@example.com", "b@example.com", "c@example.com"]
    failures = sender.send(to=recipients, subject="Hello", html_body="<p>Hi</p>")

    # One login/connection reused for every recipient, not one per recipient.
    mock_smtp_class.assert_called_once_with("smtp.gmail.com", 587)
    mock_server.login.assert_called_once()

    assert failures == {}
    assert mock_server.sendmail.call_count == 3
    sent_to = [call.args[1] for call in mock_server.sendmail.call_args_list]
    # Each call's To: list has exactly one recipient -- never everyone at once.
    assert sent_to == [["a@example.com"], ["b@example.com"], ["c@example.com"]]


@patch("smtplib.SMTP")
def test_send_isolates_a_single_recipient_failure_from_the_rest_of_the_batch(mock_smtp_class):
    import smtplib

    mock_server = MagicMock()
    mock_smtp_class.return_value.__enter__.return_value = mock_server

    def sendmail_side_effect(from_addr, to_addrs, message):
        if to_addrs == ["bad@example.com"]:
            raise smtplib.SMTPRecipientsRefused({"bad@example.com": (550, b"mailbox unavailable")})

    mock_server.sendmail.side_effect = sendmail_side_effect

    sender = GmailSmtpSender("me@gmail.com", "app-password-1234")
    failures = sender.send(to=["good@example.com", "bad@example.com"], subject="Hi", html_body="<p>x</p>")

    assert "good@example.com" not in failures
    assert "bad@example.com" in failures
    assert mock_server.sendmail.call_count == 2


@patch("smtplib.SMTP")
def test_send_uses_display_name_in_from_header_when_given(mock_smtp_class):
    mock_server = MagicMock()
    mock_smtp_class.return_value.__enter__.return_value = mock_server

    sender = GmailSmtpSender("narula.blue@gmail.com", "app-password", display_name="Ankit Narula")
    sender.send(to=["recipient@example.com"], subject="Hi", html_body="<p>x</p>")

    raw_message = mock_server.sendmail.call_args[0][2]
    assert 'From: "Ankit Narula" <narula.blue@gmail.com>' in raw_message or "From: Ankit Narula <narula.blue@gmail.com>" in raw_message


@patch("smtplib.SMTP")
def test_send_falls_back_to_bare_address_without_a_display_name(mock_smtp_class):
    mock_server = MagicMock()
    mock_smtp_class.return_value.__enter__.return_value = mock_server

    sender = GmailSmtpSender("narula.blue@gmail.com", "app-password")
    sender.send(to=["recipient@example.com"], subject="Hi", html_body="<p>x</p>")

    raw_message = mock_server.sendmail.call_args[0][2]
    assert "From: narula.blue@gmail.com" in raw_message


@patch("smtplib.SMTP")
def test_send_propagates_smtp_errors(mock_smtp_class):
    import smtplib

    mock_server = MagicMock()
    mock_server.login.side_effect = smtplib.SMTPAuthenticationError(535, b"bad credentials")
    mock_smtp_class.return_value.__enter__.return_value = mock_server

    sender = GmailSmtpSender("me@gmail.com", "wrong-password")
    try:
        sender.send(to=["recipient@example.com"], subject="Hi", html_body="<p>x</p>")
        assert False, "expected SMTPAuthenticationError to propagate"
    except smtplib.SMTPAuthenticationError:
        pass


def test_registry_is_not_configured_when_empty():
    registry = EmailSenderRegistry([])

    assert registry.is_configured() is False
    assert registry.list_identities() == []
    assert registry.get(None) is None
    assert registry.get("anything") is None


def test_registry_looks_up_by_id():
    identities = [
        SenderIdentity(id="ankit", display_name="Ankit Narula", email="narula.blue@gmail.com", app_password="a"),
        SenderIdentity(id="sakshi", display_name="Sakshi Dua", email="sakshidua.imagecoach@gmail.com", app_password="b"),
    ]
    registry = EmailSenderRegistry(identities)

    assert registry.is_configured() is True
    assert registry.list_identities() == identities
    assert registry.get("sakshi") is not None
    assert registry.get("does-not-exist") is None


def test_registry_falls_back_to_first_identity_when_no_sender_id_given():
    identities = [
        SenderIdentity(id="ankit", display_name="Ankit Narula", email="narula.blue@gmail.com", app_password="a"),
        SenderIdentity(id="sakshi", display_name="Sakshi Dua", email="sakshidua.imagecoach@gmail.com", app_password="b"),
    ]
    registry = EmailSenderRegistry(identities)

    assert registry.get(None) is registry.get("ankit")
