# **Product Requirements Document: Google SecOps MTTx**

Author: cmmartin@
Date: 2025-09-22
Version: 2.0

### **1\. Introduction & Vision**

1.1. Overview
This document outlines the requirements for Google SecOps MTTx, a custom application that enables users of the Google SecOps platform to calculate, customize, and visualize a variety of Mean Time to X metrics.
1.2. Problem Statement
Currently, Google SecOps does not provide an out-of-the-box solution for generating Mean Time To X metrics. MTTx metrics are important KPIs for MSSPs, MDRs, and Enterprises to have tangible data to understand if their Detection and Response strategy, content, and usage of Google SecOps is trending positively or negatively towards improving their overall security posture and defense.
1.3. Target Audience
The application is designed for Detection Engineers, with the resultant data to be used by SOC Managers, or a CISO, to quickly see MTTx metric data for their organization and drive insights, such as whether specific detection content is delivering value.

### **2\. Goals & Success Metrics**

**2.1. Business/Project Goals**

*   **Goal 1:** Launch an application that allows users to connect to one or more Google SecOps instances and generate key MTTx metrics (MTTA, MTTC, MTTR, MTTD).
*   **Goal 2:** Empower users to define custom logic for how these metrics are calculated to fit their specific operational needs.
*   **Goal 3:** Provide a simple and effective way to persist and visualize the results, enabling trend-over-time-analysis for security leadership.

2.2. Success Metrics
We will measure the success of this project by:

*   **Metric 1: Functional Accuracy:** The application accurately generates MTTx values against Google SecOps data, validated by manual checks.
*   **Metric 2: Adoption:** At least [e.g., 3] internal teams or pilot users have configured the application and are generating metrics on a scheduled basis within the first month.
*   **Metric 3: Engagement:** The visualization/dashboard feature is viewed at least [e.g., twice a week] per user/team, indicating that the trend analysis is being actively used.
*   **Metric 4: User Feedback:** Receive positive qualitative feedback from the target users (Detection Engineers, SOC Managers) confirming that the tool provides valuable insights they previously lacked.

### **3\. Features & Requirements**

**3.1. Core Features**

| Feature ID | Feature Name | Description | Priority |
| :--- | :--- | :--- | :--- |
| F-001 | Multi-Tenant Configuration | A stateful configuration that stores connection details for one or more instances of Google SecOps. | High |
| F-002 | Customizable MTTx Logic | Users can configure the logic for MTTC and MTTR by selecting specific SOAR case stages or statuses as the trigger points. | High |
| F-003 | Ad-hoc MTTx Analysis | Generate MTTx metrics on-demand for a user-defined time range. | High |
| F-004 | Scheduled Reporting | Create and manage scheduled jobs to generate and export MTTx metrics automatically with user-defined frequencies. | High |
| F-005 | Multiple Export Destinations | Scheduled jobs can export results to local CSV files or directly to a Google SecOps Data Table. | High |
| F-006 | Interactive Results Grid | View, sort, and filter detailed MTTx metrics for individual cases. Filtering is available for environment, rule name, and tags. | High |
| F-007 | Signal-to-Noise Chart | A quadrant plot visualization to analyze detection rule effectiveness by plotting "signal" tags (e.g., True Positive) vs. "noise" tags (e.g., False Positive). | High |
| F-008 | Automated Dashboard Creation | Generate a pre-defined Google SecOps dashboard from a Data Table export destination with a single click. | Medium |
| F-009 | Configurable Thresholds | Customize the color-coding (Good, Ok, Bad) for metric results to visually represent performance against SLOs. | Medium |

**3.2. Future Features (Post v2.0)**

*   User authentication and role-based access control (RBAC).
*   Integration with other data sources beyond SOAR Stages/Tags.
*   Advanced alerting based on metric thresholds (e.g., if MTTA exceeds a certain value).
*   More visualization types (e.g., time-series line charts, histograms).

### **4\. Technical Specifications**

**4.1. Backend (Python)**

*   **Framework:** FastAPI, SQLAlchemy.
*   **Database:** SQLite for simplicity and ease of setup.
*   **API:** The backend exposes a RESTful API for managing configurations, running analyses, and retrieving results. It interacts directly with the Google SecOps SDK for data retrieval and export.

**4.2. Frontend**

*   **Framework/Library:** Vanilla JavaScript.
*   **Styling:** Flowbite and custom CSS for a modern, responsive UI.
*   **Key characteristic:** The frontend is a Single Page Application (SPA) that communicates with the Python FastAPI backend.

### **5\. Answered Questions**

*   **What specific fields/events define MTTx metrics?**
    *   **MTTD:** `case.create_time` - `case.alerts.metadata...event.metadata.event_timestamp`
    *   **MTTA:** First `case_history.stage` change time - `case_history.create_time`
    *   **MTTC/MTTR:** Time of user-defined stage/status change - First `case_history.stage` change time. This is configurable in the UI.
*   **How does the application handle authentication?**
    *   **Google SecOps SIEM:** The backend server uses `GOOGLE_APPLICATION_CREDENTIALS`, requiring a service account with appropriate permissions.
    *   **Google SecOps SOAR:** A SOAR API key with Admin permissions is required and stored per-tenant.
*   **What are the metrics for the quadrant plot?**
    *   The X and Y axes are based on the count of cases that have user-selected "Signal" tags vs. "Noise" tags. The size of each bubble represents the total volume of alerts for that detection rule.
