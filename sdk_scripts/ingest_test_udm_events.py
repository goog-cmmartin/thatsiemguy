# Configuration Constants
CHRONICLE_CUSTOMER_ID = ""  # Your SecOps instance ID
CHRONICLE_PROJECT_ID = ""   # Your SecOps GCP project ID
CHRONICLE_REGION = ""       # Your SecOps API region
DEFAULT_PRODUCT_NAME = "My Security Product"                    # UDM Event Product Name
DEFAULT_VENDOR_NAME = "My Company"                              # UDM Vendor Product Name


import uuid
import json
from datetime import datetime, timezone
from secops import SecOpsClient
import argparse


def create_network_event(
    # Metadata parameters 
    event_id=None,  # Will be generated if not provided
    event_type="NETWORK_CONNECTION",
    product_name=DEFAULT_PRODUCT_NAME,
    vendor_name=DEFAULT_VENDOR_NAME,
    
    # Principal (source) parameters
    principal_hostname="unknown",
    principal_ip="0.0.0.0",
    principal_port=None, # Made optional by setting default to None
    
    # Target (destination) parameters
    target_ip="0.0.0.0",
    target_port=None,   # Made optional by setting default to None
    target_hostname=None,
    
    # Network parameters
    application_protocol="UNKNOWN_APPLICATION_PROTOCOL",
    direction="UNKNOWN_DIRECTION"
):
    """
    Creates a dictionary representing a network event.

    Args:
        event_id (str, optional): A unique identifier for the event. 
                                   If None, a UUID will be generated.
        event_type (str, optional): The type of the event (e.g., "NETWORK_CONNECTION").
                                    Defaults to "NETWORK_CONNECTION".
        product_name (str, optional): The name of the security product.
                                      Defaults to "My Security Product".
        vendor_name (str, optional): The name of the vendor. Defaults to "My Company".
        
        principal_hostname (str): The hostname of the principal (source).
        principal_ip (str): The IP address of the principal (source).
        principal_port (int, optional): The port of the principal (source). 
                                        If None, the 'port' field will be omitted.
        
        target_ip (str): The IP address of the target (destination).
        target_port (int, optional): The port of the target (destination). 
                                     If None, the 'port' field will be omitted.
        
        application_protocol (str): The application layer protocol (e.g., "HTTPS", "HTTP").
        direction (str): The direction of the connection ("INBOUND" or "OUTBOUND").

    Returns:
        dict: A dictionary representing the network event.
    """
    
    if event_id is None:
        event_id = str(uuid.uuid4())
    
    # Get current time in ISO 8601 format
    current_time = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    # Construct the principal dictionary conditionally
    principal_dict = {
        "hostname": principal_hostname,
        "ip": principal_ip,
    }
    if principal_port is not None: # Check if principal_port was provided
        principal_dict["port"] = principal_port

    # Construct the target dictionary conditionally
    target_dict = {
        "ip": target_ip,
    }
    if target_port is not None: # Check if target_port was provided
        target_dict["port"] = target_port

    if target_hostname is not None:
        target_dict["hostname"] = target_hostname

    # Construct the network dictionary conditionally
    network_dict = {}
    if application_protocol is not None:
        network_dict["application_protocol"] = application_protocol
    if direction is not None:
        network_dict["direction"] = direction

    network_event = {
        "metadata": {
            "id": event_id,
            "event_timestamp": current_time,
            "event_type": event_type,
            "product_name": product_name,
            "vendor_name": vendor_name
        },
        "principal": principal_dict,
        "target": target_dict,
        "network": network_dict 
    }
    return network_event


def create_process_event(
    # Metadata parameters
    event_id=None,
    event_type="PROCESS_LAUNCH", # Default for this specific event type
    product_name=DEFAULT_PRODUCT_NAME,
    vendor_name=DEFAULT_VENDOR_NAME,
    
    # Principal (source) parameters
    principal_hostname="unknown",
    
    # Target Hostname 
    target_hostname=None, 
    
    # Process details (optional)
    process_command_line=None,
    process_pid=None,
    process_file_path=None,
    process_file_hash_md5=None,
    process_file_hash_sha1=None,
    process_file_hash_sha256=None,
    
    # User details (optional)
    user_userid=None,
    user_username=None
):
    """
    Creates a dictionary representing a UDM PROCESS_LAUNCH event.

    Args:
        event_id (str, optional): A unique identifier for the event. 
                                   If None, a UUID will be generated.
        event_type (str, optional): The type of the event (e.g., "PROCESS_LAUNCH").
                                    Defaults to "PROCESS_LAUNCH".
        product_name (str, optional): The name of the security product.
                                      Defaults to "My Security Product".
        vendor_name (str, optional): The name of the vendor. Defaults to "My Company".
        
        principal_hostname (str): The hostname of the entity initiating the process.
                                  Defaults to "unknown".
        target_hostname (str, optional): The hostname where the process was launched.
                                         If None, the 'target' dictionary will not have a hostname.
                                         Defaults to None.
        
        process_command_line (str, optional): The full command line of the launched process.
                                              If None, this field is omitted.
        process_pid (int, optional): The process ID (PID) of the launched process.
                                     If None, this field is omitted.
        process_file_path (str, optional): The full path to the process executable.
                                           If None, this field is omitted.
        process_file_hash_md5 (str, optional): MD5 hash of the process executable.
                                               If None, this field is omitted.
        process_file_hash_sha1 (str, optional): SHA1 hash of the process executable.
                                                If None, this field is omitted.
        process_file_hash_sha256 (str, optional): SHA256 hash of the process executable.
                                                  If None, this field is omitted.

        user_userid (str, optional): The user ID (e.g., SID, UID) under which the process ran.
                                     If None, this field is omitted.
        user_username (str, optional): The username (human-readable) under which the process ran.
                                       If None, this field is omitted.

    Returns:
        dict: A dictionary representing the process launch event.
    """

    if event_id is None:
        event_id = str(uuid.uuid4())

    current_time = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    # --- Construct process dictionary conditionally ---
    process_dict = {}
    if process_command_line is not None:
        process_dict["command_line"] = process_command_line
    if process_pid is not None:
        process_dict["pid"] = process_pid

    # --- Handle file details and hashes ---
    # Create file_dict only if path or any hash is provided
    file_dict = {}
    if process_file_path is not None:
        file_dict["path"] = process_file_path
    if process_file_hash_md5 is not None:
        file_dict["md5"] = process_file_hash_md5
    if process_file_hash_sha1 is not None:
        file_dict["sha1"] = process_file_hash_sha1
    if process_file_hash_sha256 is not None:
        file_dict["sha256"] = process_file_hash_sha256

    # Add the 'file' dictionary to process_dict only if it's not empty
    if file_dict:
        process_dict["file"] = file_dict

    # --- Construct user dictionary conditionally ---
    user_dict = {}
    if user_userid is not None:
        user_dict["userid"] = user_userid
    if user_username is not None:
        user_dict["username"] = user_username

    # --- Initialize the main event dictionary ---
    process_event = {
        "metadata": {
            "id": event_id,
            "event_timestamp": current_time,
            "event_type": event_type,
            "product_name": product_name,
            "vendor_name": vendor_name
        },
        "principal": {
            "hostname": principal_hostname,
        },
        "target": {}
    }

    # Add target_hostname if provided
    if target_hostname is not None:
        process_event["target"]["hostname"] = target_hostname

    # Only add 'process' key to 'target' if process_dict is not empty
    if process_dict:
        process_event["target"]["process"] = process_dict

    # Only add 'user' key to 'target' if user_dict is not empty
    if user_dict:
        process_event["target"]["user"] = user_dict

    return process_event


if __name__ == "__main__":

    # --- Argument Parsing ---
    parser = argparse.ArgumentParser(
        description="Generate and optionally ingest UDM events into Chronicle."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true", # This makes it a flag: if present, True; otherwise, False
        help="Run in dry-run mode: generate events but do not ingest them into Chronicle."
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print generated UDM events to console."
    )

    args = parser.parse_args()

    # Initialize with default credentials
    client = SecOpsClient()
    chronicle = client.chronicle(
        customer_id=CHRONICLE_CUSTOMER_ID,
        project_id=CHRONICLE_PROJECT_ID,
        region=CHRONICLE_REGION
    )

    print(f"Running in dry-run mode: {args.dry_run}")
    print(f"Verbose output: {args.verbose}\n")

    # >>> IP or DOMAIN using UDM Event Type of NETWORK_CONNECTION

    """
    Note, for generating test events it is recommended to use a RFC TEST IP address range: 
    # 192.0.2.0/24 (TEST-NET-1): This block consists of 256 IP addresses (from 192.0.2.0 to 192.0.2.255). It's very commonly used in tutorials and documentation.
    # 198.51.100.0/24 (TEST-NET-2): Another block of 256 IP addresses (from 198.51.100.0 to 198.51.100.255).
    # 203.0.113.0/24 (TEST-NET-3): Also a block of 256 IP addresses (from 203.0.113.0 to 203.0.113.255).
    """

    # Example with Principal and Target IP only
    network_event_1 = create_network_event(
        principal_hostname="fake-source-host-01",
        principal_ip="192.0.2.11",
        target_ip="203.0.113.2"
    )

    # Example with a Target port
    network_event_2 = create_network_event(
        principal_hostname="fake-source-host-01",
        principal_ip="192.0.2.10",
        target_ip="203.0.113.1",
        target_port="8080"
    )

    # Example with a Target Hostname (Domain Name)
    network_event_3 = create_network_event(
        principal_hostname="fake-source-host-01",
        principal_ip="192.0.2.12",
        target_ip="203.0.113.3",
        target_hostname="www.acme.com"
    )

    all_network_events = [network_event_1, network_event_2, network_event_3]

    if args.verbose:
        print("Generated Network Events:")
        for i, event in enumerate(all_network_events):
            print(f"--- Network Event {i+1} ---")
            print(json.dumps(event, indent=4))
        print("-" * 40 + "\n")

    if not args.dry_run:
        print("Ingesting network events into Chronicle...")
        try:
            result_network = chronicle.ingest_udm(udm_events=all_network_events)
            print("Network Ingestion Result:", result_network)
        except Exception as e:
            print(f"Error ingesting network events: {e}")
    else:
        print("Skipping network event ingestion in dry-run mode.")

    # Example 1
    process_event_1 = create_process_event(
        principal_hostname="workstation-1",
        process_command_line="ping 8.8.8.8",
        process_pid="1234",
        user_userid="user123",
        process_file_hash_md5="65a8e27d88792838c4bb661601662580",
        process_file_hash_sha1="2ef7bde60bd1c2196e812fde1297e20a4b64a275",
        process_file_hash_sha256="d1e00a986c75a00473a246872584d4367375a02e5a7b744d28434857504f4202"
    )

    all_process_events = [process_event_1]

    if args.verbose:
        print("\nGenerated Process Events:")
        for i, event in enumerate(all_process_events):
            print(f"--- Process Event {i+1} ---")
            print(json.dumps(event, indent=4))
        print("-" * 40 + "\n")

    # --- Ingest Process Events (conditional on dry-run mode) ---
    if not args.dry_run:
        print("Ingesting process events into Chronicle...")
        try:
            result_process = chronicle.ingest_udm(udm_events=all_process_events)
            print("Process Ingestion Result:", result_process)
        except Exception as e:
            print(f"Error ingesting process events: {e}")
    else:
        print("Skipping process event ingestion in dry-run mode.")
