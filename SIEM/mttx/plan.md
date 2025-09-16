# **Product Requirements Document: Google SecOps MTTx**

Author: cmmartin@	  
Date: 2025-09-01  
Version: 1.0

### **1\. Introduction & Vision**

1.1. Overview  
This document outlines the requirements for Google SecOps MTTx, a custom application that enables users of the Google SecOps platform to calculate, customize, and visualize a variety of Mean Time to X metrics.  
1.2. Problem Statement  
Currently, Google SecOps does not provide an out of the box solution for generating Mean Time To X metrics. MTTx metrics are important KPIs for MSSPs, MDRs, and Enterprises in order to have tangible data to understand if their Detection and Response strategy, content, and usage of Google SecOps is trending positive or negative towards improving their overall security posture and defence.  
1.3. Target Audience  
The application is designed for Detection Engineers, with the resultant data to be used by SOC Managers, or a CISO, in order to be able to quickly see MTTx metric data for their organization, and drive insights such as are is specific detection content delivering value, or not.

### **2\. Goals & Success Metrics**

**2.1. Business/Project Goals**

* **Goal 1:** Launch an MVP that allows users to connect to one or more Google SecOps instances and generate key MTTx metrics (MTTA, MTTC, MTTR, MTTD).  
* **Goal 2:** Empower users to define custom logic for how these metrics are calculated to fit their specific operational needs.  
* **Goal 3:** Provide a simple and effective way to persist and visualize the results, enabling trend-over-time-analysis for security leadership.

2.2. Success Metrics  
We will measure the success of this project by:

* **Metric 1: Functional Accuracy:** The application accurately generates MTTx values against Google SecOps data, validated by manual checks.  
* **Metric 2: Adoption:** At least \[e.g., 3\] internal teams or pilot users have configured the application and are generating metrics on a scheduled basis within the first month.  
* **Metric 3: Engagement:** The visualization/dashboard feature is viewed at least \[e.g., twice a week\] per user/team, indicating that the trend analysis is being actively used.  
* **Metric 4: User Feedback:** Receive positive qualitative feedback from the target users (Detection Engineers, SOC Managers) confirming that the tool provides valuable insights they previously lacked.

### **3\. Features & Requirements**

**3.1. Core Features (Must-Haves for v1.0)**

| Feature ID | Feature Name | Description | Priority |
| :---- | :---- | :---- | :---- |
| F-001 | Add SecOps Tenant | A stateful configuration that stores connection details for one or more instances of Google SecOps. | High |
| F-002 | Configure MTTx Parameters | Allow users to configure the 4 key MTTx Metrics by defining the start (Input A) and end (Input B) events to calculate the duration. | High |
| F-003 | Use SOAR Case Stages | Allow a SOAR Case Stage transition to be used as an input for an MTTx calculation. | High |
| F-004 | Use SOAR Case Tags | Allow a SOAR Case Tag addition to be used as an input for an MTTx calculation. | High |
| F-005 | Ad-hoc MTTx Analysis | The ability to generate MTTx metrics on-demand for a user-defined time range. | High |
| F-006 | Scheduled MTTx Analysis | Create and manage scheduled jobs to generate MTTx metrics automatically with user-defined time ranges and frequencies. | Medium |
| F-007 | Export to SecOps Data Tables | Ability to write or update the calculated MTTx results to a specified Google SecOps Data Table for persistence and integration. | Medium |
| F-008 | View MTTx Metrics | An interactive data table within the application to view, sort, and filter the MTTx metric results. | High |
| F-009 | Quadrant Plot Visualization | A quadrant visualization (e.g., a scatter plot) to analyze results, such as True Positive vs. False Positive counts by rule. | Medium |

**3.2. Future Features (Nice-to-Haves for later versions)**

* User authentication and role-based access control (RBAC).  
* Integration with other data sources beyond SOAR Stages/Tags.  
* Advanced alerting based on metric thresholds (e.g., if MTTA exceeds a certain value).  
* More visualization types (e.g., time-series line charts, histograms).  
* Exporting results from the UI to formats like CSV or PDF.  
* Advanced filtering and drill-down capabilities in the data table.

### **4\. Technical Specifications**

**4.1. Backend (Python)**

* **Framework:** FastAPI, SQLAlchemy, and a custom Python wrapper for the Google SecOps SDK.  
* **Database:** SQLite for simplicity and ease of setup in v1.0.  
* **API:** The backend will expose a RESTful API for managing configurations, running analyses, and retrieving results. It will interact with the Google SecOps SDK for data retrieval and export.

**4.2. Frontend**

* **Framework/Library:** React.  
* **Styling:** Tailwind CSS for rapid, utility-first styling.  
* **Key characteristic:** The frontend will be a Single Page Application (SPA) that communicates with the Python FastAPI backend.

**4.3. Deployment (Optional)**

* **Hosting:** \[e.g., Heroku, Vercel, AWS, PythonAnywhere\]

### **5\. Open Questions**

* What specific fields/events within Google SecOps are needed to define "Input A" and "Input B" for each MTTx metric?  
* How will the application handle authentication with the Google SecOps APIs? (e.g., Service Accounts, API keys).  
* For the quadrant plot, what are the exact metrics for the X and Y axes? (e.g., X=Count of Alerts, Y=Mean Time to Acknowledge).
