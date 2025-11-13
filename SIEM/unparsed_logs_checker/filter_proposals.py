import argparse
import json
import sys


def filter_proposal_results(input_file: str):
    """
    Reads the output file from propose_extensions_for_failures.py and filters it
    to show only completed operations.

    Args:
        input_file: Path to the file containing the output.
    """
    try:
        with open(input_file, 'r') as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Error: Input file not found at '{input_file}'", file=sys.stderr)
        return
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from '{input_file}'. Ensure it's a valid JSON file.", file=sys.stderr)
        return

    filtered_results = {}
    for log_type, proposals in data.items():
        completed_proposals = []
        for proposal in proposals:
            state = proposal.get("state")
            if state in ["SUCCEEDED", "FAILED"]:
                completed_proposals.append(proposal)
        
        if completed_proposals:
            filtered_results[log_type] = completed_proposals

    if filtered_results:
        print(json.dumps(filtered_results, indent=2))
    else:
        print("No completed (SUCCEEDED or FAILED) operations found in the input file.", file=sys.stderr)


def main():
    """Main function to parse arguments."""
    parser = argparse.ArgumentParser(
        description="Filter the output of propose_extensions_for_failures.py to show only completed operations."
    )
    parser.add_argument(
        "input_file",
        default="suggested_extensions.json",
        nargs='?',
        help="Path to the output file from propose_extensions_for_failures.py (default: 'suggested_extensions.json').",
    )

    args = parser.parse_args()
    filter_proposal_results(args.input_file)


if __name__ == "__main__":
    main()
