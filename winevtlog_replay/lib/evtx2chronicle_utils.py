import os
import re
import sys
import logging
import base64
import Evtx.Evtx as evtx  #!pip3 install python-evtx
from datetime import date, datetime, timedelta

logger = logging.getLogger(__name__) 

def is_file_empty(filename):
  """Checks if a file is empty.

  Args:
    filename: The path to the file.

  Returns:
    True if the file is empty, False otherwise.
  """

  return os.stat(filename).st_size == 0

def read_file(filename):
  """
  This function reads a file and returns its content as a string.

  Args:
      filename: The path to the file you want to read.

  Returns:
      A string containing the contents of the file, or None if there's an error.
  """

  try:
    with open(filename, "r") as file:
        content = "".join(
            line.replace("\t", "\\t") for line in file if line.strip()
        )           
        return content      
  except FileNotFoundError:
    print(f"Error: File not found - {filename}")
    return None
  except Exception as e:
    print(f"Error reading file {filename}: {e}")
    return None
  

def find_regex_matches(text, pattern):
  """
  This function finds matches in a string using a regex pattern and returns the match groups.

  Args:
      text: The string to search for matches.
      pattern: The regular expression pattern to use.

  Returns:
      A list of match groups found in the string, or an empty list if no matches are found.
  """

  regex = re.compile(pattern, re.DOTALL)

  matches = regex.findall(text)

  return matches


def get_date_with_offset(offset=0):
  """Gets the current date with an optional offset in YYYY-MM-DD format.

  Args:
      offset: An integer representing the number of days to offset the current date.
              Positive values move the date forward, negative values move it backward.

  Returns:
      A string representing the adjusted date in YYYY-MM-DD format.
  """

  today = date.today()
  adjusted_date = today + timedelta(days=offset)
  formatted_date = adjusted_date.strftime("%Y-%m-%d")
  return formatted_date


def extract_xml_from_evtx(evtx_file_path, output_file_path):
    """Extracts XML data from an EVTX file and saves it to an XML file.

    Args:
        evtx_file_path (str): The path to the input EVTX file.
        output_file_path (str): The path to the output XML file.

    Raises:
        FileNotFoundError: If the input EVTX file does not exist.
        TypeError: If the input path is not a file.
        PermissionError: If the input EVTX file is not readable.
    """  
    with evtx.Evtx(evtx_file_path) as log:
        with open(output_file_path, 'w', encoding='utf-8') as outfile:
            outfile.write('<Events>\n')  # Start the XML document
            for record in log.records():
                try:
                    outfile.write(record.xml().replace('\n', '') + '\n')
                except Exception as e:
                    print(f"Error processing record: {e}")
            outfile.write('</Events>\n')  # Close the XML document


def prepare_log_entry(log_message, namespace, use_case_name):
    """
    Encodes a log message into a base64-encoded JSON string.

    Args:
        log_message: original windows XML event
        namespace: SecOps SIEM environment namespace
        use_case_name: Adds custom metadata.ingestion_labels

    Returns:
        A dictionary in the Telemetry Log format
    """

    json_bytes = log_message.encode('utf-8')
    base64_bytes = base64.b64encode(json_bytes)
    base64_str = base64_bytes.decode('utf-8')
    return { "data": base64_str, 
            "environment_namespace": namespace,
            "labels" : {
                "use_case_name": {
                   "value": use_case_name
                    },
                "replayed_date": {
                    "value": get_date_with_offset()
                    }
                }
            }


def split_list_by_size(data_list, namespace="untagged", use_case_name="evtx_replay", max_chunk_size=3200000, max_limit=4000000):
    """
    Splits a list into chunks based on their estimated size in bytes.

    Args:
        data_list: The list to be split.
        max_chunk_size: The target maximum size for each chunk in bytes (default: 800KB).
        max_limit: The absolute maximum size allowed for a chunk in bytes (default: 1MB).

    Returns:
        A list of lists, where each sublist represents a chunk of the original list.
    """

    chunks = []
    current_chunk = []
    current_chunk_size = 0

    for item in data_list:
        item_size = sys.getsizeof(item)
        item = prepare_log_entry(item,namespace,use_case_name)

        # If adding the item would exceed the max_limit, start a new chunk
        if current_chunk_size + item_size > max_limit:
            chunks.append(current_chunk)
            current_chunk = []
            current_chunk_size = 0

        # If adding the item would exceed the target chunk size, 
        # and the current chunk is not empty, start a new chunk
        elif current_chunk_size + item_size > max_chunk_size and current_chunk:
            chunks.append(current_chunk)
            current_chunk = [item]
            current_chunk_size = item_size

        # Otherwise, add the item to the current chunk
        else:
            current_chunk.append(item)
            current_chunk_size += item_size

    # Add the last chunk if it's not empty
    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def check_evtx_type(evtx):
    """
    Checks a string for specific identifiers and returns a corresponding type.

    Args:
        text: The string to check.

    Returns:
        The detected Chronicle Ingestion Label based upon the Channel
        Returns WINEVTLOG if no exact match is found.
    """   

    # Security
    if "Microsoft-Windows-Security-Auditing" in evtx:
        return "WINEVTLOG"
    # System
    elif "<Channel>System</Channel>" in evtx:
        return "WINEVTLOG"       
    # Application
    elif "<Channel>Application</Channel>" in evtx:
       return "WINEVTLOG"
    # Setup
    elif "<Channel>Setup</Channel>" in evtx:
       return "WINEVTLOG"       
    # Sysmon
    elif "Microsoft-Windows-Sysmon/Operational" in evtx:
       return "WINDOWS_SYSMON"
    # PowerShell 
    elif "<Channel>PowerShellCore/Operational</Channel>" in evtx:
        return "POWERSHELL"
    elif "<Channel>Windows PowerShell</Channel>" in evtx:
        return "POWERSHELL"
    elif "<Channel>Microsoft-Windows-PowerShell/Operational</Channel>" in evtx:
        return "POWERSHELL"       
    # Catch-all            
    else:
        return "WINEVTLOG"


def sort_logs(logs):
  """Sorts a list of logs by date and time, oldest to newest.

  Args:
    logs: A list of log strings in the format "SystemTime=\"YYYY-MM-DDTHH:MM:SS.fffffffZ\"".

  Returns:
    A new list of logs sorted by date and time.
  """
  def extract_datetime(log):
    """Extracts the datetime object from a log string."""

    timestamp_str = log.split('SystemTime="')[1].split('"')[0]
    return datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))

  return sorted(logs, key=extract_datetime)


def update_log_times(logs, offset_minutes=-60):
  """
  Updates the timestamps in a list of logs.

  Args:
    logs: A list of log strings, each containing a "TimeCreated SystemTime" entry.
    offset_minutes: An optional offset in minutes to apply to the latest timestamp.

  Returns:
    A new list of log strings with updated timestamps.
  """

  logs = sort_logs(logs)

  # Get the last log entry and extract its timestamp
  last_log = logs[-1]
  last_timestamp_str = last_log.split('SystemTime="')[1].split('"')[0]
  last_timestamp = datetime.fromisoformat(last_timestamp_str.replace('Z', '+00:00'))

  # Calculate the new "now" timestamp
  now = datetime.now(last_timestamp.tzinfo) + timedelta(minutes=offset_minutes)

  # Calculate the time difference between the last timestamp and the new "now"
  time_delta = now - last_timestamp

  updated_logs = []
  for log in logs:

    # Extract the timestamp from the current log entry
    # General Windows Event Log
    timestamp_str = log.split('SystemTime="')[1].split('"')[0]
    timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))

    # Update the timestamp by adding the time difference
    new_timestamp = timestamp + time_delta

    # Windows Sysmon
    # - The WINDOWS_SYSMON parser in Chronicle SIEM uses the UtcTime field rather than SystemTime
    # <Data Name="UtcTime">2024-08-23 07:47:07.196</Data>

    if '<Data Name="UtcTime">' in log:
        sysmon_timestamp_str = log.split('"UtcTime">')[1].split('<')[0]
        sysmon_timestamp = datetime.strptime(sysmon_timestamp_str, "%Y-%m-%d %H:%M:%S.%f")

        new_sysmon_timestamp = sysmon_timestamp + time_delta

        new_sysmon_timestamp_str = new_sysmon_timestamp.strftime("%Y-%m-%d %H:%M:%S.%f")
        log = log.replace(sysmon_timestamp_str, new_sysmon_timestamp_str)        


    # Format the new timestamp back into the original string format
    new_timestamp_str = new_timestamp.isoformat().replace('+00:00', 'Z')
    updated_log = log.replace(timestamp_str, new_timestamp_str)
    updated_logs.append(updated_log)

  return updated_logs

