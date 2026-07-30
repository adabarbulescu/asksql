import unittest

from asksql.evals import evaluate_sql


class SqlQualityHarnessTest(unittest.TestCase):
    def test_accepts_read_only_sql_using_expected_tables(self) -> None:
        cases = [
            (
                "sqlite",
                "select customers.name, sum(orders.total) as revenue "
                "from customers join orders on orders.customer_id = customers.id "
                "group by customers.name order by revenue desc limit 10",
                {"customers", "orders"},
            ),
            (
                "postgres",
                "select date_trunc('week', created_at) as week, count(*) "
                "from signups group by week order by week desc limit 12",
                {"signups"},
            ),
            (
                "sqlite",
                "with paid as (select * from invoices where status = 'paid') select count(*) from paid",
                {"invoices"},
            ),
        ]

        for dialect, sql, tables in cases:
            with self.subTest(dialect=dialect, sql=sql):
                self.assertEqual(evaluate_sql(sql, dialect=dialect, required_tables=tables), [])

    def test_rejects_unsafe_or_wrong_table_sql(self) -> None:
        self.assertIn(
            "SQL must be one read-only statement",
            evaluate_sql("delete from customers", dialect="sqlite", required_tables={"customers"}),
        )
        self.assertIn(
            "SQL must use table: orders",
            evaluate_sql("select * from customers", dialect="sqlite", required_tables={"orders"}),
        )
        self.assertIn(
            "SQL must not use table: archived_orders",
            evaluate_sql(
                "select * from orders union all select * from archived_orders",
                dialect="sqlite",
                required_tables={"orders"},
                forbidden_tables={"archived_orders"},
            ),
        )


if __name__ == "__main__":
    unittest.main()
