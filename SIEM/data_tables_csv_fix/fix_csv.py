import csv
import sys

def remove_commas_in_fields(input_file, output_file):
    """Removes all commas from each individual field in a CSV file.

    Args:
      input_file: Path to the input CSV file.
      output_file: Path to the output CSV file.
    """

    with open(input_file, 'r', newline='') as infile, \
         open(output_file, 'w', newline='') as outfile:

        reader = csv.reader(infile)
        writer = csv.writer(outfile)

        for row in reader:
            # This processes each field (column) in the row
            processed_row = [value.replace(',', '') for value in row]
            writer.writerow(processed_row)

if __name__ == "__main__":
    # Expect 3 arguments: script name, input file, output file
    if len(sys.argv) != 3:
        print("Usage: python script_name.py <input_csv_file> <output_csv_file>")
        sys.exit(1)

    # Assign arguments to variables
    input_csv = sys.argv[1]
    output_csv = sys.argv[2] # Use the second argument for the output file
    
    print(f"Processing '{input_csv}' and saving to '{output_csv}'...")
    remove_commas_in_fields(input_csv, output_csv)
    print("Done.")
