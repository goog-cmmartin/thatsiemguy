# -*- coding: utf-8 -*-
"""
Finds and prints a specific filter block from a Chronicle parser file
by counting all operations (including mutate sub-functions).
"""

from collections import defaultdict
import argparse
import sys
import base64
import binascii

def find_parser_block(parser_file: str, target_node_type: str = None, target_node_index: int = None, list_nodes: bool = False):
    """
    Finds a specific node block (filter or control flow) or lists all nodes from a parser file.
    If the file content is base64 encoded, it will be automatically decoded.

    Args:
        parser_file: Path to the parser file (can be base64 encoded).
        target_node_type: The type of node to find (e.g., 'mutate', 'grok', 'if').
        target_node_index: The zero-based global index of the node to find.
        list_nodes: If True, lists all nodes instead of finding a specific block.
    """
    try:
        with open(parser_file, 'r') as f:
            file_content = f.read().strip()
    except FileNotFoundError:
        print(f"Error: Parser file not found at '{parser_file}'", file=sys.stderr)
        sys.exit(1)

    lines = []
    try:
        # Attempt to decode the entire file content as base64
        decoded_bytes = base64.b64decode(file_content, validate=True)
        decoded_str = decoded_bytes.decode('utf-8')
        # If we reach here, it was valid base64 and utf-8
        print(f"Info: Detected and successfully decoded base64 content from '{parser_file}'.", file=sys.stderr)
        lines = [line + '\n' for line in decoded_str.splitlines()]
    except (binascii.Error, UnicodeDecodeError):
        # Decoding failed, assume it's plain text
        with open(parser_file, 'r') as f:
            lines = f.readlines()

    # All keywords that represent a countable "node" in the parser graph
    #node_keywords = ["mutate", "replace", "merge", "grok", "match", "convert", "rename", "json", "date", "drop", "kv", "if", "else", "elseif", "for"]
    node_keywords = ["mutate", "grok", "json", "date", "kv", "if", "else", "elseif", "for"]

    node_counter = 0
    brace_level = 0
    in_target_block = False
    
    current_block_content = []
    current_block_start_line = 0
    
    # Store all found nodes for potential error reporting
    all_found_nodes = {}

    if list_nodes:
        print(f"--- Listing all countable nodes in '{parser_file}' ---")

    for line_num, line in enumerate(lines, 1):
        stripped_line = line.strip()
        
        # Find which keyword, if any, this line starts with
        current_node_type = next((keyword for keyword in node_keywords if stripped_line.startswith(keyword)), None)

        if current_node_type:
            # This line defines a new node
            all_found_nodes[node_counter] = {
                "type": current_node_type,
                "line_num": line_num,
                "content": stripped_line
            }

            if list_nodes:
                print(f"  Node {node_counter:03d} ({current_node_type}): (Line {line_num:03d}) {stripped_line}")

            # Check if this is the node we are looking for
            if node_counter == target_node_index and current_node_type == target_node_type:
                in_target_block = True
                current_block_start_line = line_num
                brace_level = 0 # Reset brace level for the new block
            
            node_counter += 1

        if in_target_block:
            current_block_content.append(line)
            # Handle special case for 'else' which might not have its own block braces
            # e.g., `else if ... {` or just `else {`
            if stripped_line.startswith("else") and "if" in stripped_line:
                 pass # The 'if' part will handle the brace
            elif stripped_line == "else":
                 pass # The next line should have the brace
            else:
                brace_level += line.count('{')
            
            brace_level -= line.count('}')

            # Block ends when brace level returns to 0
            if brace_level == 0 and current_block_content:
                block_text = "".join(current_block_content).strip()
                print(f"\n--- Found Block for Node #{target_node_index} ('{target_node_type}') in '{parser_file}' ---")
                print(f"Block starts at line {current_block_start_line}")
                print(block_text)
                print("----------------------------------------------------")
                return
    
    if list_nodes:
        print(f"\nFound a total of {node_counter} nodes.")
    elif target_node_type is not None and target_node_index is not None:
        error_message = f"Error: Could not find node '{target_node_type}' with global index {target_node_index}. The script found a total of {node_counter} nodes."
        
        if target_node_index in all_found_nodes:
            found_node = all_found_nodes[target_node_index]
            error_message += f"\n  However, at global index {target_node_index} (line {found_node['line_num']}), a '{found_node['type']}' node was found: '{found_node['content']}'"
        
        print(error_message, file=sys.stderr)


def main():
    """Main function to parse arguments."""
    parser = argparse.ArgumentParser(
        description="Find a specific filter or control flow block in a Chronicle parser file based on its global index."
    )
    parser.add_argument(
        "parser_file",
        help="Path to the decoded parser file (e.g., 'CHRONICLE_SOAR_AUDIT_decoded.conf').",
    )
    parser.add_argument(
        "node_type",
        nargs='?',
        help="The type of node that failed (e.g., 'mutate', 'grok', 'if'). From the error message 'filter <type> ...'.",
    )
    parser.add_argument(
        "node_index",
        type=int,
        nargs='?',
        help="The zero-based global index of the failing node. From the error message '... (<index>) failed'.",
    )
    parser.add_argument(
        "--list-nodes",
        action="store_true",
        help="List all found nodes (filters and control flow) with their global index and line numbers.",
    )

    args = parser.parse_args()

    if not args.list_nodes and (args.node_type is None or args.node_index is None):
        parser.error("When not using '--list-nodes', both 'node_type' and 'node_index' must be provided.")

    find_parser_block(args.parser_file, args.node_type, args.node_index, args.list_nodes)


if __name__ == "__main__":
    main()
