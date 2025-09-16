import os
import uvicorn
import logging
import json
import pandas as pd
import numpy as np
import requests
from datetime import datetime, timezone
from fastapi import FastAPI, Depends, HTTPException, APIRouter
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, Integer, String, Boolean, ForeignKey, Text
from sqlalchemy.orm import sessionmaker, Session, relationship
from sqlalchemy.ext.declarative import declarative_base
from pydantic import BaseModel, field_validator
from typing import List, Dict, Any, Optional

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- SDK Import ---
try:
    from secops import SecOpsClient
    SECOPS_SDK_AVAILABLE = True
except ImportError:
    SECOPS_SDK_AVAILABLE = False
    logging.warning("SecOps SDK not found. /test and /analysis endpoints will be disabled.")

# --- Database Setup ---
DATABASE_URL = "sqlite:///./mttx.db"
Base = declarative_base()
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# --- SQLAlchemy Models ---
class Tenant(Base):
    __tablename__ = "tenants"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    guid = Column(String, unique=True, index=True, nullable=False)
    region = Column(String, nullable=False)
    gcp_project_id = Column(String, nullable=False)
    base_url = Column(String, nullable=True)
    soar_url = Column(String, nullable=True)
    soar_api_key = Column(String, nullable=True)
    
    stages = relationship("CaseStage", back_populates="tenant", cascade="all, delete-orphan")
    configs = relationship("MTTxConfig", back_populates="tenant", cascade="all, delete-orphan")
    queries = relationship("QueryConfig", back_populates="tenant", cascade="all, delete-orphan")
    schedules = relationship("Schedule", back_populates="tenant", cascade="all, delete-orphan")

class Schedule(Base):
    __tablename__ = "schedules"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    cron_schedule = Column(String, nullable=False)
    time_unit = Column(String, nullable=False, default="DAY")
    start_time_val = Column(Integer, nullable=False, default=1)
    output_avg_metrics = Column(Boolean, default=True)
    output_completion_rates = Column(Boolean, default=True)
    output_individual_cases = Column(Boolean, default=False)
    is_enabled = Column(Boolean, default=True)

    tenant = relationship("Tenant", back_populates="schedules")
    destinations = relationship("ScheduleDestination", back_populates="schedule", cascade="all, delete-orphan")

class ScheduleDestination(Base):
    __tablename__ = "schedule_destinations"
    id = Column(Integer, primary_key=True, index=True)
    schedule_id = Column(Integer, ForeignKey("schedules.id"), nullable=False)
    destination_type = Column(String, nullable=False, default="CSV") # e.g., CSV, WEBHOOK, EMAIL
    path = Column(String, nullable=True) # For CSV, this is the file path
    is_enabled = Column(Boolean, default=True)

    schedule = relationship("Schedule", back_populates="destinations")

class CaseStage(Base):
    __tablename__ = "case_stages"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    soar_id = Column(Integer)
    tenant_id = Column(Integer, ForeignKey("tenants.id"))

    tenant = relationship("Tenant", back_populates="stages")

class CaseStatus(Base):
    __tablename__ = "case_statuses"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    enum_id = Column(Integer, unique=True)

class MTTxConfig(Base):
    __tablename__ = "mttx_configs"
    id = Column(Integer, primary_key=True, index=True)
    metric_type = Column(String, index=True)
    config_key = Column(String)
    config_value = Column(String)
    tenant_id = Column(Integer, ForeignKey("tenants.id"))

    tenant = relationship("Tenant", back_populates="configs")

class QueryConfig(Base):
    __tablename__ = "query_configs"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True) 
    query_text = Column(Text)
    tenant_id = Column(Integer, ForeignKey("tenants.id"))

    tenant = relationship("Tenant", back_populates="queries")


Base.metadata.create_all(bind=engine)

# --- Pydantic Schemas ---
class TenantBase(BaseModel):
    name: str
    guid: str
    region: str
    gcp_project_id: str
    base_url: Optional[str] = None
    soar_url: Optional[str] = None
    soar_api_key: Optional[str] = None
    
    @field_validator('base_url', 'soar_url')
    def clean_urls(cls, v):
        if v:
            return v.strip().rstrip('/')
        return v

class TenantCreate(TenantBase): pass
class TenantUpdate(TenantBase): pass

class CaseStageResponse(BaseModel):
    id: int
    name: str
    soar_id: int
    class Config: from_attributes = True

class CaseStatusResponse(BaseModel):
    id: int
    name: str
    enum_id: int
    class Config: from_attributes = True

class TenantResponse(TenantBase):
    id: int
    class Config: from_attributes = True

class MTTxConfigUpdate(BaseModel):
    config_key: str
    config_value: str

class MTTxConfigResponse(BaseModel):
    id: int
    metric_type: str
    config_key: str
    config_value: str
    tenant_id: int
    class Config: from_attributes = True

class QueryConfigUpdate(BaseModel):
    query_text: str

class QueryConfigResponse(BaseModel):
    id: int
    name: str
    query_text: str
    tenant_id: int
    class Config: from_attributes = True

class AnalysisRequest(BaseModel):
    tenant_id: int
    time_unit: str
    start_time_val: int
    
class CalculationRequest(BaseModel):
    tenant_id: int
    case_history_data: Dict[str, Any]
    case_mttd_data: Dict[str, Any]

class TestConnectionResponse(BaseModel):
    status: str
    message: str

class MetricsResponse(BaseModel):
    individual_cases: Dict[str, Any]
    average_metrics: Dict[str, Any]
    completion_rates: Dict[str, Any]
    base_url: Optional[str] = None

class FetchStagesResponse(BaseModel):
    status: str
    message: str
    stages_fetched: int

class ScheduleBase(BaseModel):
    cron_schedule: str
    time_unit: str = "DAY"
    start_time_val: int = 1
    output_avg_metrics: bool = True
    output_completion_rates: bool = True
    output_individual_cases: bool = False
    is_enabled: bool = True

class ScheduleCreate(ScheduleBase):
    tenant_id: int

class ScheduleUpdate(ScheduleBase):
    pass

class ScheduleResponse(ScheduleBase):
    id: int
    tenant_id: int

    class Config:
        from_attributes = True

class ScheduleDestinationBase(BaseModel):
    destination_type: str = "CSV"
    path: Optional[str] = None
    is_enabled: bool = True

class ScheduleDestinationCreate(ScheduleDestinationBase):
    schedule_id: int

class ScheduleDestinationUpdate(ScheduleDestinationBase):
    pass

class ScheduleDestinationResponse(ScheduleDestinationBase):
    id: int
    schedule_id: int

    class Config:
        from_attributes = True


# --- FastAPI App Setup ---
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
api_router = APIRouter()

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()
        
def seed_case_statuses(db: Session):
    statuses = {0: "UNSPECIFIED", 1: "OPENED", 2: "CLOSED", 3: "ALL", 4: "MERGED", 5: "CREATION_PENDING"}
    if db.query(CaseStatus).count() == 0:
        for enum_id, name in statuses.items():
            db.add(CaseStatus(name=name, enum_id=enum_id))
        db.commit()

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import atexit

# --- Scheduler Setup ---
scheduler = BackgroundScheduler()

def run_scheduled_analysis(tenant_id: int, schedule_id: int):
    """Function to be executed by the scheduler."""
    logging.info(f"Running scheduled analysis for tenant_id: {tenant_id}, schedule_id: {schedule_id}")
    db = SessionLocal()
    try:
        schedule = db.query(Schedule).filter(Schedule.id == schedule_id).first()
        if not schedule or not schedule.is_enabled:
            logging.info(f"Schedule {schedule_id} is disabled or not found. Skipping.")
            return
        
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if not tenant:
            logging.error(f"Tenant {tenant_id} not found for schedule {schedule_id}.")
            return

        analysis_data = perform_analysis(
            tenant_id=tenant_id, 
            time_unit=schedule.time_unit, 
            start_time_val=schedule.start_time_val, 
            db=db
        )
        
        metrics = calculate_soc_metrics_structured(
            case_history_data=analysis_data['case_history_data'],
            case_mttd_data=analysis_data['case_mttd_data'],
            db=db,
            tenant_id=tenant_id
        )
        
        if not metrics:
            logging.warning(f"Metric calculation returned no data for tenant {tenant_id}, schedule {schedule_id}.")
            return

        output = {}
        if schedule.output_avg_metrics:
            output['average_metrics'] = metrics.get('average_metrics')
        if schedule.output_completion_rates:
            output['completion_rates'] = metrics.get('completion_rates')
        if schedule.output_individual_cases:
            output['individual_cases'] = metrics.get('individual_cases')
            
        logging.info(f"Scheduled run output for schedule {schedule_id}:\n{json.dumps(output, indent=2)}")

        # Handle destinations
        for dest in schedule.destinations:
            if dest.is_enabled and dest.destination_type == 'CSV' and dest.path:
                try:
                    base_path, extension = os.path.splitext(dest.path)
                    output_dir = os.path.dirname(dest.path)
                    if not os.path.exists(output_dir):
                        os.makedirs(output_dir)
                    
                    export_dt = datetime.now(timezone.utc).isoformat()
                    tenant_name = tenant.name

                    if schedule.output_avg_metrics:
                        df_avg = pd.DataFrame([metrics.get('average_metrics')])
                        if not df_avg.empty:
                            df_avg['tenant_name'] = tenant_name
                            df_avg['export_datetime'] = export_dt
                            file_path = f"{base_path}_average_metrics{extension}"
                            df_avg.to_csv(file_path, index=False)
                            logging.info(f"Successfully wrote average_metrics CSV for schedule {schedule_id} to {file_path}")

                    if schedule.output_completion_rates:
                        df_comp = pd.DataFrame([metrics.get('completion_rates')])
                        if not df_comp.empty:
                            df_comp['tenant_name'] = tenant_name
                            df_comp['export_datetime'] = export_dt
                            file_path = f"{base_path}_completion_rates{extension}"
                            df_comp.to_csv(file_path, index=False)
                            logging.info(f"Successfully wrote completion_rates CSV for schedule {schedule_id} to {file_path}")

                    if schedule.output_individual_cases:
                        df_ind = pd.DataFrame.from_dict(metrics.get('individual_cases', {}), orient='index')
                        if not df_ind.empty:
                            df_ind['tenant_name'] = tenant_name
                            df_ind['export_datetime'] = export_dt
                            file_path = f"{base_path}_individual_cases{extension}"
                            df_ind.to_csv(file_path, index_label="case_id")
                            logging.info(f"Successfully wrote individual_cases CSV for schedule {schedule_id} to {file_path}")

                except Exception as e:
                    logging.error(f"Failed to write CSV for schedule {schedule_id} to {dest.path}: {e}", exc_info=True)

    except Exception as e:
        logging.error(f"Error during scheduled analysis for tenant {tenant_id}, schedule {schedule_id}: {e}", exc_info=True)
    finally:
        db.close()

def setup_scheduler(db: Session):
    """Initializes the scheduler and adds jobs from the database."""
    schedules = db.query(Schedule).filter(Schedule.is_enabled == True).all()
    for schedule in schedules:
        scheduler.add_job(
            run_scheduled_analysis,
            trigger=CronTrigger.from_crontab(schedule.cron_schedule),
            args=[schedule.tenant_id, schedule.id],
            id=str(schedule.id),
            replace_existing=True
        )
    if not scheduler.running:
        scheduler.start()
        atexit.register(lambda: scheduler.shutdown())

@app.on_event("startup")
def on_startup():
    with SessionLocal() as db:
        seed_case_statuses(db)
        setup_scheduler(db)


# --- Data Processing Functions ---
def json_to_dataframe(json_data: Dict[str, Any]) -> pd.DataFrame:
    results = json_data.get('results', [])
    if not results or not any(res.get('values') for res in results):
        return pd.DataFrame()
    
    headers = [res.get('column', 'Unknown') for res in results]
    num_rows = len(results[0].get('values', []))
    
    data_for_df = {header: [None] * num_rows for header in headers}

    for col_idx, res in enumerate(results):
        header = headers[col_idx]
        values = res.get('values', [])
        
        for row_idx in range(num_rows):
            if row_idx < len(values):
                item_dict = values[row_idx]
                
                if 'list' in item_dict and isinstance(item_dict['list'].get('values'), list):
                    tag_list = []
                    for tag_item in item_dict['list']['values']:
                        value_key = next((k for k in tag_item if k != 'metadata'), None)
                        if value_key and tag_item[value_key]:
                            tag_list.append(tag_item[value_key])
                    data_for_df[header][row_idx] = tag_list
                    
                elif 'value' in item_dict:
                    inner_val_dict = item_dict.get('value', {})
                    if inner_val_dict:
                        value_key = next((k for k in inner_val_dict if k != 'metadata'), None)
                        if value_key:
                            data_for_df[header][row_idx] = inner_val_dict[value_key]
    
    return pd.DataFrame(data_for_df)

def calculate_soc_metrics_structured(
    case_history_data: Dict[str, Any], 
    case_mttd_data: Dict[str, Any], 
    db: Session, 
    tenant_id: int
) -> Dict[str, Any]:
    
    df_mttd = json_to_dataframe(case_mttd_data)
    df_history = json_to_dataframe(case_history_data)

    if df_mttd.empty or df_history.empty:
        return {}

    valid_case_ids = df_mttd['case_id'].unique()
    df_history_filtered = df_history[df_history['case_history_case_id'].isin(valid_case_ids)]

    if df_history_filtered.empty:
        return {}

    df_history_filtered['case_history_case_event_time'] = pd.to_numeric(df_history_filtered['case_history_case_event_time'])
    case_ids = df_history_filtered['case_history_case_id'].unique()
    total_cases = len(case_ids)
    
    configs_db = db.query(MTTxConfig).filter(MTTxConfig.tenant_id == tenant_id).all()
    configs = {c.metric_type: c for c in configs_db}
    mttc_config = configs.get("MTTC", MTTxConfig(config_key="case_history_stage", config_value="Incident"))
    mttr_config = configs.get("MTTR", MTTxConfig(config_key="case_history_status", config_value="CLOSED"))

    individual_case_metrics = {}
    mtta_values, mttc_values, mttr_values = [], [], []

    for case_id in case_ids:
        case_df = df_history_filtered[df_history_filtered['case_history_case_id'] == case_id].sort_values(by='case_history_case_event_time')
        results = {}
        create_events = case_df[case_df['case_history_case_activity'] == 'CREATE_CASE']
        if create_events.empty: continue
        
        time_created = create_events['case_history_case_event_time'].iloc[0]
        stage_changes = case_df[(case_df['case_history_case_activity'] == 'STAGE_CHANGE') & (case_df['case_history_case_event_time'] > time_created)]
        time_first_action = stage_changes['case_history_case_event_time'].min()
        time_contained = case_df[case_df[mttc_config.config_key] == mttc_config.config_value]['case_history_case_event_time'].min()
        time_closed = case_df[case_df[mttr_config.config_key] == mttr_config.config_value]['case_history_case_event_time'].min()

        results['MTTA'] = int(time_first_action - time_created) if pd.notna(time_first_action) else '-'
        if pd.notna(time_first_action): mtta_values.append(time_first_action - time_created)
        
        results['MTTC'] = int(time_contained - time_first_action) if pd.notna(time_contained) and pd.notna(time_first_action) else '-'
        if pd.notna(time_contained) and pd.notna(time_first_action): mttc_values.append(time_contained - time_first_action)
            
        results['MTTR'] = int(time_closed - time_first_action) if pd.notna(time_closed) and pd.notna(time_first_action) else '-'
        if pd.notna(time_closed) and pd.notna(time_first_action): mttr_values.append(time_closed - time_first_action)
        
        individual_case_metrics[case_id] = results
        
    mttd_values = []
    if not df_mttd.empty:
        df_mttd['created_time'] = pd.to_numeric(df_mttd['created_time'])
        df_mttd['min_event_ts'] = pd.to_numeric(df_mttd['min_event_ts'])
        df_mttd['mttd_seconds'] = df_mttd['created_time'] - df_mttd['min_event_ts']
        
        for index, row in df_mttd.iterrows():
            case_id = row['case_id']
            if case_id in individual_case_metrics:
                mttd = row['mttd_seconds']
                individual_case_metrics[case_id]['tags'] = row.get('tags', []) if isinstance(row.get('tags'), list) else []
                individual_case_metrics[case_id]['environment'] = row.get('environment', 'Unknown')
                individual_case_metrics[case_id]['detection_rule_name'] = row.get('detection_rule_name', 'Unknown')
                if pd.notna(mttd) and mttd >= 0:
                    individual_case_metrics[case_id]['MTTD'] = int(mttd)
                    mttd_values.append(mttd)
                else:
                    individual_case_metrics[case_id]['MTTD'] = '-'
    
    for case_id in individual_case_metrics:
        if 'MTTD' not in individual_case_metrics[case_id]: individual_case_metrics[case_id]['MTTD'] = '-'
        if 'tags' not in individual_case_metrics[case_id]: individual_case_metrics[case_id]['tags'] = []
        if 'environment' not in individual_case_metrics[case_id]: individual_case_metrics[case_id]['environment'] = 'Unknown'
        if 'detection_rule_name' not in individual_case_metrics[case_id]: individual_case_metrics[case_id]['detection_rule_name'] = 'Unknown'

    avg_mtta, avg_mttc, avg_mttr, avg_mttd = (np.mean(vals) if vals else 0 for vals in [mtta_values, mttc_values, mttr_values, mttd_values])
    comp_mtta, comp_mttc, comp_mttr, comp_mttd = ((len(vals) / total_cases) * 100 if total_cases > 0 else 0 for vals in [mtta_values, mttc_values, mttr_values, mttd_values])

    return {
        "individual_cases": individual_case_metrics,
        "average_metrics": {"Average_MTTA_seconds": int(avg_mtta), "Average_MTTC_seconds": int(avg_mttc), "Average_MTTR_seconds": int(avg_mttr), "Average_MTTD_seconds": int(avg_mttd)},
        "completion_rates": {"MTTA_completion_percent": round(comp_mtta, 2), "MTTC_completion_percent": round(comp_mttc, 2), "MTTR_completion_percent": round(comp_mttr, 2), "MTTD_completion_percent": round(comp_mttd, 2), "total_cases": total_cases}
    }


# --- API Endpoints ---
@api_router.get("/tenants", response_model=List[TenantResponse])
def read_tenants(db: Session = Depends(get_db)): return db.query(Tenant).all()
@api_router.post("/tenants", response_model=TenantResponse, status_code=201)
def create_tenant(tenant: TenantCreate, db: Session = Depends(get_db)):
    db_tenant = Tenant(**tenant.model_dump())
    db.add(db_tenant)
    db.commit()
    db.refresh(db_tenant)
    return db_tenant

@api_router.put("/tenants/{tenant_id}", response_model=TenantResponse)
def update_tenant(tenant_id: int, tenant: TenantUpdate, db: Session = Depends(get_db)):
    db_tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not db_tenant: raise HTTPException(status_code=404, detail="Tenant not found")
    for key, value in tenant.model_dump(exclude_unset=True).items():
        setattr(db_tenant, key, value)
    db.commit()
    db.refresh(db_tenant)
    return db_tenant

@api_router.post("/tenants/{tenant_id}/test", response_model=TestConnectionResponse)
def test_tenant_connection(tenant_id: int, db: Session = Depends(get_db)):
    if not SECOPS_SDK_AVAILABLE: raise HTTPException(status_code=501, detail="SecOps SDK not installed.")
    db_tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not db_tenant: raise HTTPException(status_code=404, detail="Tenant not found")
    try:
        client = SecOpsClient()
        chronicle = client.chronicle(customer_id=db_tenant.guid, project_id=db_tenant.gcp_project_id, region=db_tenant.region)
        chronicle.list_feeds()
        return {"status": "success", "message": "Connection successful."}
    except Exception as e:
        return {"status": "failed", "message": str(e)}

@api_router.post("/tenants/{tenant_id}/fetch-stages", response_model=FetchStagesResponse)
def fetch_and_store_stages(tenant_id: int, db: Session = Depends(get_db)):
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant or not tenant.soar_url or not tenant.soar_api_key:
        raise HTTPException(status_code=400, detail="Tenant not found or SOAR not configured.")
    api_url = f"{tenant.soar_url.rstrip('/')}/api/external/v1/settings/GetCaseStageDefinitionRecords"
    headers = {'AppKey': tenant.soar_api_key, 'Content-Type': 'application/json'}
    try:
        response = requests.post(api_url, headers=headers, json={"pageSize": 100}, timeout=10)
        response.raise_for_status()
        stages = response.json().get("objectsList", [])
        db.query(CaseStage).filter(CaseStage.tenant_id == tenant_id).delete()
        for stage in stages:
            db.add(CaseStage(name=stage.get("name"), soar_id=stage.get("id"), tenant_id=tenant_id))
        db.commit()
        return {"status": "success", "message": f"Fetched {len(stages)} stages.", "stages_fetched": len(stages)}
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"SOAR API connection failed: {e}")

@api_router.get("/tenants/{tenant_id}/stages", response_model=List[CaseStageResponse])
def get_tenant_stages(tenant_id: int, db: Session = Depends(get_db)):
    return db.query(CaseStage).filter(CaseStage.tenant_id == tenant_id).all()

@api_router.get("/case-statuses", response_model=List[CaseStatusResponse])
def get_case_statuses(db: Session = Depends(get_db)): return db.query(CaseStatus).all()

@api_router.get("/tenants/{tenant_id}/mttx-configs", response_model=List[MTTxConfigResponse])
def get_mttx_configs(tenant_id: int, db: Session = Depends(get_db)):
    configs = db.query(MTTxConfig).filter(MTTxConfig.tenant_id == tenant_id).all()
    if not configs:
        default_configs_data = [
            {"metric_type": "MTTC", "config_key": "case_history_stage", "config_value": "Incident", "tenant_id": tenant_id},
            {"metric_type": "MTTR", "config_key": "case_history_status", "config_value": "CLOSED", "tenant_id": tenant_id}
        ]
        new_configs = [MTTxConfig(**d) for d in default_configs_data]
        db.add_all(new_configs)
        db.commit()
        return new_configs
    return configs

@api_router.put("/mttx-configs/{config_id}", response_model=MTTxConfigResponse)
def update_mttx_config(config_id: int, config: MTTxConfigUpdate, db: Session = Depends(get_db)):
    db_config = db.query(MTTxConfig).filter(MTTxConfig.id == config_id).first()
    if not db_config: raise HTTPException(status_code=404, detail="Configuration not found")
    db_config.config_key = config.config_key
    db_config.config_value = config.config_value
    db.commit()
    db.refresh(db_config)
    return db_config

@api_router.get("/tenants/{tenant_id}/queries", response_model=List[QueryConfigResponse])
def get_queries(tenant_id: int, db: Session = Depends(get_db)):
    queries = db.query(QueryConfig).filter(QueryConfig.tenant_id == tenant_id).all()
    if not queries:
        default_query_history = """
$case_history_case_id = case_history.case_response_platform_info.case_id
$case_history_case_activity = case_history.case_activity
$case_history_case_event_time = case_history.event_time.seconds
$case_history_stage = case_history.stage
$case_history_status = case_history.status
match: $case_history_case_id, $case_history_case_activity, $case_history_case_event_time, $case_history_stage, $case_history_status
order: $case_history_case_id desc
limit: 1000
"""
        default_query_case = """
$case_id = case.response_platform_info.response_platform_id
$created_time = case.create_time.seconds
$environment = case.environment
cast.as_int(case.alerts.metadata.collection_elements.references.event.metadata.event_timestamp.seconds) > 0
$detection_rule_name = case.alerts.metadata.detection.rule_name
match: $case_id, $environment, $created_time, $detection_rule_name
outcome: 
    $min_event_ts = min(case.alerts.metadata.collection_elements.references.event.metadata.event_timestamp.seconds)
    $tags = array_distinct(case.tags.name)
order: $case_id desc
limit: 1000
"""
        db_queries = [
            QueryConfig(name="query_history", query_text=default_query_history, tenant_id=tenant_id),
            QueryConfig(name="query_case", query_text=default_query_case, tenant_id=tenant_id)
        ]
        db.add_all(db_queries)
        db.commit()
        return db_queries
    return queries

@api_router.put("/queries/{query_id}", response_model=QueryConfigResponse)
def update_query(query_id: int, query: QueryConfigUpdate, db: Session = Depends(get_db)):
    db_query = db.query(QueryConfig).filter(QueryConfig.id == query_id).first()
    if not db_query: raise HTTPException(status_code=404, detail="Query not found")
    db_query.query_text = query.query_text
    db.commit()
    db.refresh(db_query)
    return db_query

def perform_analysis(tenant_id: int, time_unit: str, start_time_val: int, db: Session):
    """Reusable function to perform the core analysis."""
    if not SECOPS_SDK_AVAILABLE:
        raise HTTPException(status_code=501, detail="SecOps SDK not installed.")
    
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found.")

    queries_db = db.query(QueryConfig).filter(QueryConfig.tenant_id == tenant_id).all()
    queries = {q.name: q.query_text for q in queries_db}
    if "query_history" not in queries or "query_case" not in queries:
        # Ensure default queries exist if they are missing
        get_queries(tenant_id, db)
        queries_db = db.query(QueryConfig).filter(QueryConfig.tenant_id == tenant_id).all()
        queries = {q.name: q.query_text for q in queries_db}

    interval = {
        "relativeTime": {
            "timeUnit": time_unit,
            "startTimeVal": str(start_time_val)
        }
    }
    
    try:
        client = SecOpsClient()
        chronicle = client.chronicle(customer_id=tenant.guid, project_id=tenant.gcp_project_id, region=tenant.region)
        
        results_history = chronicle.execute_dashboard_query(query=queries["query_history"], interval=interval)
        results_mttd = chronicle.execute_dashboard_query(query=queries["query_case"], interval=interval)
        
        return {
            "case_history_data": results_history,
            "case_mttd_data": results_mttd
        }
    except Exception as e:
        logging.error(f"Analysis query failed for tenant {tenant_id}: {e}", exc_info=True)
        # Re-raise as HTTPException to be handled by FastAPI
        raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")

@api_router.post("/analysis/run")
def run_analysis(request: AnalysisRequest, db: Session = Depends(get_db)):
    return perform_analysis(request.tenant_id, request.time_unit, request.start_time_val, db)


@api_router.post("/analysis/calculate", response_model=MetricsResponse)
def calculate_metrics(request: CalculationRequest, db: Session = Depends(get_db)):
    tenant = db.query(Tenant).filter(Tenant.id == request.tenant_id).first()
    if not tenant: raise HTTPException(status_code=404, detail="Tenant not found for calculation.")
    try:
        metrics = calculate_soc_metrics_structured(request.case_history_data, request.case_mttd_data, db, request.tenant_id)
        if not metrics: raise HTTPException(status_code=400, detail="Failed to calculate metrics.")
        
        full_response = metrics
        full_response['base_url'] = tenant.base_url
        return full_response
    except Exception as e:
        logging.error(f"Metric calculation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/schedules", response_model=ScheduleResponse, status_code=201)
def create_schedule(schedule: ScheduleCreate, db: Session = Depends(get_db)):
    db_schedule = Schedule(**schedule.model_dump())
    db.add(db_schedule)
    db.commit()
    db.refresh(db_schedule)
    return db_schedule

@api_router.get("/tenants/{tenant_id}/schedules", response_model=List[ScheduleResponse])
def get_schedules_for_tenant(tenant_id: int, db: Session = Depends(get_db)):
    return db.query(Schedule).filter(Schedule.tenant_id == tenant_id).all()

@api_router.put("/schedules/{schedule_id}", response_model=ScheduleResponse)
def update_schedule(schedule_id: int, schedule: ScheduleUpdate, db: Session = Depends(get_db)):
    db_schedule = db.query(Schedule).filter(Schedule.id == schedule_id).first()
    if not db_schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    for key, value in schedule.model_dump(exclude_unset=True).items():
        setattr(db_schedule, key, value)
    db.commit()
    db.refresh(db_schedule)
    return db_schedule

@api_router.delete("/schedules/{schedule_id}", status_code=204)
def delete_schedule(schedule_id: int, db: Session = Depends(get_db)):
    db_schedule = db.query(Schedule).filter(Schedule.id == schedule_id).first()
    if not db_schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    db.delete(db_schedule)
    db.commit()
    return None

@api_router.post("/schedules/{schedule_id}/run", status_code=200)
def run_schedule_now(schedule_id: int, db: Session = Depends(get_db)):
    """Endpoint to trigger an immediate run of a schedule."""
    db_schedule = db.query(Schedule).filter(Schedule.id == schedule_id).first()
    if not db_schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    
    try:
        # Running in the background to avoid long-hanging HTTP requests
        # A more robust solution might use a task queue like Celery or ARQ
        import threading
        thread = threading.Thread(target=run_scheduled_analysis, args=(db_schedule.tenant_id, db_schedule.id))
        thread.start()
        return {"status": "success", "message": f"Test run for schedule {schedule_id} initiated in the background."}
    except Exception as e:
        logging.error(f"Failed to initiate test run for schedule {schedule_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to start test run.")

@api_router.post("/destinations", response_model=ScheduleDestinationResponse, status_code=201)
def create_destination(destination: ScheduleDestinationCreate, db: Session = Depends(get_db)):
    db_destination = ScheduleDestination(**destination.model_dump())
    db.add(db_destination)
    db.commit()
    db.refresh(db_destination)
    return db_destination

@api_router.get("/schedules/{schedule_id}/destinations", response_model=List[ScheduleDestinationResponse])
def get_destinations_for_schedule(schedule_id: int, db: Session = Depends(get_db)):
    return db.query(ScheduleDestination).filter(ScheduleDestination.schedule_id == schedule_id).all()

@api_router.put("/destinations/{destination_id}", response_model=ScheduleDestinationResponse)
def update_destination(destination_id: int, destination: ScheduleDestinationUpdate, db: Session = Depends(get_db)):
    db_destination = db.query(ScheduleDestination).filter(ScheduleDestination.id == destination_id).first()
    if not db_destination:
        raise HTTPException(status_code=404, detail="Destination not found")
    for key, value in destination.model_dump(exclude_unset=True).items():
        setattr(db_destination, key, value)
    db.commit()
    db.refresh(db_destination)
    return db_destination

@api_router.delete("/destinations/{destination_id}", status_code=204)
def delete_destination(destination_id: int, db: Session = Depends(get_db)):
    db_destination = db.query(ScheduleDestination).filter(ScheduleDestination.id == destination_id).first()
    if not db_destination:
        raise HTTPException(status_code=404, detail="Destination not found")
    db.delete(db_destination)
    db.commit()
    return None


app.include_router(api_router, prefix="/api")
frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.exists(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="static")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

