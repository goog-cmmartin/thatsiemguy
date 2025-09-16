# CSV Comma Remover

This script removes all commas from within the fields of a CSV file. This is useful for cleaning up data where commas are not intended to be delimiters within a specific field.

## Usage

To use the script, run it from the command line with two arguments: the input file path and the output file path.

```bash
python fix_csv.py <input_file.csv> <output_file.csv>
```

The script will read the `input_file.csv`, remove the commas from each field, and save the result to `output_file.csv`.
