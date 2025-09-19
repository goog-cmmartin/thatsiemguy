from secops import SecOpsClient
from secops.chronicle import client

client = SecOpsClient()

# Initialize Chronicle client
chronicle = client.chronicle(
    customer_id="a556547c-1cff-43ef-a2e4-cf5b12a865df",  # Your Chronicle instance ID
    project_id="sdl-preview-americas",             # Your GCP project ID
    region="us"                               # Chronicle API region 
)

# Path to the dashboard file
dashboard = {
    "dashboard": {
        "name": "ef22790e-bfb5-4c7b-a140-efadbe46b2e7",
        "displayName": "Mean Time to 1",
        "description": "@cmmartin",
        "definition": {
            "filters": [
                {
                    "id": "GlobalTimeFilter",
                    "dataSource": "GLOBAL",
                    "filterOperatorAndFieldValues": [
                        {
                            "filterOperator": "PAST",
                            "fieldValues": [
                                "1",
                                "DAY"
                            ]
                        }
                    ],
                    "displayName": "Global Time Filter",
                    "isStandardTimeRangeFilter": True,
                    "isStandardTimeRangeFilterEnabled": True
                }
            ],
            "charts": [
                {
                    "dashboardChart": "75e398e2-b779-40b0-907c-803eeaec5313",
                    "chartLayout": {
                        "startX": 17,
                        "spanX": 57,
                        "startY": 0,
                        "spanY": 12
                    }
                },
                {
                    "dashboardChart": "e3df172d-41d6-4575-a4c7-39b30369c84e",
                    "chartLayout": {
                        "startX": 17,
                        "spanX": 57,
                        "startY": 12,
                        "spanY": 12
                    }
                },
                {
                    "dashboardChart": "33599b2a-fbd1-4dd9-be08-80a16eb98237",
                    "chartLayout": {
                        "startX": 4,
                        "spanX": 90,
                        "startY": 24,
                        "spanY": 47
                    }
                }
            ]
        },
        "type": "CUSTOM",
        "etag": "dd24d78565b9d47225d37b53ce1b5e3dabc11092fd793e925ddcc47a8557d10e",
        "access": "DASHBOARD_PRIVATE"
    },
    "dashboardCharts": [
    {
        "name": "75e398e2-b779-40b0-907c-803eeaec5313",
        "displayName": "Average MTTx Metrics",
        "chartDatasource": {
            "dashboardQuery": "944c229d-f6c9-4325-8521-97fc4e6c0db7",
            "dataSources": [
                "DATA_TABLE"
            ]
        },
        "visualization": {
            "xAxes": [
                {
                    "axisType": "VALUE"
                }
            ],
            "yAxes": [
                {
                    "axisType": "VALUE"
                }
            ],
            "legends": [
                {
                    "legendOrient": "HORIZONTAL"
                }
            ],
            "columnDefs": [
                {
                    "field": "tenant",
                    "header": "tenant"
                },
                {
                    "field": "date",
                    "header": "date"
                },
                {
                    "field": "mtta",
                    "header": "mtta"
                },
                {
                    "field": "mttc",
                    "header": "mttc"
                },
                {
                    "field": "mttr",
                    "header": "mttr"
                },
                {
                    "field": "mttd",
                    "header": "mttd"
                }
            ],
            "groupingType": "Off",
            "tableConfig": {}
        },
        "tileType": "TILE_TYPE_VISUALIZATION",
        "etag": "8b63a3d7d75abd3ee14c8dea75779b73eb3d853aff9f4d95f1009a76e049950f",
        "drillDownConfig": {}
    },
    {
        "name": "e3df172d-41d6-4575-a4c7-39b30369c84e",
        "displayName": "MTTx Completion Rates",
        "chartDatasource": {
            "dashboardQuery": "c03748d7-365b-4451-9ba8-bf04914cac67",
            "dataSources": [
                "DATA_TABLE"
            ]
        },
        "visualization": {
            "xAxes": [
                {
                    "axisType": "VALUE"
                }
            ],
            "yAxes": [
                {
                    "axisType": "VALUE"
                }
            ],
            "legends": [
                {
                    "legendOrient": "HORIZONTAL"
                }
            ],
            "columnDefs": [
                {
                    "field": "tenant",
                    "header": "tenant"
                },
                {
                    "field": "date",
                    "header": "date"
                },
                {
                    "field": "MTTA_completion_percent",
                    "header": "MTTA_completion_percent"
                },
                {
                    "field": "MTTC_completion_percent",
                    "header": "MTTC_completion_percent"
                },
                {
                    "field": "MTTR_completion_percent",
                    "header": "MTTR_completion_percent"
                },
                {
                    "field": "MTTD_completion_percent",
                    "header": "MTTD_completion_percent"
                }
            ],
            "groupingType": "Off",
            "tableConfig": {}
        },
        "tileType": "TILE_TYPE_VISUALIZATION",
        "etag": "746340a21e18cc06feb6765fe806900480e493b01508aa35dabd5fbbeccb73f5",
        "drillDownConfig": {}
    },
    {
        "name": "33599b2a-fbd1-4dd9-be08-80a16eb98237",
        "displayName": "Case Level MTTx Metrics",
        "chartDatasource": {
            "dashboardQuery": "1be9e167-9710-42ff-8903-ca079503498d",
            "dataSources": [
                "DATA_TABLE"
            ]
        },
        "visualization": {
            "xAxes": [
                {
                    "axisType": "VALUE"
                }
            ],
            "yAxes": [
                {
                    "axisType": "VALUE"
                }
            ],
            "legends": [
                {
                    "legendOrient": "HORIZONTAL"
                }
            ],
            "columnDefs": [
                {
                    "field": "tenant",
                    "header": "tenant"
                },
                {
                    "field": "date",
                    "header": "date"
                },
                {
                    "field": "case_id",
                    "header": "case_id"
                },
                {
                    "field": "MTTD",
                    "header": "MTTD"
                },
                {
                    "field": "MTTA",
                    "header": "MTTA"
                },
                {
                    "field": "MTTR",
                    "header": "MTTR"
                },
                {
                    "field": "MTTC",
                    "header": "MTTC"
                }
            ],
            "groupingType": "Off",
            "tableConfig": {}
        },
        "tileType": "TILE_TYPE_VISUALIZATION",
        "etag": "9a166139df025a37275d8f34eb1838f55ed29f0fe1b11bea6e3e264f7eee8bf9",
        "drillDownConfig": {}
    }],
    "dashboardQueries":[
    {
        "name": "944c229d-f6c9-4325-8521-97fc4e6c0db7",
        "query": "$tenant = %mttx_schedule_1_average_metrics.tenant_name\n$date = %mttx_schedule_1_average_metrics.export_datetime\n$mtta = %mttx_schedule_1_average_metrics.Average_MTTA_seconds\n$mttc = %mttx_schedule_1_average_metrics.Average_MTTC_seconds\n$mttr = %mttx_schedule_1_average_metrics.Average_MTTR_seconds\n$mttd = %mttx_schedule_1_average_metrics.Average_MTTD_seconds\nmatch: $tenant, $date, $mtta, $mttc, $mttr, $mttd",
        "input": {
            "relativeTime": {
                "timeUnit": "DAY",
                "startTimeVal": "7"
            }
        },
        "etag": "628529b6bfb4666c6725b3f2a5fb873f82227b26ab42bfaaafa2a7cb7a03d575"
    },
    {
        "name": "c03748d7-365b-4451-9ba8-bf04914cac67",
        "query": "$tenant = %mttx_schedule_1_completion_rates.tenant_name\n$date = %mttx_schedule_1_completion_rates.export_datetime\n$MTTA_completion_percent = %mttx_schedule_1_completion_rates.MTTA_completion_percent\n$MTTC_completion_percent = %mttx_schedule_1_completion_rates.MTTC_completion_percent\n$MTTR_completion_percent = %mttx_schedule_1_completion_rates.MTTR_completion_percent\n$MTTD_completion_percent = %mttx_schedule_1_completion_rates.MTTD_completion_percent\nmatch: $tenant, $date, $MTTA_completion_percent, $MTTC_completion_percent, $MTTR_completion_percent, $MTTD_completion_percent ",
        "input": {
            "relativeTime": {
                "timeUnit": "DAY",
                "startTimeVal": "1"
            }
        },
        "etag": "ad364e878d94847b2403414ad73a30113142aa79e13cfb0d840ae3d77abfb616"
    },
    {
        "name": "1be9e167-9710-42ff-8903-ca079503498d",
        "query": "$tenant = %mttx_schedule_1_individual_cases.tenant_name\n$date = %mttx_schedule_1_individual_cases.export_datetime\n$case_id = %mttx_schedule_1_individual_cases.case_id\n$MTTD = %mttx_schedule_1_individual_cases.MTTD\n$MTTA = %mttx_schedule_1_individual_cases.MTTA\n$MTTR = %mttx_schedule_1_individual_cases.MTTR\n$MTTC = %mttx_schedule_1_individual_cases.MTTC\nmatch: $tenant, $date, $case_id, $MTTD, $MTTA, $MTTR, $MTTC",
        "input": {
            "relativeTime": {
                "timeUnit": "DAY",
                "startTimeVal": "1"
            }
        },
        "etag": "a25381368cc12f4c90e2e8e285c478b635b1497dd553e58110f0c1d895716d0c"
    }
    ]
}

import os
import json
with open(os.path.join(os.path.dirname(__file__), 'debug3.txt'), 'w') as debug_file:
    debug_file.write(json.dumps(dashboard, indent=2))


# Import the dashboard
try:
    new_dashboard = chronicle.import_dashboard(dashboard)
    print(new_dashboard)
except Exception as e:
    print(f"An error occurred: {e}")

