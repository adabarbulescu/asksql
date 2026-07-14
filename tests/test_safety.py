import unittest

from asksql.safety import is_read_only


class SafetyTest(unittest.TestCase):
    def test_read_only_sql(self) -> None:
        self.assertTrue(is_read_only("select * from users"))
        self.assertTrue(is_read_only("with x as (select * from users) select * from x"))
        self.assertFalse(is_read_only("delete from users"))
        self.assertFalse(is_read_only("select * from users; drop table users"))


if __name__ == "__main__":
    unittest.main()
