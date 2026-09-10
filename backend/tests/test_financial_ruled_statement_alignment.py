"""Regression for fractional PDF table edges and sparse payment columns."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from services.financial.pdf_tables import read_tables, TableSource, GeometrySource
from services.financial.table_geometry import locate_table, TableGeometryError
from services.financial.candidate_page_scan import propose_scan_columns
from services.financial.candidate_sources import suggest_candidate_rows
from postgres.models.enums import CoordinateSpace

# Expected values transcribed from the user-supplied synthetic statement.
PAYMENTS = [
    ('2023-03-18', '€125,000', '', '€137,450'),
    ('2023-03-20', '', '€120,000', '€17,450'),
    ('2023-05-25', '€180,000', '', '€197,450'),
    ('2023-05-28', '', '€175,000', '€22,450'),
    ('2023-07-11', '€95,000', '', '€117,450'),
    ('2023-07-15', '', '€90,000', '€27,450'),
    ('2023-10-03', '€210,000', '', '€237,450'),
    ('2023-10-06', '', '€200,000', '€37,450'),
    ('2023-11-15', '€150,000', '', '€187,450'),
    ('2023-11-18', '', '€145,000', '€42,450'),
    ('2023-12-23', '€275,000', '', '€317,450'),
    ('2023-12-28', '', '€270,000', '€47,450'),
]


def source_from_table(table):
    rows = {}
    for cell in table.geometry.cells:
        rows.setdefault(cell.row, []).append(dict(column_index=cell.column,
            expected_text=cell.text, locator=cell.locator.to_json()))
    return dict(case_id='case', evidence_file_id='file', page_number=1,
        table_index=0, source_revision='a'*64, columns=list(range(5)),
        rows=[dict(row_index=i, cells=cells) for i,cells in sorted(rows.items())])


def assert_statement(test, table):
    test.assertEqual(table.table_source, TableSource.drawn_geometry)
    test.assertEqual(table.geometry_source, GeometrySource.cell_rectangles)
    source = source_from_table(table)
    rows = [{c['column_index']:c['expected_text'] for c in r['cells']} for r in source['rows']]
    test.assertEqual(len(rows),14)  # header, opening control, twelve payments
    test.assertEqual(rows[0],dict(enumerate(['Date','Description','Credit','Debit','Balance'])))
    test.assertEqual(rows[1][4],'€12,450')
    test.assertNotIn(2,rows[1]); test.assertNotIn(3,rows[1])
    balance=12450
    for row, (date,credit,debit,closing) in zip(rows[2:],PAYMENTS):
        test.assertEqual((row[0],row.get(2,''),row.get(3,''),row[4]),(date,credit,debit,closing))
        amount=lambda s:int(s.replace('€','').replace(',','')) if s else 0
        balance += amount(credit)-amount(debit)
        test.assertEqual(balance,amount(closing))
    choice,reason=propose_scan_columns(source,'EUR')
    test.assertIsNone(reason)
    test.assertEqual(choice['date_column'],0)
    test.assertEqual({choice['amount_column'],*choice['additional_amount_columns']},{2,3})
    proposed=[]
    with patch('services.financial.candidate_sources.read_candidate_source',return_value=source):
        for col in [choice['amount_column'],*choice['additional_amount_columns']]:
            result=suggest_candidate_rows(None,case_id='case',evidence_file_id='file',page_number=1,
                table_index=0,expected_revision='a'*64,date_column=0,amount_column=col,currency='EUR')
            proposed.extend(row for row in result['rows'] if row['suggested'])
    test.assertEqual(sorted(row['row_index'] for row in proposed),list(range(2,14)))
    test.assertEqual(sorted(row['date_source']['expected_text'] for row in proposed),sorted(p[0] for p in PAYMENTS))
    test.assertTrue(all(row['date_assessment']['proposals'] for row in proposed))
    return source


class RuledStatementAlignmentTests(unittest.TestCase):
    def test_fractional_ruled_edges_preserve_dates_blanks_and_running_balances(self):
        grid=[['Date','Description','Credit','Debit','Balance'],['2023-01-01','Opening Balance','','','€12,450']]
        grid += [[date,'Synthetic payment',credit,debit,balance] for date,credit,debit,balance in PAYMENTS]
        x=[104.4000015258789,162.0,320.3999938964844,385.1999816894531,450.0,507.6000061035156]
        rects=[[(x[c],331.0001+r*19,x[c+1],350.0001+r*19) for c in range(5)] for r in range(14)]
        table=SimpleNamespace(bbox=(x[0],331.0001,x[-1],597.0001),extract=lambda:grid,
            rows=[SimpleNamespace(cells=row) for row in rects])
        page=SimpleNamespace(rect=SimpleNamespace(width=612,height=792),rotation=0,
            find_tables=lambda:SimpleNamespace(tables=[table]),get_text=lambda _:[])
        tables=read_tables(page,1)
        self.assertEqual(len(tables),1)
        assert_statement(self,tables[0])

    def test_real_submillipoint_overlap_is_still_refused(self):
        with self.assertRaisesRegex(TableGeometryError,'share page area'):
            locate_table(page_number=1,table_rect=(0,0,100,100),cell_text=[['left','right']],
                cell_rects=[[(0,0,50.0004,20),(50.0003,0,100,20)]],
                space=CoordinateSpace.pdf_displayed,rotation=0,page_width=100,page_height=100)

    def test_rotated_adjacent_fractional_edges_remain_locatable(self):
        for rotation in (0,90,180,270):
            with self.subTest(rotation=rotation):
                table=locate_table(page_number=1,table_rect=(0,0,100,100),cell_text=[['left','right']],
                    cell_rects=[[(0,0,50.0004,20),(50.0004,0,100,20)]],
                    space=CoordinateSpace.pdf_unrotated,rotation=rotation,page_width=100,page_height=100)
                self.assertEqual(table.located_values,2)

if __name__=='__main__':unittest.main()
