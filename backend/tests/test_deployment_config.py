import os
import runpy
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy.dialects.postgresql.psycopg import PGDialect_psycopg
from src import gcp_service


class DatabaseConfigurationTests(unittest.TestCase):
    def connection_parameters(self, host):
        environment = {
            "DB_HOST": host,
            "DB_PORT": "5433",
            "DB_USER": "test_user",
            "DB_PASSWORD": "synthetic@password:/?#%",
            "DB_NAME": "test_database",
        }
        with patch.dict(os.environ, environment, clear=True):
            config = runpy.run_path(
                str(Path(__file__).resolve().parents[1] / "src/config.py")
            )
        _, parameters = PGDialect_psycopg().create_connect_args(config["DATABASE_URI"])
        return parameters

    def test_local_tcp_and_reserved_password_characters(self):
        parameters = self.connection_parameters("127.0.0.1")
        self.assertEqual(parameters["host"], "127.0.0.1")
        self.assertEqual(parameters["port"], 5433)
        self.assertEqual(parameters["password"], "synthetic@password:/?#%")
        self.assertEqual(parameters["dbname"], "test_database")

    def test_cloud_sql_socket_and_reserved_password_characters(self):
        socket = "/cloudsql/test-project:us-east1:test-instance"
        parameters = self.connection_parameters(socket)
        self.assertEqual(parameters["host"], socket)
        self.assertEqual(parameters["password"], "synthetic@password:/?#%")


class StorageCredentialsTests(unittest.TestCase):
    def test_missing_key_uses_default_credentials(self):
        with (
            patch.object(gcp_service, "GCP_SERVICE_ACCOUNT_KEY", None),
            patch.object(
                gcp_service.service_account.Credentials, "from_service_account_file"
            ) as load_key,
            patch.object(gcp_service.storage, "Client") as client,
        ):
            gcp_service.get_bucket(gcp_service.get_credientials())
        load_key.assert_not_called()
        client.assert_called_once_with(project=gcp_service.GCP_PROJECT_ID)

    def test_explicit_local_key_is_preserved(self):
        with (
            patch.object(gcp_service, "GCP_SERVICE_ACCOUNT_KEY", "/test/key.json"),
            patch.object(
                gcp_service.service_account.Credentials, "from_service_account_file"
            ) as load_key,
            patch.object(gcp_service.storage, "Client") as client,
        ):
            gcp_service.get_bucket(gcp_service.get_credientials())
        load_key.assert_called_once_with("/test/key.json")
        client.assert_called_once_with(
            project=gcp_service.GCP_PROJECT_ID, credentials=load_key.return_value
        )


if __name__ == "__main__":
    unittest.main()
