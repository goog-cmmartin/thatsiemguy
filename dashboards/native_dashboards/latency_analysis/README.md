# Google SecOps: Latency Analysis Dashboard

This repository contains the JSON model for a native Google SecOps (Chronicle) dashboard designed to help you analyze and diagnose both **Ingestion Latency** and **Detection Latency** within your environment.

Understanding latency is critical for any SIEM. This dashboard provides a high-level, data-driven overview to help you pinpoint:

  * Problematic log sources with high ingestion delays.
  * Log sources with clock skew or timezone misconfigurations.
  * Slow-running detection rules.
  * The cumulative impact of ingestion and enrichment delays on your alert timeliness.

[ingestion_latency.png]

## Dashboard Overview

The dashboard is split into two main sections: **Ingestion Latency** and **Detection Latency**.

## Key Features

### 1\. Ingestion Latency Widget

This widget analyzes the time difference between `metadata.event_timestamp` (when the event happened) and `metadata.ingested_timestamp` (when it arrived in SecOps).

  * **Calculates** the average latency in minutes for every `log_type`.
  * **Buckets** log counts into time-based columns (`< 0 hours`, `0-1 hours`, `1-2 hours`, `> 2 hours`) to help you instantly spot trends.
  * **Identifies Clock Skew** (`cnt_lt_0_hours` column) where logs are arriving with a future timestamp, pointing to NTP or timezone parsing errors.
  * **(Optional)** Includes advanced profiling fields (`latency_profile`, `latency_slo_minutes`, etc.) from the multi-stage YARA-L query to automatically classify sources as `realtime`, `near_realtime`, or `batch`.

### 2\. Detection Latency Widget

This widget analyzes the time difference between the *earliest event* in a detection (`eventtime_min`) and the *time the detection was created* (`detectiontime_min`).

  * **Calculates** the total detection latency in seconds, minutes, and hours for every rule.
  * **Highlights** your slowest-running rules, allowing you to prioritize optimization.
  * **Provides** all key timestamps (`eventtime_min`, `ingestiontime_min`, `detectiontime_min`) to help you diagnose *why* a detection was slow (e.g., Ingestion Latency vs. Enrichment/Rule Schedule Latency).

## How to Import the Dashboard

1.  Go to your Google SecOps instance.
2.  Navigate to **Dashboards**.
3.  In the top right, click the **three-dot menu (⋮)** and select **Import**.
4.  Select the `latency_dashboard.json` file from this repository.
5.  The "Latency Analysis" dashboard will be added to your list.

## How to Use This Dashboard

### 🕵️ Investigating Ingestion Latency

  * **Find Clock Skew:** Sort the `Ingestion Latency` widget by **`cnt_lt_0_hours`** (descending). Any `log_type` with a count greater than 0 has a misconfiguration that needs to be fixed.
  * **Find Slowest Sources:** Sort by **`average_difference_minutes`** (descending). Correlate the slow log types with their ingestion method (e.g., GCS Batch vs. Pub/Sub stream) to determine if the latency is expected or anomalous.
  * **Find Broken Feeds:** Sort by **`cnt_gt_2_hours`** (descending). This identifies sources that are consistently arriving very late, often pointing to a failing collector script or a long-running batch job.

### ⏱️ Investigating Detection Latency

  * **Find Slowest Rules:** Sort the `Detection Latency` widget by **`dl_t_hours`** (descending). This is your "worst offenders" list.
  * **Diagnose the "Why":** For a slow rule, compare the three timestamps:
      * **Gap between `eventtime_min` and `ingestiontime_min`**: This is your Ingestion Latency (`L_log`). The problem is with the data feed.
      * **Gap between `ingestiontime_min` and `detectiontime_min`**: This is your Enrichment + Detection Schedule Latency (`L_enrich` + `S_detection`). The log arrived, but it was waiting for threat intel or for the next rule run (e.g., a 1-hour schedule or a 48-hour cleanup run).

