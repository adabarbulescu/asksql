import os
import unittest

from asksql.adapters import adapter_for
from asksql.models import ExecutionStatus
from asksql.service import QueryService


@unittest.skipUnless(os.getenv("ASKSQL_TEST_POSTGRES"), "PostgreSQL integration URL is not configured")
class PostgreSQLIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.url = os.environ["ASKSQL_TEST_POSTGRES"]
        cls.service = QueryService(cls.url)
        cls.service.execute("drop table if exists asksql_integration", allow_write=True)
        created = cls.service.execute(
            "create table asksql_integration(id serial primary key, name text not null)", allow_write=True
        )
        if created.status != ExecutionStatus.SUCCEEDED:
            raise RuntimeError(created.error)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.service.execute("drop table if exists asksql_integration", allow_write=True)

    def test_schema_read_and_write(self) -> None:
        inserted = self.service.execute("insert into asksql_integration(name) values ('studio')", allow_write=True)
        selected = self.service.execute("select name from asksql_integration order by id")
        details = adapter_for(self.url).inspect_details()

        self.assertEqual(inserted.status, ExecutionStatus.SUCCEEDED)
        self.assertEqual(selected.status, ExecutionStatus.SUCCEEDED)
        self.assertEqual(selected.result.rows, [("studio",)])
        self.assertIn("asksql_integration", details.tables)

    def test_statement_timeout(self) -> None:
        execution = self.service.execute("select pg_sleep(0.2)", timeout=0.01)

        self.assertEqual(execution.status, ExecutionStatus.TIMED_OUT)


if __name__ == "__main__":
    unittest.main()
