"""Redação de segredos: detecção e bloqueio."""

from lore.redact import scan


def test_clean_text_passes():
    result = scan("Como configurar split DNS no WireGuard?")
    assert result.found == []
    assert "[REDIGIDO]" not in result.text


def test_private_key_blocked():
    text = "-----BEGIN RSA PRIVATE KEY-----\nabc"
    result = scan(text)
    assert "private-key" in result.found
    assert "BEGIN" not in result.text


def test_tokens_blocked():
    assert "github-token" in scan("token ghp_abcdefghij1234567890").found
    assert "openai-key" in scan("chave sk-abcdefghij1234567890").found
    assert "aws-key" in scan("AKIAIOSFODNN7EXAMPLE").found


def test_password_and_url_credentials():
    assert "password-assign" in scan("password: s3cr3t!x").found
    assert "url-credentials" in scan("https://user:s3cret@host/x").found


def test_extra_patterns_from_config():
    result = scan("projeto codinome abacaxi", extra=[r"codinome \w+"])
    assert result.found == ["extra-0"]
    assert "abacaxi" not in result.text


def test_bad_extra_pattern_ignored():
    result = scan("texto normal", extra=["(["])
    assert result.found == []
