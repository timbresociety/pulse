import uuid

import pytest
from pydantic import ValidationError

from app.auth import hash_otp
from app.config import settings
from app.schemas import EmailOtpVerifyIn


def test_otp_hash_is_bound_to_challenge_email_and_code(monkeypatch):
    monkeypatch.setattr(settings, "otp_pepper", "test-pepper")
    challenge_id = uuid.uuid4()
    digest = hash_otp(challenge_id, "person@example.com", "123456")

    assert digest == hash_otp(challenge_id, "PERSON@example.com", "123456")
    assert digest != hash_otp(uuid.uuid4(), "person@example.com", "123456")
    assert digest != hash_otp(challenge_id, "other@example.com", "123456")
    assert digest != hash_otp(challenge_id, "person@example.com", "654321")
    assert "123456" not in digest


def test_otp_schema_accepts_only_six_digits():
    challenge_id = uuid.uuid4()
    assert EmailOtpVerifyIn(challenge_id=challenge_id, code=" 123 456 ").code == "123456"

    for invalid in ("12345", "1234567", "abcdef", "12-3456"):
        with pytest.raises(ValidationError):
            EmailOtpVerifyIn(challenge_id=challenge_id, code=invalid)


def test_otp_requires_delivery_outside_debug(monkeypatch):
    monkeypatch.setattr(settings, "otp_email_enabled", True)
    monkeypatch.setattr(settings, "resend_api_key", "")
    monkeypatch.setattr(settings, "smtp_host", "")
    monkeypatch.setattr(settings, "debug", False)
    assert settings.otp_available is False

    monkeypatch.setattr(settings, "debug", True)
    assert settings.otp_available is True
