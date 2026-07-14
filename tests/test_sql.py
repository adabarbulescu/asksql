import unittest

from asksql.sql import clean_sql, pretty_sql


class SqlTest(unittest.TestCase):
    def test_clean_sql(self) -> None:
        self.assertEqual(clean_sql("```sql\nselect * from users\n```"), "select *\nfrom users")
        self.assertEqual(clean_sql("select * from users"), "select *\nfrom users")

    def test_pretty_sql(self) -> None:
        self.assertEqual(pretty_sql("select * from users order by id"), "select *\nfrom users\norder by id")


if __name__ == "__main__":
    unittest.main()
