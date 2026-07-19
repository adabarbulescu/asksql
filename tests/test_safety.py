import unittest

from asksql.safety import is_read_only, is_write


class SafetyTest(unittest.TestCase):
    def test_read_only_sql(self) -> None:
        self.assertTrue(is_read_only("select * from users"))
        self.assertTrue(is_read_only("with x as (select * from users) select * from x"))
        self.assertFalse(is_read_only("delete from users"))
        self.assertFalse(is_read_only("select * from users; drop table users"))

    def test_ignores_write_words_in_literals_and_comments(self) -> None:
        self.assertTrue(is_read_only("select 'drop table users' as note"))
        self.assertTrue(is_read_only("select 1 -- drop table users"))

    def test_rejects_multiple_statements(self) -> None:
        self.assertFalse(is_read_only("select 1; select 2"))

    def test_pragma_allowlist(self) -> None:
        self.assertTrue(is_read_only("pragma table_info(users)"))
        self.assertTrue(is_read_only("pragma foreign_key_list(orders)"))
        self.assertFalse(is_read_only("pragma journal_mode = WAL"))

    def test_explain_query_plan_validates_inner_sql(self) -> None:
        self.assertTrue(is_read_only("explain query plan select * from users"))
        self.assertFalse(is_read_only("explain query plan delete from users"))

    def test_rejects_write_structures(self) -> None:
        self.assertFalse(is_read_only("insert into users(id) values (1)"))
        self.assertFalse(is_read_only("update users set id = 1"))
        self.assertFalse(is_read_only("drop table users"))
        self.assertFalse(is_read_only("create table users(id integer)"))

    def test_recognizes_supported_single_write_statement(self) -> None:
        self.assertTrue(is_write("insert into users(id) values (1)"))
        self.assertTrue(is_write("update users set id = 1"))
        self.assertTrue(is_write("delete from users"))
        self.assertTrue(is_write("create table users(id integer)"))
        self.assertFalse(is_write("select * from users"))
        self.assertFalse(is_write("delete from users; drop table users"))
        self.assertFalse(is_write("pragma journal_mode = WAL"))


if __name__ == "__main__":
    unittest.main()
