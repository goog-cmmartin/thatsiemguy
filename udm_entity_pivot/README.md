# UDM Entity Pivot

This HTML widget, designed for Chronicle SOAR, enhances alert investigation by providing pivot links for UDM and Raw Log searches based on related entities.  It streamlines the process of querying Chronicle UDM and raw logs, enabling analysts to quickly explore relevant data within a specified timeframe.

## Features

* **Entity Table:** Displays entities associated with an alert, including:
    * Identifier
    * Type
    * Suspicious (flagged by Playbook)
    * Pivot (used to link alerts in a Case)
    * Internal (manually created)
    * Links for UDM Search and Raw Log Search pivots

* **Time Range:** Automatically determines the search time range based on the first and last timestamps of events in the alert.

* **UDM Search Pivot:**
    * Uses UDM Grouped Fields for case-insensitive matching across all UDM Nouns.

* **Raw Log Search Pivot:**
    * Employs case-insensitive regular expressions for searching.

* **Compound Search:**
    * Supports creating compound UDM searches with AND/OR logic.
    * Select multiple entities using the radio buttons.
    * Choose the desired logic (AND or OR) from the dropdown menu.
    * Click "Run" to execute the compound search.

## Usage

1.  The widget automatically loads entities related to the current alert.
2.  Click on the UDM Search or Raw Log Search links in the table to pivot on a specific entity.
3.  To create a compound search:
    * Select multiple entities using the radio buttons.
    * Choose the desired logic (AND or OR) from the "Compound Operator" dropdown.
    * Click the "Run" button.

## Development

This widget is built using HTML and JavaScript.  Further development or customization can be done by modifying the source code.

## Contributing

Contributions are welcome! Please submit pull requests for any bug fixes, enhancements, or new features.

