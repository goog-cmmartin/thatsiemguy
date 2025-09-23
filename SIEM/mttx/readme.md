# SecOps MTTx Report Generator

This application provides a comprehensive solution for calculating, visualizing, and exporting "Mean Time To X" (MTTx) metrics for a Security Operations Center (SOC). It features a FastAPI backend and a dynamic Vanilla JS and Flowbite frontend.

It connects to Google SecOps (SIEM) and a SOAR platform to fetch case and event data, processing it to provide deep insights into incident response efficiency, including Mean Time to Detect (MTTD), Acknowledge (MTTA), Contain (MTTC), and Remediate (MTTR).

## Core Features

-   **Multi-Tenant Support**: Securely manages configurations for multiple Google SecOps tenants.
-   **Customizable MTTx Metrics**: Ingests raw case history and alert data to calculate MTTD, MTTA, MTTC, and MTTR for individual cases and provides aggregated averages.
-   **Ad-hoc & Scheduled Reporting**: Perform on-demand analysis for specific time ranges or schedule recurring reports.
-   **Multiple Export Destinations**: Export generated reports as CSV files or directly into Chronicle Data Tables.
-   **Automated Dashboard Generation**: Automatically create a comprehensive SecOps dashboard from a Data Table export destination with a single click.
-   **Signal-to-Noise Analysis**: Visualize the effectiveness of detection rules with a quadrant chart, plotting signal vs. noise based on case tags.
-   **Configurable Thresholds**: Customize the color-coding for metric results to visually represent performance against SLOs.
-   **Interactive Filtering**: Dynamically filter the detailed results table by environment, detection rule, and tags.

## How it Works (UI Flow)

The frontend is organized into a stepper navigation system that guides the user through the process:

1.  **Tenants**: The first step is to configure one or more SecOps tenants, providing connection details for the SIEM and SOAR platforms.
2.  **Configurations**: For each tenant, users can customize the logic for metric calculation. This includes defining the data source queries, specifying which SOAR stages/statuses correspond to "Containment" (MTTC) and "Resolution" (MTTR), and setting the color-coded thresholds for the results.
3.  **Ad-hoc Analysis**: Users can trigger an immediate, on-demand analysis for any configured tenant by specifying a relative time range (e.g., the last 7 days).
4.  **MTTx Results**: This panel displays the results of the latest analysis. It includes cards for average metrics and completion rates, along with a detailed, sortable, and filterable table of individual case metrics.
5.  **Scheduler**: Users can create and manage scheduled jobs to automatically run the analysis and export the results to either CSV files or a Chronicle Data Table.
6.  **Signal to Noise**: This panel features a quadrant chart that helps visualize the performance of detection rules by plotting "signal" tags (e.g., True Positive) against "noise" tags (e.g., False Positive).

## Installation and Setup

1.  **Clone the repository**:
    ```bash
    git clone <repository-url>
    cd mttx
    ```
2.  **Install backend dependencies**:
    ```bash
    cd backend
    pip install -r requirements.txt
    ```
3.  **Run the backend server**:
    ```bash
    uvicorn main:app --reload --port 8000
    ```
4.  **Access the frontend**:
    Open the `frontend/index.html` file in your web browser.

## Database Schema

The application uses a SQLite database (`mttx.db`) with the following main tables:

-   `tenants`: Stores connection details for each SecOps tenant.
-   `schedules` & `schedule_destinations`: Manages scheduled reporting jobs and their export destinations (CSV or Data Table).
-   `mttx_configs`: Stores the logic for what defines "Containment" and "Remediation".
-   `metric_thresholds`: Stores the color-coding thresholds for report visualization.
-   `query_configs`: Stores the UDM queries used to fetch data.
-   `case_stages` & `case_statuses`: Caches SOAR stage and status definitions.

## API Endpoints

The backend provides a RESTful API for all frontend operations. Key endpoints include:

-   `/api/tenants`: Manage tenants (CRUD).
-   `/api/tenants/{tenant_id}/test`: Test tenant connection.
-   `/api/tenants/{tenant_id}/fetch-stages`: Get case stage definitions from SOAR.
-   `/api/tenants/{tenant_id}/mttx-configs`: Manage MTTC/MTTR logic.
-   `/api/tenants/{tenant_id}/thresholds`: Manage report color-coding thresholds.
-   `/api/tenants/{tenant_id}/queries`: Manage data source queries.
-   `/api/analysis/run`: Execute queries to fetch raw data.
-   `/api/analysis/calculate`: Process raw data to calculate MTTx metrics.
-   `/api/schedules` & `/api/destinations`: Manage scheduled reports and their destinations (CRUD).
-   `/api/schedules/{schedule_id}/run`: Trigger an immediate run of a scheduled job.
-   `/api/destinations/{destination_id}/create-dashboard`: Create a SecOps dashboard from a Data Table destination.