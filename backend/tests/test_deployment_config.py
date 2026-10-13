import runpy
from pathlib import Path

from sqlalchemy.dialects.postgresql.psycopg import PGDialect_psycopg
from src import gcp_service


def connection_parameters(monkeypatch, host):
    settings = {
        "DB_HOST": host,
        "DB_PORT": "5433",
        "DB_USER": "test_user",
        "DB_PASSWORD": "test@password:/?#%",
        "DB_NAME": "test_database",
    }
    for name, value in settings.items():
        monkeypatch.setenv(name, value)

    path = Path(__file__).resolve().parents[1] / "src/config.py"
    config = runpy.run_path(str(path))
    _, parameters = PGDialect_psycopg().create_connect_args(config["DATABASE_URI"])
    return parameters


def test_local_connection(monkeypatch):
    parameters = connection_parameters(monkeypatch, "127.0.0.1")
    assert parameters["host"] == "127.0.0.1"
    assert parameters["port"] == 5433
    assert parameters["dbname"] == "test_database"
    assert parameters["password"] == "test@password:/?#%"


def test_cloud_sql_socket(monkeypatch):
    socket = "/cloudsql/test-project:test-region:test-instance"
    parameters = connection_parameters(monkeypatch, socket)
    assert parameters["host"] == socket
    assert parameters["password"] == "test@password:/?#%"


def test_no_key_file(monkeypatch):
    monkeypatch.setattr(gcp_service, "GCP_SERVICE_ACCOUNT_KEY", None)

    def unexpected_file_read(path):
        raise AssertionError("No key file should be read")

    monkeypatch.setattr(
        gcp_service.service_account.Credentials,
        "from_service_account_file",
        unexpected_file_read,
    )
    assert gcp_service.get_credientials() is None


def test_local_key_file(monkeypatch):
    monkeypatch.setattr(gcp_service, "GCP_SERVICE_ACCOUNT_KEY", "/test/key.json")
    credentials = object()

    def read_test_key(path):
        assert path == "/test/key.json"
        return credentials

    monkeypatch.setattr(
        gcp_service.service_account.Credentials,
        "from_service_account_file",
        read_test_key,
    )
    assert gcp_service.get_credientials() is credentials
