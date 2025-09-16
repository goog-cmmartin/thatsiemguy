# MTTx Backend API

This application is a FastAPI-based backend designed to calculate and display key performance indicators (KPIs) for a Security Operations Center (SOC). It focuses on "Mean Time To X" (MTTx) metrics, such as Mean Time to Detect (MTTD), Acknowledge (MTTA), Contain (MTTC), and Remediate (MTTR).

The application connects to a security platform (like Google Chronicle, via the SecOps SDK) and a SOAR platform to fetch case and event data. It then processes this data to provide insights into incident response efficiency.

## Core Features

- **Multi-Tenant Support**: Manages configurations for multiple tenants, each with its own connection settings for Chronicle and a SOAR platform.
- **Metric Calculation**: Ingests raw case history and alert data to calculate MTTD, MTTA, MTTC, and MTTR for individual cases and provides averages across all cases.
- **Configurable Logic**: Allows customization of the UDM queries used to fetch data and the specific case stages/statuses that define the boundaries for MTTC and MTTR calculations.
- **RESTful API**: Provides a set of API endpoints to manage tenants, configurations, and trigger analysis.
- **Frontend Hosting**: Serves a static frontend for interacting with the API.

## How it Works

1.  **Configuration**: A `Tenant` is configured in the system with its unique Chronicle `guid`, `gcp_project_id`, `region`, and SOAR connection details.
2.  **Data Fetching**: The `/api/analysis/run` endpoint is called. It uses pre-configured UDM queries to fetch two main datasets from the tenant's Chronicle instance over a specified time range:
    *   **Case History**: A log of all events and changes related to cases (e.g., creation, status changes, stage changes).
    *   **Case MTTD Data**: A dataset linking cases to their underlying detection events to determine the initial detection time.
3.  **Metric Calculation**: The fetched JSON data is passed to the `/api/analysis/calculate` endpoint. This endpoint uses the `pandas` library to:
    *   Parse the raw JSON into structured DataFrames.
    *   For each case, it identifies key timestamps:
        *   **Detection Time**: The earliest event time associated with the case's alerts.
        *   **Creation Time**: When the case was created in the SOAR platform.
        *   **First Action Time**: The first recorded activity after case creation (e.g., a stage change).
        *   **Containment Time**: When the case moved to a specific, user-defined "containment" stage (e.g., "Incident").
        *   **Resolution Time**: When the case was moved to a user-defined "closed" status.
    *   It calculates the duration between these timestamps to produce the final MTTx metrics for each case.
    *   It also calculates the average metrics and completion rates across all analyzed cases.
4.  **Display**: The final calculated metrics are returned as a JSON response, ready to be displayed by a frontend.

## Database Schema

The application uses a SQLite database (`mttx.db`) with the following tables:

-   `tenants`: Stores connection and configuration details for each tenant.
-   `case_stages`: Stores SOAR case stages fetched for a specific tenant.
-   `case_statuses`: A static table mapping status names (e.g., "OPENED", "CLOSED") to their enum IDs.
-   `mttx_configs`: Stores the configuration that defines what stage or status marks the "Containment" and "Remediation" milestones.
-   `query_configs`: Stores the UDM queries used to fetch data for a tenant.

## API Endpoints

-   `GET /api/tenants`: List all configured tenants.
-   `POST /api/tenants`: Create a new tenant.
-   `PUT /api/tenants/{tenant_id}`: Update a tenant's configuration.
-   `POST /api/tenants/{tenant_id}/test`: Test the connection to a tenant's Chronicle instance.
-   `POST /api/tenants/{tenant_id}/fetch-stages`: Fetch and store case stage definitions from the tenant's SOAR platform.
-   `GET /api/tenants/{tenant_id}/stages`: Get the stored case stages for a tenant.
-   `GET /api/case-statuses`: Get all possible case statuses.
-   `GET /api/tenants/{tenant_id}/mttx-configs`: Get the MTTx calculation configurations for a tenant.
-   `PUT /api/mttx-configs/{config_id}`: Update a specific MTTx configuration.
-   `GET /api/tenants/{tenant_id}/queries`: Get the UDM queries for a tenant.
-   `PUT /api/queries/{query_id}`: Update a UDM query.
-   `POST /api/analysis/run`: Execute the queries against Chronicle to fetch raw data for analysis.
-   `POST /api/analysis/calculate`: Process the raw data and calculate the final MTTx metrics.
