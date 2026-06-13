"""Tests for app gateway CLI behavior."""

import errno

from click.testing import CliRunner

from hal9000.cli import cli


def test_gateway_http_reports_port_in_use(monkeypatch):
    """A bound gateway port should produce a presenter-readable CLI error."""

    def raise_port_in_use(*args, **kwargs):
        raise OSError(errno.EADDRINUSE, "Address already in use")

    monkeypatch.setattr("hal9000.gateway.http.run_gateway_http_server", raise_port_in_use)

    result = CliRunner().invoke(
        cli,
        ["gateway", "http", "--host", "127.0.0.1", "--port", "9101"],
    )

    assert result.exit_code != 0
    assert "could not bind 127.0.0.1:9101" in result.output
    assert "open http://127.0.0.1:9101/ui" in result.output
    assert "lsof -nP -iTCP:9101 -sTCP:LISTEN" in result.output
    assert "python3 -m hal9000.cli gateway http --host 127.0.0.1 --port 9104" in result.output
