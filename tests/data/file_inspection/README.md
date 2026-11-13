# Legacy XLS fixture

`legacy.xls` is synthetic BIFF8 data generated with xlwt. Sheet `Data` contains:

| id  | label |
| --- | ----- |
| 2   | alpha |
| 3   | beta  |

Generation (xlwt is a fixture-generation tool, not a project dependency):

```python
import xlwt

book = xlwt.Workbook()
sheet = book.add_sheet("Data")
for row_no, row in enumerate([["id", "label"], [2, "alpha"], [3, "beta"]]):
    for column_no, value in enumerate(row):
        sheet.write(row_no, column_no, value)
book.save("legacy.xls")
```
