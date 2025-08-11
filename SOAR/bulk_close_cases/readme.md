# **Bulk Case Closer Utility**

## **Overview**

This command-line script is designed to connect to a Siemplify SOAR instance via its API, search for open cases based on specific criteria, and close them in bulk. It is highly configurable, allowing users to specify the case title and time window for the search. The script processes each configured environment individually to ensure compatibility with API limitations.

## **Features**

* **Bulk Case Closing**: Closes multiple open cases in a single run.  
* **Targeted Search**: Filters cases by title and creation date (e.g., last 30 days).  
* **Environment Iteration**: Queries each environment one by one to avoid API errors.  
* **Flexible Execution**: Can be run once or in a continuous loop for ongoing cleanup.  
* **Secure Configuration**: Supports credentials via command-line arguments or environment variables (recommended).  
* **Detailed Logging**: Creates a log file (overflow\_case\_closer.log) and provides real-time console output for monitoring and debugging.

## **Prerequisites**

Before using this script, ensure you have the following:

* **Python 3.6+**  
* The **requests** library for Python.

## **Installation**

1. **Clone or Download**: Save the script case\_closer.py to your local machine.  
2. **Install Dependencies**: Open your terminal or command prompt and install the required requests library:  
   pip install requests

## **Configuration**

The script requires two essential pieces of information to connect to the API:

* **Instance URL**: The base URL of your Siemplify instance (e.g., https://my-soar.example.com).  
* **API Key**: A valid API key generated from your Siemplify instance.

### **Using Environment Variables (Recommended)**

For better security and to avoid exposing credentials in your command history, it is highly recommended to use environment variables.

**On Linux or macOS:**

export INSTANCE\_URL="\[https://your-instance.com\](https://your-instance.com)"  
export API\_KEY="your-secret-api-key"

**On Windows (Command Prompt):**

set INSTANCE\_URL="\[https://your-instance.com\](https://your-instance.com)"  
set API\_KEY="your-secret-api-key"

Once set, the script will automatically use these values without needing command-line arguments.

## **Usage**

The script is run from the terminal. The basic structure of the command is:  
python3 case\_closer.py \[OPTIONS\]

### **Common Commands**

* Get Help  
  To see a full list of all available commands and their descriptions:  
  python3 case\_closer.py \--help

* Default Run (Close "Overflow Case")  
  This command runs the script once, searching for and closing open cases titled "Overflow Case" from the last 30 days. It assumes you have set up environment variables for the URL and API key.  
  python3 case\_closer.py

* Specify Credentials via Arguments  
  If you are not using environment variables, you can provide the URL and key directly:  
  python3 case\_closer.py \--url \[https://your-instance.com\](https://your-instance.com) \--key YOUR\_API\_KEY

* Specify a Different Case Title  
  Use the \--title flag to search for a different case.  
  python3 case\_closer.py \--title "Phishing Alert"

* Close Cases with Any Title (Use with Caution)  
  To match and close cases regardless of their title, provide an empty string to the \--title flag.  
  python3 case\_closer.py \--title ""

* Adjust the Search Window  
  Use the \--days flag to change the search window from the default of 30 days. This example searches for cases from the last 7 days.  
  python3 case\_closer.py \--days 7

* Enable Verbose Logging  
  For debugging, use the \-v or \--verbose flag to print detailed information about API requests and responses to the console.  
  python3 case\_closer.py \-v

* Run in Continuous Mode  
  To run the script on a recurring schedule, use the \--continuous flag. You can set the time between runs with \--interval (in seconds). This command runs the script every 15 minutes.  
  python3 case\_closer.py \--continuous \--interval 900

### **Putting It All Together: A Practical Example**

This command will:

* Run continuously.  
* Check every hour (3600 seconds).  
* Search for open cases titled "Suspicious Login Detected".  
* Limit the search to cases created in the last 2 days.  
* Provide detailed debug output.

python3 case\_closer.py \--continuous \--interval 3600 \--title "Suspicious Login Detected" \--days 2 \-v  
