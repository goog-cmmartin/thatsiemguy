# main.py
# Phase 2: Implementing the Rule Syncing Logic

# Import necessary libraries
import uvicorn
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Iterator, Dict, Any
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, Text, ForeignKey, or_, func, Table
from sqlalchemy.orm import sessionmaker, Session, relationship, declarative_base
import datetime
from datetime import timedelta, timezone
import os
import git
import yaml
from pathlib import Path
import logging
import json

# --- Updated imports for Correct Conversion Logic ---
# Alias the imported SigmaRule to avoid naming conflict with our SQLAlchemy model
from sigma.rule import SigmaRule as SigmaRuleParser
from sigma.backends.secops import SecOpsBackend
from sigma.pipelines.secops import secops_udm_pipeline
from secops import SecOpsClient
from fastapi.responses import FileResponse, StreamingResponse

# --- Configure logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- 1. Database Configuration ---
DATABASE_URL = "sqlite:///./sigma_manager.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- 2. Database Models (Unchanged) ---

class Tenant(Base):
    __tablename__ = "tenants"
    tenant_id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    guid = Column(String, unique=True, index=True)
    region = Column(String)
    gcp_project_id = Column(String)
    is_default = Column(Boolean, default=False)
    deployments = relationship("Deployment", back_populates="tenant")

class SigmaLibrary(Base):
    __tablename__ = "sigma_libraries"
    library_id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    source_path = Column(String)
    last_synced_at = Column(DateTime, nullable=True)
    rules = relationship("SigmaRule", back_populates="library")

# Association table for the many-to-many relationship between rules and tags
rule_tag_association = Table('rule_tag_association', Base.metadata,
    Column('rule_id', Integer, ForeignKey('sigma_rules.rule_id'), primary_key=True),
    Column('tag_id', Integer, ForeignKey('tags.tag_id'), primary_key=True)
)

class Tag(Base):
    __tablename__ = 'tags'
    tag_id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, index=True)

class SigmaRule(Base):
    __tablename__ = "sigma_rules"

    # --- Core Columns ---
    rule_id = Column(Integer, primary_key=True, index=True)
    file_path = Column(String, unique=True)
    raw_content = Column(Text) # Keep for original source

    # --- Extracted Columns for Filtering ---
    title = Column(String, index=True)
    sigma_id = Column(String, index=True, nullable=True) # The 'id' from the YAML
    status = Column(String, index=True, nullable=True)
    description = Column(Text, nullable=True)
    author = Column(String, index=True, nullable=True)
    # Storing dates as strings for simplicity, as some dates in sigma are just YYYY/MM/DD and others are more complex
    date = Column(String, nullable=True)
    modified = Column(String, nullable=True)
    level = Column(String, index=True, nullable=True)

    # --- Flattened Logsource Fields ---
    logsource_product = Column(String, index=True, nullable=True)
    logsource_category = Column(String, index=True, nullable=True)
    logsource_service = Column(String, index=True, nullable=True)

    # --- Conversion-related Columns ---
    conversion_status = Column(String, default="pending")
    conversion_error = Column(Text, nullable=True)

    # --- Relationships ---
    library_id = Column(Integer, ForeignKey("sigma_libraries.library_id"))
    library = relationship("SigmaLibrary", back_populates="rules")
    yaral_rule = relationship("YaraLRule", back_populates="sigma_rule", uselist=False)
    tags = relationship("Tag", secondary=rule_tag_association, backref="rules")

class YaraLRule(Base):
    __tablename__ = "yaral_rules"
    yaral_rule_id = Column(Integer, primary_key=True, index=True)
    converted_content = Column(Text)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    source = Column(String, default="pySigma") # Add source column
    sigma_rule_id = Column(Integer, ForeignKey("sigma_rules.rule_id"))
    sigma_rule = relationship("SigmaRule", back_populates="yaral_rule")
    deployments = relationship("Deployment", back_populates="yaral_rule")

class Deployment(Base):
    __tablename__ = "deployments"
    deployment_id = Column(Integer, primary_key=True, index=True)
    deployed_at = Column(DateTime, default=datetime.datetime.utcnow)
    status = Column(String, default="live") # live, disabled, error
    detection_count = Column(Integer, default=0)
    last_perf_check = Column(DateTime, nullable=True)
    yaral_rule_id = Column(Integer, ForeignKey("yaral_rules.yaral_rule_id"))
    tenant_id = Column(Integer, ForeignKey("tenants.tenant_id"))
    yaral_rule = relationship("YaraLRule", back_populates="deployments")
    tenant = relationship("Tenant", back_populates="deployments")


# --- Create the database tables ---
Base.metadata.create_all(bind=engine)

# --- 3. Pydantic Schemas (Unchanged) ---

class TenantCreate(BaseModel):
    name: str
    guid: str
    region: str
    gcp_project_id: str
    is_default: Optional[bool] = False
class TenantResponse(TenantCreate):
    tenant_id: int
    class Config:
        from_attributes = True

class SigmaLibraryCreate(BaseModel):
    name: str
    source_path: str
class SigmaLibraryResponse(SigmaLibraryCreate):
    library_id: int
    last_synced_at: Optional[datetime.datetime] = None
    class Config:
        from_attributes = True

class TagResponse(BaseModel):
    tag_id: int
    name: str
    class Config:
        from_attributes = True

class SigmaRuleResponse(BaseModel):
    rule_id: int
    library_id: int
    title: str
    file_path: str
    status: Optional[str] = None
    level: Optional[str] = None
    conversion_status: str
    author: Optional[str] = None
    date: Optional[str] = None
    modified: Optional[str] = None
    logsource_product: Optional[str] = None
    logsource_category: Optional[str] = None
    class Config:
        from_attributes = True

class SigmaRuleDetailResponse(SigmaRuleResponse):
    sigma_id: Optional[str] = None
    description: Optional[str] = None
    author: Optional[str] = None
    date: Optional[str] = None
    modified: Optional[str] = None
    logsource_product: Optional[str] = None
    logsource_category: Optional[str] = None
    logsource_service: Optional[str] = None
    raw_content: str
    conversion_error: Optional[str] = None
    tags: List[TagResponse] = []
    class Config:
        from_attributes = True

class YaraLRuleResponse(BaseModel):
    yaral_rule_id: int
    converted_content: str
    created_at: datetime.datetime
    source: str
    sigma_rule_id: int
    class Config:
        from_attributes = True

class DeploymentResponse(BaseModel):
    deployment_id: int
    status: str
    detection_count: int
    deployed_at: datetime.datetime
    yaral_rule_id: int
    tenant_id: int
    class Config:
        from_attributes = True

class ConvertRequest(BaseModel):
    sigma_rule_ids: List[int]

class DeployRequest(BaseModel):
    yaral_rule_id: int
    tenant_id: int

class ValidationResponse(BaseModel):
    success: bool
    message: Optional[str] = None
    position: Optional[Dict[str, int]] = None

class YaraLRuleUpdate(BaseModel):
    converted_content: str


# --- 4. FastAPI Application Setup (Unchanged) ---
app = FastAPI(
    title="SIGMA Rule Management API",
    description="Backend API for managing the lifecycle of SIGMA rules in Google SecOps.",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# --- 5. Dependency Injection for Database Session (Unchanged) ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- 6. Background Tasks ---
def sync_sigma_rules(library_id: int):
    """
    Clones or pulls a git repo and upserts Sigma rules into the database.
    """
    db = SessionLocal()
    processed_tags = {}  # Local cache for tags within this transaction
    try:
        db_library = db.query(SigmaLibrary).filter(SigmaLibrary.library_id == library_id).first()
        if not db_library:
            logging.error(f"Error: Library {library_id} not found in background task.")
            return

        repo_path_str = f"./sigma_repos/{db_library.name.replace(' ', '_')}"
        repo_path = Path(repo_path_str)

        if repo_path.exists() and repo_path.is_dir():
            logging.info(f"Pulling latest changes for {db_library.name}...")
            repo = git.Repo(repo_path)
            repo.remotes.origin.pull()
        else:
            logging.info(f"Cloning {db_library.name} from {db_library.source_path}...")
            repo_path.mkdir(parents=True, exist_ok=True)
            git.Repo.clone_from(db_library.source_path, repo_path)

        rule_count = 0
        for yaml_file in repo_path.rglob("*.yml"):
            relative_path = str(yaml_file.relative_to(repo_path))
            
            try:
                with open(yaml_file, 'r', encoding='utf-8') as f:
                    raw_content = f.read()
                    documents = list(yaml.safe_load_all(raw_content))
                    if not documents:
                        continue
                    rule_yaml = documents[0]

                if 'title' in rule_yaml and 'id' in rule_yaml and isinstance(rule_yaml, dict):
                    existing_rule = db.query(SigmaRule).filter(
                        SigmaRule.library_id == library_id,
                        SigmaRule.file_path == relative_path
                    ).first()

                    logsource = rule_yaml.get('logsource', {}) or {}
                    
                    rule_data = {
                        'raw_content': raw_content,
                        'title': rule_yaml.get('title'),
                        'sigma_id': rule_yaml.get('id'),
                        'status': rule_yaml.get('status'),
                        'description': rule_yaml.get('description'),
                        'author': rule_yaml.get('author'),
                        'date': str(rule_yaml.get('date')),
                        'modified': str(rule_yaml.get('modified')),
                        'level': rule_yaml.get('level'),
                        'logsource_product': logsource.get('product'),
                        'logsource_category': logsource.get('category'),
                        'logsource_service': logsource.get('service'),
                        'conversion_status': "pending"
                    }

                    tag_objects = []
                    tag_list = rule_yaml.get('tags', [])
                    if tag_list:
                        for tag_name in tag_list:
                            tag_name = tag_name.strip()
                            if tag_name in processed_tags:
                                db_tag = processed_tags[tag_name]
                            else:
                                db_tag = db.query(Tag).filter(Tag.name == tag_name).first()
                                if not db_tag:
                                    db_tag = Tag(name=tag_name)
                                    db.add(db_tag)
                                processed_tags[tag_name] = db_tag
                            tag_objects.append(db_tag)

                    if existing_rule:
                        for key, value in rule_data.items():
                            setattr(existing_rule, key, value)
                        existing_rule.tags = tag_objects
                    else:
                        new_rule = SigmaRule(
                            **rule_data,
                            file_path=relative_path,
                            library_id=library_id
                        )
                        new_rule.tags = tag_objects
                        db.add(new_rule)
                    
                    rule_count += 1
            except Exception as e:
                logging.error(f"Error processing file {relative_path}: {e}")
        
        db_library.last_synced_at = datetime.datetime.utcnow()
        db.commit()
        logging.info(f"Sync complete for library '{db_library.name}'. Processed {rule_count} rules.")

    finally:
        db.close()

# --- REVISED: Background Task for Rule Conversion (with fix) ---
def convert_rules_task(sigma_rule_ids: List[int]):
    """
    Takes a list of SigmaRule IDs and attempts to convert them to YARA-L.
    Updates the database with the result.
    """
    db = SessionLocal()
    # Initialize the backend WITH the UDM pipeline
    udm_pipeline = secops_udm_pipeline()
    backend = SecOpsBackend(processing_pipeline=udm_pipeline)

    try:
        for rule_id in sigma_rule_ids:
            db_rule = db.query(SigmaRule).filter(SigmaRule.rule_id == rule_id).first()
            if not db_rule:
                continue

            try:
                # Load the individual rule from its raw YAML content using the aliased parser
                rule = SigmaRuleParser.from_yaml(db_rule.raw_content)
                
                # Convert the single rule
                converted_rules = backend.convert_rule(rule, "yara_l")
                
                if not converted_rules:
                    raise ValueError("Conversion resulted in no output. The rule might be unsupported.")

                yaral_content = converted_rules[0]
                # FIX: Replace 'conditions:' with 'condition:' to address 3rd party library bug
                yaral_content = yaral_content.replace("conditions:", "condition:")

                existing_yaral = db.query(YaraLRule).filter(YaraLRule.sigma_rule_id == rule_id).first()
                if existing_yaral:
                    existing_yaral.converted_content = yaral_content
                    existing_yaral.source = 'pySigma'
                else:
                    new_yaral_rule = YaraLRule(
                        sigma_rule_id=rule_id,
                        converted_content=yaral_content,
                        source='pySigma'
                    )
                    db.add(new_yaral_rule)
                
                db_rule.conversion_status = "success"
                db_rule.conversion_error = None

            except Exception as e:
                db_rule.conversion_status = "failed"
                db_rule.conversion_error = str(e)
                # Add logging for the conversion error
                logging.error(f"Failed to convert rule ID {rule_id} ({db_rule.title}): {e}")
            
            db.commit()
        logging.info(f"Conversion task finished. Processed {len(sigma_rule_ids)} rules.")
    finally:
        db.close()

def convert_rules_with_ai_task(sigma_rule_ids: List[int]):
    """
    Takes a list of SigmaRule IDs and attempts to convert them to YARA-L using AI.
    Updates the database with the result.
    """
    db = SessionLocal()
    try:
        # For now, let's assume a default tenant for the Gemini client.
        # A better approach would be to let the user select a tenant.
        tenant = db.query(Tenant).filter(Tenant.is_default == True).first()
        if not tenant:
            # If no default tenant, pick the first one
            tenant = db.query(Tenant).first()
        if not tenant:
            logging.error("No tenants configured for AI conversion.")
            # Mark all rules as failed
            for rule_id in sigma_rule_ids:
                db_rule = db.query(SigmaRule).filter(SigmaRule.rule_id == rule_id).first()
                if db_rule:
                    db_rule.conversion_status = "failed"
                    db_rule.conversion_error = "No tenants configured for AI conversion."
            db.commit()
            return

        client = SecOpsClient()
        chronicle = client.chronicle(
            customer_id=tenant.guid,
            project_id=tenant.gcp_project_id,
            region=tenant.region
        )

        for rule_id in sigma_rule_ids:
            db_rule = db.query(SigmaRule).filter(SigmaRule.rule_id == rule_id).first()
            if not db_rule:
                continue

            try:
                prompt = f"Convert this Sigma rule into YARA-L: {db_rule.raw_content}"
                response = chronicle.gemini(prompt)
                
                logging.info(f"Gemini response for rule ID {rule_id}: {response}")

                # I'll assume the YARA-L rule is in the first code block
                code_blocks = response.get_code_blocks()
                if not code_blocks:
                    logging.error(f"AI conversion for rule ID {rule_id} resulted in no code block. Full response: {response}")
                    raise ValueError("AI conversion resulted in no code block.")

                yaral_content = code_blocks[0].content
                
                # FIX: Replace 'conditions:' with 'condition:' to address 3rd party library bug
                yaral_content = yaral_content.replace("conditions:", "condition:")

                existing_yaral = db.query(YaraLRule).filter(YaraLRule.sigma_rule_id == rule_id).first()
                if existing_yaral:
                    existing_yaral.converted_content = yaral_content
                    existing_yaral.source = 'SecOps Gemini'
                else:
                    new_yaral_rule = YaraLRule(
                        sigma_rule_id=rule_id,
                        converted_content=yaral_content,
                        source='SecOps Gemini'
                    )
                    db.add(new_yaral_rule)
                
                db_rule.conversion_status = "success"
                db_rule.conversion_error = None

            except Exception as e:
                db_rule.conversion_status = "failed"
                db_rule.conversion_error = str(e)
                logging.error(f"Failed to convert rule ID {rule_id} with AI: {e}", exc_info=True)
            
            db.commit()
        logging.info(f"AI conversion task finished. Processed {len(sigma_rule_ids)} rules.")
    finally:
        db.close()

# --- NEW: Background Task for Rule Deployment ---
def deploy_rule_task(deployment_id: int):
    """
    Handles the actual deployment of a YARA-L rule to a SecOps tenant.
    """
    db = SessionLocal()
    try:
        deployment = db.query(Deployment).filter(Deployment.deployment_id == deployment_id).first()
        if not deployment:
            logging.error(f"Deployment ID {deployment_id} not found for deployment task.")
            return

        tenant = deployment.tenant
        yaral_rule = deployment.yaral_rule
        
        logging.info(f"Starting deployment of '{yaral_rule.sigma_rule.title}' to tenant '{tenant.name}'.")

        try:
            # IMPORTANT: secops-wrapper authenticates using Application Default Credentials (ADC).
            # Ensure your environment is authenticated (e.g., by running `gcloud auth application-default login`)
            # before running the API server.
            client = SecOpsClient()

            chronicle = client.chronicle(
                customer_id=tenant.guid,
                project_id=tenant.gcp_project_id,
                region=tenant.region
            )

            # The create_rule method takes the rule content as a string.
            response = chronicle.create_rule(yaral_rule.converted_content)
            rule_id = response.get("name", "").split("/")[-1]
            print(f"Rule ID: {rule_id}")

            # Assuming a successful API call means the rule is live.
            # You might want to parse the 'response' for more details in a real application.
            deployment.status = "live"
            deployment.deployed_at = datetime.datetime.utcnow()
            logging.info(f"Successfully deployed rule. Response: {response}")

        except Exception as e:
            deployment.status = "error"
            logging.error(f"Failed to deploy rule ID {yaral_rule.yaral_rule_id} to tenant {tenant.tenant_id}: {e}")
        
        db.commit()

    finally:
        db.close()


class APIError(Exception):
    pass

class SecOpsError(Exception):
    pass

def run_rule_test(
    client,
    rule_text: str,
    start_time: datetime,
    end_time: datetime,
    max_results: int = 100,
    timeout: int = 300,
) -> Iterator[Dict[str, Any]]:
    """Tests a rule against historical data and returns matches.

    This function connects to the legacy:legacyRunTestRule streaming
    API endpoint and processes the response which contains progress updates
    and detection results.

    Args:
        client: ChronicleClient instance
        rule_text: Content of the detection rule to test
        start_time: Start time for the test range
        end_time: End time for the test range
        max_results: Maximum number of results to return
            (default 100, max 10000)
        timeout: Request timeout in seconds (default 300)

    Yields:
        Dictionaries containing detection results, progress updates
        or error information, depending on the response type.

    Raises:
        APIError: If the API request fails
        SecOpsError: If the input parameters are invalid
        ValueError: If max_results is outside valid range
    """
    # Validate input parameters
    if max_results < 1 or max_results > 10000:
        raise ValueError("max_results must be between 1 and 10000")

    # Convert datetime objects to ISO format strings required by the API
    # API expects timestamps in RFC3339 format with UTC timezone
    if not start_time.tzinfo:
        start_time = start_time.replace(tzinfo=timezone.utc)
    if not end_time.tzinfo:
        end_time = end_time.replace(tzinfo=timezone.utc)

    # Format as RFC3339 with Z suffix
    start_time_str = start_time.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_time_str = end_time.strftime("%Y-%m-%dT%H:%M:%SZ")

    # Fix: Use the full path for the legacy API endpoint
    url = (
        f"{client.base_url}/projects/{client.project_id}/locations"
        f"/{client.region}/instances/{client.customer_id}"
        "/legacy:legacyRunTestRule"
    )

    body = {
        "ruleText": rule_text,
        "timeRange": {
            "startTime": start_time_str,
            "endTime": end_time_str,
        },
        "maxResults": max_results,
        "scope": "",  # Empty scope parameter
    }
    
    # Make the request and get the complete response
    try:
        response = client.session.post(url, json=body, timeout=timeout)

        if response.status_code != 200:
            raise APIError(f"Failed to test rule: {response.text}")

        # Parse the response as a JSON array
        try:
            json_array = json.loads(response.text)

            # Yield each item in the array
            for item in json_array:
                # Transform the response items to match the expected format
                if "detection" in item:
                    # Return the detection with proper type
                    yield {"type": "detection", "detection": item["detection"]}
                elif "progressPercent" in item:
                    yield {
                        "type": "progress",
                        "percentDone": item["progressPercent"],
                    }
                elif "ruleCompilationError" in item:
                    yield {
                        "type": "error",
                        "message": item["ruleCompilationError"],
                        "isCompilationError": True,
                    }
                elif "ruleError" in item:
                    yield {"type": "error", "message": item["ruleError"]}
                elif "tooManyDetections" in item and item["tooManyDetections"]:
                    yield {
                        "type": "info",
                        "message": (
                            "Too many detections found, "
                            "results may be incomplete"
                        ),
                    }
                else:
                    # Unknown item type, yield as-is
                    yield item

        except json.JSONDecodeError as e:
            raise APIError(
                f"Failed to parse rule test response: {str(e)}"
            ) from e

    except Exception as e:
        raise APIError(f"Error testing rule: {str(e)}") from e


# --- 7. API Endpoints ---

@app.get("/", response_class=FileResponse, tags=["Root"])
async def read_root():
    """Serves the main index.html file."""
    return "index.html"

# --- Tenant Management Endpoints (Unchanged) ---
@app.post("/api/tenants", response_model=TenantResponse, tags=["Tenant Management"])
def create_tenant(tenant: TenantCreate, db: Session = Depends(get_db)):
    db_tenant = Tenant(**tenant.dict())
    db.add(db_tenant)
    db.commit()
    db.refresh(db_tenant)
    return db_tenant

@app.get("/api/tenants", response_model=List[TenantResponse], tags=["Tenant Management"])
def get_tenants(db: Session = Depends(get_db)):
    return db.query(Tenant).all()

# --- Sigma Library Management Endpoints (Sync endpoint is now active) ---
@app.post("/api/libraries", response_model=SigmaLibraryResponse, tags=["Sigma Library Management"])
def create_library(library: SigmaLibraryCreate, db: Session = Depends(get_db)):
    db_library = SigmaLibrary(**library.dict())
    db.add(db_library)
    db.commit()
    db.refresh(db_library)
    return db_library

@app.get("/api/libraries", response_model=List[SigmaLibraryResponse], tags=["Sigma Library Management"])
def get_libraries(db: Session = Depends(get_db)):
    return db.query(SigmaLibrary).all()

@app.post("/api/libraries/{library_id}/sync", response_model=dict, tags=["Sigma Library Management"])
def sync_library_endpoint(library_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Trigger a background job to sync rules from the library's source."""
    db_library = db.query(SigmaLibrary).filter(SigmaLibrary.library_id == library_id).first()
    if not db_library:
        raise HTTPException(status_code=404, detail="Library not found")
    
    # Add the sync function to run in the background
    background_tasks.add_task(sync_sigma_rules, library_id)
    
    return {"status": "sync_started", "message": f"Sync job initiated for library {db_library.name}."}

# --- Rule Management & Conversion ---
@app.get("/api/sigma-rules", response_model=List[SigmaRuleResponse], tags=["Rule Management & Conversion"])
def get_sigma_rules(
    library_id: Optional[int] = None, 
    status: Optional[str] = None, 
    level: Optional[str] = None,
    search: Optional[str] = None, 
    tag: Optional[str] = None,
    rule_ids: Optional[List[int]] = Query(None), 
    db: Session = Depends(get_db)
):
    query = db.query(SigmaRule)
    if library_id: query = query.filter(SigmaRule.library_id == library_id)
    if status: query = query.filter(SigmaRule.conversion_status == status)
    if level: query = query.filter(func.lower(SigmaRule.level) == level.lower())
    if tag:
        query = query.join(SigmaRule.tags).filter(func.lower(Tag.name) == tag.lower())
    if search:
        search_term = f"%{search.lower()}%"
        query = query.filter(or_(
            func.lower(SigmaRule.title).like(search_term),
            func.lower(SigmaRule.description).like(search_term),
            func.lower(SigmaRule.author).like(search_term),
            func.lower(SigmaRule.file_path).like(search_term)
        ))
    if rule_ids:
        query = query.filter(SigmaRule.rule_id.in_(rule_ids))
    return query.all()

@app.get("/api/sigma-rules/{rule_id}", response_model=SigmaRuleDetailResponse, tags=["Rule Management & Conversion"])
def get_sigma_rule_details(rule_id: int, db: Session = Depends(get_db)):
    db_rule = db.query(SigmaRule).filter(SigmaRule.rule_id == rule_id).first()
    if db_rule is None:
        raise HTTPException(status_code=404, detail="Sigma rule not found")
    return db_rule

@app.post("/api/sigma-rules/convert", response_model=dict, tags=["Rule Management & Conversion"])
def convert_sigma_rules(request: ConvertRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """
    Takes a list of sigma_rule_ids and triggers a background job to convert them.
    """
    logging.info(f"Received conversion request: {request.dict()}")
    # Quick check to see if rules exist
    rules_to_convert = db.query(SigmaRule).filter(SigmaRule.rule_id.in_(request.sigma_rule_ids)).all()
    if len(rules_to_convert) != len(request.sigma_rule_ids):
        raise HTTPException(status_code=404, detail="One or more rule IDs not found.")

    background_tasks.add_task(convert_rules_task, request.sigma_rule_ids)

    return {"status": "conversion_started", "message": f"Conversion job initiated for {len(request.sigma_rule_ids)} rules."}

@app.post("/api/sigma-rules/convert-with-ai", response_model=dict, tags=["Rule Management & Conversion"])
def convert_sigma_rules_with_ai(request: ConvertRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """
    Takes a list of sigma_rule_ids and triggers a background job to convert them using AI.
    """
    # Quick check to see if rules exist
    rules_to_convert = db.query(SigmaRule).filter(SigmaRule.rule_id.in_(request.sigma_rule_ids)).all()
    if len(rules_to_convert) != len(request.sigma_rule_ids):
        raise HTTPException(status_code=404, detail="One or more rule IDs not found.")

    background_tasks.add_task(convert_rules_with_ai_task, request.sigma_rule_ids)

    return {"status": "ai_conversion_started", "message": f"AI conversion job initiated for {len(request.sigma_rule_ids)} rules."}


@app.get("/api/yaral-rules", response_model=List[YaraLRuleResponse], tags=["Rule Management & Conversion"])
def get_yaral_rules(search: Optional[str] = None, db: Session = Depends(get_db)):
    """
    Get a list of all successfully converted YARA-L rules.
    Can be filtered by a search term on the original Sigma rule title.
    """
    query = db.query(YaraLRule)

    # NEW: Add search logic
    if search:
        search_term = f"%{search.lower()}%"
        # Join with the related SigmaRule and filter on the title
        query = query.join(YaraLRule.sigma_rule).filter(
            func.lower(SigmaRule.title).like(search_term)
        )
        
    return query.all()

@app.get("/api/yaral-rules/{yaral_rule_id}/test", tags=["Rule Management & Conversion"])
async def test_yaral_rule(yaral_rule_id: int, db: Session = Depends(get_db)):
    """
    Tests a YARA-L rule against historical data and streams the results.
    """
    logging.info(f"Starting test for YARA-L rule ID: {yaral_rule_id}")
    db_rule = db.query(YaraLRule).filter(YaraLRule.yaral_rule_id == yaral_rule_id).first()
    if not db_rule:
        logging.error(f"YARA-L rule with ID {yaral_rule_id} not found.")
        raise HTTPException(status_code=404, detail="YARA-L rule not found")

    # For now, let's assume a default tenant. 
    # A better approach would be to let the user select a tenant.
    tenant = db.query(Tenant).filter(Tenant.is_default == True).first()
    if not tenant:
        # If no default tenant, pick the first one
        tenant = db.query(Tenant).first()
    if not tenant:
        logging.error("No tenants configured.")
        raise HTTPException(status_code=404, detail="No tenants configured")
    
    logging.info(f"Using tenant: {tenant.name} ({tenant.guid})")

    client = SecOpsClient()
    chronicle_client = client.chronicle(
        customer_id=tenant.guid,
        project_id=tenant.gcp_project_id,
        region=tenant.region
    )

    now = datetime.datetime.now(timezone.utc)
    start_time = now - timedelta(hours=192)
    end_time = now - timedelta(hours=24)

    async def event_stream():
        logging.info("Event stream started.")
        try:
            for result in run_rule_test(
                client=chronicle_client,
                rule_text=db_rule.converted_content,
                start_time=start_time,
                end_time=end_time,
            ):
                logging.info(f"Yielding result: {result}")
                yield f"data: {json.dumps(result)}\n\n"
        except Exception as e:
            logging.error(f"An error occurred during the event stream: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        finally:
            logging.info("Event stream finished.")

    response = StreamingResponse(event_stream(), media_type="text/event-stream")
    return response


@app.get("/api/yaral-rules/{yaral_rule_id}", response_model=YaraLRuleResponse, tags=["Rule Management & Conversion"])

def get_yaral_rule(yaral_rule_id: int, db: Session = Depends(get_db)):
    """
    Get the details of a single converted YARA-L rule by its ID.
    """
    db_rule = db.query(YaraLRule).filter(YaraLRule.yaral_rule_id == yaral_rule_id).first()
    if db_rule is None:
        raise HTTPException(status_code=404, detail="YARA-L rule not found")
    return db_rule

@app.post("/api/yaral-rules/{yaral_rule_id}/verify", response_model=ValidationResponse, tags=["Rule Management & Conversion"])
def verify_yaral_rule(yaral_rule_id: int, db: Session = Depends(get_db)):
    """
    Validates the syntax of a YARA-L rule without running it against data.
    """
    db_rule = db.query(YaraLRule).filter(YaraLRule.yaral_rule_id == yaral_rule_id).first()
    if not db_rule:
        raise HTTPException(status_code=404, detail="YARA-L rule not found")

    # Use the default or first tenant to get Chronicle credentials
    tenant = db.query(Tenant).filter(Tenant.is_default == True).first() or db.query(Tenant).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="No tenants configured for validation")

    try:
        client = SecOpsClient()
        chronicle_client = client.chronicle(
            customer_id=tenant.guid,
            project_id=tenant.gcp_project_id,
            region=tenant.region
        )

        # Perform the validation
        result = chronicle_client.validate_rule(db_rule.converted_content)

        return ValidationResponse(
            success=result.success,
            message=result.message,
            position=result.position
        )
    except Exception as e:
        logging.error(f"An error occurred during rule validation: {e}", exc_info=True)
        return ValidationResponse(success=False, message=str(e))

@app.put("/api/yaral-rules/{yaral_rule_id}", response_model=YaraLRuleResponse, tags=["Rule Management & Conversion"])
def update_yaral_rule(yaral_rule_id: int, rule_update: YaraLRuleUpdate, db: Session = Depends(get_db)):
    """
    Updates the content of a converted YARA-L rule.
    """
    db_rule = db.query(YaraLRule).filter(YaraLRule.yaral_rule_id == yaral_rule_id).first()
    if db_rule is None:
        raise HTTPException(status_code=404, detail="YARA-L rule not found")

    # Update the content and mark the source as manually edited
    db_rule.converted_content = rule_update.converted_content
    db_rule.source = "Manual Edit"
    
    db.commit()
    db.refresh(db_rule)
    
    return db_rule

# --- Deployment & Performance (Unchanged for now) ---
@app.get("/api/deployments", response_model=List[DeploymentResponse], tags=["Deployment & Performance"])
def get_deployments(tenant_id: Optional[int] = None, db: Session = Depends(get_db)):
    query = db.query(Deployment)
    if tenant_id:
        query = query.filter(Deployment.tenant_id == tenant_id)
    return query.all()

# --- Deployment Endpoint ---
@app.post("/api/deployments", response_model=dict, tags=["Deployment & Performance"])
def deploy_rule(request: DeployRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    # Check if the rule and tenant exist before starting the task
    yaral_rule = db.query(YaraLRule).filter(YaraLRule.yaral_rule_id == request.yaral_rule_id).first()
    tenant = db.query(Tenant).filter(Tenant.tenant_id == request.tenant_id).first()
    if not yaral_rule or not tenant:
        raise HTTPException(status_code=404, detail="YARA-L rule or tenant not found")

    # Create the deployment record with a "pending" status
    new_deployment = Deployment(
        yaral_rule_id=request.yaral_rule_id, 
        tenant_id=request.tenant_id,
        status="pending"
    )
    db.add(new_deployment)
    db.commit()
    db.refresh(new_deployment)
    
    # Start the background task to perform the actual deployment
    background_tasks.add_task(deploy_rule_task, new_deployment.deployment_id)
    
    return {"status": "deployment_started", "deployment_id": new_deployment.deployment_id}

# --- Uvicorn Runner ---
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)

