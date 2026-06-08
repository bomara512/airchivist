import pytest
import sqlite3
from unittest.mock import patch
from webapp.cli import main


def make_db(tmp_path):
    from tests.webapp.conftest import _setup_db, SEED_SQL
    db_path = str(tmp_path / "test.db")
    _setup_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.executescript(SEED_SQL)
    conn.close()
    return db_path


class TestWebappCLI:
    def test_starts_with_valid_db(self, tmp_path):
        db_path = make_db(tmp_path)
        with patch("webapp.cli.create_app") as mock_app:
            mock_app.return_value.run = lambda **kw: None
            main(["--db", db_path])
            mock_app.assert_called_once_with(db_path)

    def test_default_host_and_port(self, tmp_path):
        db_path = make_db(tmp_path)
        run_kwargs = {}
        with patch("webapp.cli.create_app") as mock_app:
            mock_app.return_value.run = lambda **kw: run_kwargs.update(kw)
            main(["--db", db_path])
        assert run_kwargs.get("host") == "127.0.0.1"
        assert run_kwargs.get("port") == 5000

    def test_custom_host_and_port(self, tmp_path):
        db_path = make_db(tmp_path)
        run_kwargs = {}
        with patch("webapp.cli.create_app") as mock_app:
            mock_app.return_value.run = lambda **kw: run_kwargs.update(kw)
            main(["--db", db_path, "--host", "0.0.0.0", "--port", "8080"])
        assert run_kwargs.get("host") == "0.0.0.0"
        assert run_kwargs.get("port") == 8080

    def test_debug_flag(self, tmp_path):
        db_path = make_db(tmp_path)
        run_kwargs = {}
        with patch("webapp.cli.create_app") as mock_app:
            mock_app.return_value.run = lambda **kw: run_kwargs.update(kw)
            main(["--db", db_path, "--debug"])
        assert run_kwargs.get("debug") is True

    def test_missing_db_exits(self, tmp_path):
        with pytest.raises(SystemExit) as exc_info:
            main(["--db", str(tmp_path / "nonexistent.db")])
        assert exc_info.value.code == 1
