import argparse
import sys
import os
import logging
import time
from lib import evtx2chronicle_utils
from lib import siem_auth 

def parse_arguments():
    """Parses command-line arguments."""        
    parser = argparse.ArgumentParser(description='EVTX2Chronicle')

    # Required arguments
    parser.add_argument('--credentials_file', required=True, help='Path to Chronicle SIEM credentials JSON file')
    parser.add_argument('--customer_id', required=True, help='Chronicle SIEM Customer GUID')
    parser.add_argument('--region', required=True, help='Chronicle SIEM Ingestion API Region')
    parser.add_argument('--project_id', required=True, help='Chronicle SIEM GCP BYOP Project ID')
    parser.add_argument('--forwarder_id', required=True, help='Chronicle SIEM Forwarder Config GU')        
    parser.add_argument('--path', required=True, help='Path to EVTX or XML input file')
    parser.add_argument('--use_case_name', required=True, help='The Use Case name, added to the Ingestion Labels')

    # Optional arguments with default values
    parser.add_argument('--namespace', default="untagged", help="Chronicle SIEM Namespace")
    parser.add_argument('--test_mode', default="false", help="If true then Events are not replayed to SIEM")

    return parser.parse_args()


if __name__ == '__main__':
    args = parse_arguments()

    logging.basicConfig(
        level=logging.INFO, 
        format='<%(levelname)s>%(asctime)s: %(message)s', 
        datefmt='%Y-%m-%dT%H:%M:%S%z'
    )
    logger = logging.getLogger(__name__)
    
    for arg_name, arg_value in vars(args).items():
        logger.info(f'{arg_name.replace("_", " ").title()}: {arg_value}') 

    try:
        evtx_file = args.path

        if not os.path.exists(evtx_file):
            raise FileNotFoundError(f"The file {evtx_file} does not exist.")

        if not os.path.isfile(evtx_file):
            raise TypeError(f"{evtx_file} is not a file.")

        if not os.access(evtx_file, os.R_OK):
            raise PermissionError(f"The file {evtx_file} is not readable.")

        CREDENTIAL_FILE = args.credentials_file
        REGION = args.region
        CUSTOMER_ID = args.customer_id
        PROJECT_ID = args.project_id
        FORWARDER_ID = args.forwarder_id
        NAMESPACE = args.namespace
        USE_CASE_NAME = args.use_case_name

        # Extract the extension
        _, ext = os.path.splitext(evtx_file)

        # Normalize the extension (remove leading dot and lowercase)
        ext = ext.lower().lstrip(".")

        # Check if the extension is valid
        if ext in ("evtx"):
            logger.info(f"Valid file extension: {ext}")
            if evtx2chronicle_utils.is_file_empty(evtx_file):
                raise ValueError("File is empty.")            
            # Convert the EVTX to XML, and loads the XML file
            evtx2chronicle_utils.extract_xml_from_evtx(evtx_file, evtx_file + '.xml')
            evtx_xml = evtx2chronicle_utils.read_file(evtx_file + '.xml')        
        elif ext in ("xml"):
            logger.info(f"Valid file extension: {ext}")
            if evtx2chronicle_utils.is_file_empty(evtx_file):
                raise ValueError("File is empty.")            
            # Loads the XML file
            evtx_xml = evtx2chronicle_utils.read_file(evtx_file)
        else:
            logger(f"Invalid file extension: {ext}")
            raise ValueError("Invalid file type. Only .evtx or .xml files are expected.")

        file_name = os.path.basename(evtx_file)
        logger.info(f'EVTX filename = {file_name}')

        # The original string will include one or more Windows Event logs
        # each is delineated by opening and closing <Event> </Event> xml tags
        extract_evt_events = evtx2chronicle_utils.find_regex_matches(evtx_xml,"<Event\s.*?<\/Event>")

        final_event_list = evtx2chronicle_utils.update_log_times(extract_evt_events)
        final_event_types = list(map(evtx2chronicle_utils.check_evtx_type, final_event_list)) 

        # create a unique list to store the Ingestion Labels observed
        unique_event_type = list(set(final_event_types))
        logging.info(f'Unique Ingestion Labels count = {len(unique_event_type)}')

        if len(unique_event_type) > 1:
            logging.error(f'unique_event_type: {unique_event_type}')
            raise ValueError("More than one Ingestion Label observed.  Not supported.")
        else:
            LOG_TYPE = unique_event_type[0]

        logging.info(f'Event count = {len(final_event_list)}')
        logging.debug(f'Final Event List: {final_event_list}')

        final_event_list_size = sys.getsizeof(final_event_list)
        final_event_element_sizes = [sys.getsizeof(item) for item in final_event_list]
        total_element_size = sum(final_event_element_sizes)
        estimated_size = final_event_list_size + total_element_size

        logging.info(f"Estimated size of the list: {estimated_size} bytes")

        # In dry run mode we will only output to Console
        dry_run = args.test_mode
        logging.info(f'dry_run mode = {dry_run}')

        if dry_run == "false":

            auth_token = siem_auth.get_authorized_session(CREDENTIAL_FILE)

            chunks = evtx2chronicle_utils.split_list_by_size(final_event_list,NAMESPACE,USE_CASE_NAME)
            for chunk in chunks:

                payload = siem_auth.build_payload(PROJECT_ID, CUSTOMER_ID, FORWARDER_ID, chunk)
                logging.info(f"payload: {payload}")

                submission = siem_auth.send_to_chronicle(
                    REGION, PROJECT_ID, CUSTOMER_ID, LOG_TYPE, auth_token, payload)

                logging.info(f"submission: {submission.text}")

                time.sleep(1)   

    except Exception as e:
        logger.exception(f"An error occurred: {e}") 
    finally:
        logging.info(f'Exiting.')