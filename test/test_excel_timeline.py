import unittest

from cogtasks.excel_timeline import Row, Rows, Event, write_excel_timeline


class TestExcelGantt(unittest.TestCase):
    def test_iter_rows(self):

        r = Rows()

        a = Row('A')
        aa = Row('AA', events=[Event('AA1', 1, 2), Event('AA2', 10, 12), Event('AA3', 11, 15)])
        a.add_child_row(aa)
        ab = Row('AB', events=[Event('AB1', 3, 4), Event('AB2', 11, 12)])
        a.add_child_row(ab)

        b = Row('B')
        c = Row('C', events=[Event('C1', 5, 6), Event('C2', 12, 14)])

        r.add_row(a)
        r.add_row(b)
        r.add_row(c)

        for indent, row in r.visit_rows():
            print("{}{}".format(' '*indent, row))

        print(r.find_row('AA'))

        # print(r.find_row('aab'))

        write_excel_timeline("test.xlsx", r, mins_per_col=1, worksheet_name=None)

    def test_find_or_create(self):
        r = Rows()
        r.find_row_path(['A','B','C'], create=True)
        for indent, row in r.visit_rows():
            print("{}{}".format(' '*indent, row))

        b = r.find_row_path(['A','B'])
        print(b)

if __name__ == '__main__':
    unittest.main()
