"""
Galvana API with complete security fixes
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, status
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
import asyncio
import uuid
import logging

# Import local modules
from services.api.config import settings
from services.api.models import (
    RunStatus, RunType, SimulationEngine,
    CreateRunRequest, UpdateRunRequest,
    RunResponse, ScenarioCreate,
    User, UserCreate, UserUpdate, PasswordChange, Token
)
from services.api.auth_service import (
    AuthService, get_current_active_user, require_user, require_admin,
    create_access_token, create_refresh_token
)
from services.api.middleware import setup_middleware, create_rate_limit
from services.api.exceptions import (
    register_exception_handlers,
    ResourceNotFoundException,
    SimulationException,
    ValidationException
)
from services.api.logging_config import setup_logging, get_logger
from services.api.database import get_db, init_db, Run as RunModel, Scenario as ScenarioModel, User as UserModel
from services.api.metrics import setup_metrics, record_run_created, record_auth_attempt
from services.api.routers import websocket_router

# Configure logging
setup_logging()
logger = get_logger(__name__)

# Models for API responses
class RunHandle(BaseModel):
    """Simplified response for run creation"""
    run_id: str
    status: RunStatus
    queue_position: Optional[int] = None
    stream_url: Optional[str] = None

class HealthCheck(BaseModel):
    """Health check response"""
    status: str = "healthy"
    timestamp: datetime
    services: Dict[str, str]

# Lifespan management
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Galvana API...")
    # Initialize database
    init_db()
    # Initialize background tasks
    asyncio.create_task(process_run_queue())
    yield
    logger.info("Shutting down Galvana API...")

# Create FastAPI app
app = FastAPI(
    title="Galvana API",
    description="Phygital Electrochemistry Platform API",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/api/docs" if settings.environment != "production" else None,
    redoc_url="/api/redoc" if settings.environment != "production" else None,
)

# Setup all middleware (CORS, security, rate limiting, etc.)
setup_middleware(app)

# Setup Prometheus metrics (after middleware, before exception handlers)
instrumentator = setup_metrics(app)

# Expose /metrics endpoint for Prometheus scraping
@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
    from fastapi.responses import Response
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

# Register exception handlers
register_exception_handlers(app)

# Include WebSocket router
app.include_router(websocket_router)

# ============= Authentication Endpoints =============

@app.post("/api/v1/auth/register", response_model=User, status_code=status.HTTP_201_CREATED)
@create_rate_limit("3/hour")  # Strict rate limit for registration
async def register(
    user_create: UserCreate,
    db: Session = Depends(get_db)
):
    """Register new user account"""
    try:
        db_user = AuthService.create_user(db, user_create)
        return User(
            id=db_user.id,
            username=db_user.username,
            email=db_user.email,
            full_name=db_user.full_name,
            role=db_user.role,
            is_active=db_user.is_active,
            is_superuser=db_user.is_superuser
        )
    except Exception as e:
        logger.error(f"Registration failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@app.post("/api/v1/auth/token", response_model=Token)
@create_rate_limit("5/minute")  # Rate limit login attempts
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    """Authenticate and receive access token"""
    user = AuthService.authenticate_user(db, form_data.username, form_data.password)
    if not user:
        # Log failed attempt and record metric
        logger.warning(f"Failed login attempt for username: {form_data.username}")
        record_auth_attempt(success=False)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Record successful authentication
    record_auth_attempt(success=True)

    # Create tokens
    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = create_access_token(
        data={"sub": user.id},
        expires_delta=access_token_expires
    )
    refresh_token = create_refresh_token(data={"sub": user.id})

    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.access_token_expire_minutes * 60
    )

@app.get("/api/v1/auth/me", response_model=User)
async def get_current_user_info(
    current_user: User = Depends(get_current_active_user)
):
    """Get current user information"""
    return current_user

@app.put("/api/v1/auth/password")
async def change_password(
    password_change: PasswordChange,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Change user password"""
    # Verify current password
    user = AuthService.authenticate_user(db, current_user.username, password_change.current_password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect"
        )
    
    # Update password
    success = AuthService.update_password(db, current_user.id, password_change.new_password)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update password"
        )
    
    return {"message": "Password updated successfully"}

# ============= Health Check =============

@app.get("/health", response_model=HealthCheck)
async def health_check():
    """Public health check endpoint"""
    return HealthCheck(
        timestamp=datetime.utcnow(),
        services={
            "api": "healthy",
            "database": "healthy",
            "redis": "healthy",
        }
    )

# ============= Run Management (All Protected) =============

@app.post("/api/v1/runs", response_model=RunHandle, status_code=202)
@create_rate_limit("10/minute")
async def create_run(
    request: CreateRunRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Create and queue a new simulation run"""
    # Validate scenario exists if ID provided
    if request.scenario_id:
        scenario = db.query(ScenarioModel).filter(
            ScenarioModel.id == request.scenario_id
        ).first()
        if not scenario:
            raise ResourceNotFoundException("Scenario", request.scenario_id)
    
    # Create run in database
    run = RunModel(
        type=request.type.value,
        status=RunStatus.QUEUED.value,
        scenario_id=request.scenario_id,
        user_id=current_user.id,
        engine=request.engine.value,
        tags=request.tags,
        metadata=request.metadata
    )

    db.add(run)
    db.commit()
    db.refresh(run)

    # Record metrics
    record_run_created(run_type=request.type.value, engine=request.engine.value)

    # Queue for processing
    background_tasks.add_task(queue_run_for_processing, run.id)

    return RunHandle(
        run_id=run.id,
        status=RunStatus.QUEUED,
        queue_position=get_queue_position(run.id, db),
        stream_url=f"/api/v1/runs/{run.id}/stream"
    )

@app.get("/api/v1/runs", response_model=List[RunResponse])
async def list_runs(
    status: Optional[RunStatus] = None,
    limit: int = Field(20, le=100),
    offset: int = 0,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """List user's runs with optional filtering"""
    query = db.query(RunModel).filter(RunModel.user_id == current_user.id)
    
    if status:
        query = query.filter(RunModel.status == status.value)
    
    # Admin can see all runs
    if current_user.is_superuser:
        query = db.query(RunModel)
        if status:
            query = query.filter(RunModel.status == status.value)
    
    runs = query.order_by(RunModel.created_at.desc()).limit(limit).offset(offset).all()
    
    return [RunResponse(
        id=run.id,
        type=RunType(run.type),
        status=RunStatus(run.status),
        scenario_id=run.scenario_id,
        engine=run.engine,
        created_at=run.created_at,
        started_at=run.started_at,
        completed_at=run.completed_at,
        progress=run.progress,
        error=run.error,
        tags=run.tags or []
    ) for run in runs]

@app.get("/api/v1/runs/{run_id}", response_model=RunResponse)
async def get_run(
    run_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get run details"""
    run = db.query(RunModel).filter(
        RunModel.id == run_id,
        (RunModel.user_id == current_user.id) | (current_user.is_superuser == True)
    ).first()
    
    if not run:
        raise ResourceNotFoundException("Run", run_id)
    
    return RunResponse(
        id=run.id,
        type=RunType(run.type),
        status=RunStatus(run.status),
        scenario_id=run.scenario_id,
        engine=run.engine,
        created_at=run.created_at,
        started_at=run.started_at,
        completed_at=run.completed_at,
        progress=run.progress,
        error=run.error,
        tags=run.tags or []
    )

@app.patch("/api/v1/runs/{run_id}")
async def update_run(
    run_id: str,
    update: UpdateRunRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Update run status (pause/resume/abort)"""
    run = db.query(RunModel).filter(
        RunModel.id == run_id,
        (RunModel.user_id == current_user.id) | (current_user.is_superuser == True)
    ).first()
    
    if not run:
        raise ResourceNotFoundException("Run", run_id)
    
    current_status = RunStatus(run.status)
    
    if update.action == "pause" and current_status == RunStatus.RUNNING:
        run.status = RunStatus.PAUSED.value
    elif update.action == "resume" and current_status == RunStatus.PAUSED:
        run.status = RunStatus.RUNNING.value
    elif update.action == "abort":
        run.status = RunStatus.ABORTED.value
        run.completed_at = datetime.utcnow()
        if update.reason:
            run.error = {"message": update.reason}
    else:
        raise ValidationException(
            f"Invalid action {update.action} for status {current_status}",
            field="action"
        )
    
    db.commit()
    return {"message": f"Run {run_id} updated successfully"}

# ============= Scenario Management (All Protected) =============

@app.post("/api/v1/scenarios", response_model=Dict[str, str], status_code=201)
async def create_scenario(
    scenario_data: ScenarioCreate,  # Now using validated Pydantic model
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Create or update a scenario"""
    scenario = ScenarioModel(
        name=scenario_data.name,
        version=scenario_data.version,
        description=scenario_data.description,
        creator_id=current_user.id,
        physics=scenario_data.physics.dict(),
        geometry=scenario_data.geometry.dict(),
        materials=scenario_data.materials.dict(),
        boundaries=scenario_data.boundaries,
        kinetics=scenario_data.kinetics.dict() if hasattr(scenario_data, 'kinetics') else None,
        drive=scenario_data.drive.dict(),
        numerics=scenario_data.numerics.dict(),
        outputs=scenario_data.outputs.dict(),
        tags=scenario_data.tags
    )
    
    db.add(scenario)
    db.commit()
    db.refresh(scenario)
    
    return {
        "id": scenario.id,
        "message": f"Scenario '{scenario.name}' created successfully"
    }

@app.get("/api/v1/scenarios", response_model=List[Dict[str, Any]])
async def list_scenarios(
    limit: int = Field(20, le=100),
    offset: int = 0,
    public_only: bool = False,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """List scenarios"""
    query = db.query(ScenarioModel)
    
    if not current_user.is_superuser:
        if public_only:
            query = query.filter(ScenarioModel.is_public == True)
        else:
            query = query.filter(
                (ScenarioModel.creator_id == current_user.id) | 
                (ScenarioModel.is_public == True)
            )
    
    scenarios = query.order_by(ScenarioModel.created_at.desc()).limit(limit).offset(offset).all()
    
    return [{
        "id": s.id,
        "name": s.name,
        "version": s.version,
        "description": s.description,
        "is_public": s.is_public,
        "created_at": s.created_at.isoformat(),
        "tags": s.tags or []
    } for s in scenarios]

@app.get("/api/v1/scenarios/{scenario_id}")
async def get_scenario(
    scenario_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get scenario details"""
    scenario = db.query(ScenarioModel).filter(
        ScenarioModel.id == scenario_id,
        (
            (ScenarioModel.creator_id == current_user.id) | 
            (ScenarioModel.is_public == True) |
            (current_user.is_superuser == True)
        )
    ).first()
    
    if not scenario:
        raise ResourceNotFoundException("Scenario", scenario_id)
    
    return {
        "id": scenario.id,
        "name": scenario.name,
        "version": scenario.version,
        "description": scenario.description,
        "physics": scenario.physics,
        "geometry": scenario.geometry,
        "materials": scenario.materials,
        "boundaries": scenario.boundaries,
        "kinetics": scenario.kinetics,
        "drive": scenario.drive,
        "numerics": scenario.numerics,
        "outputs": scenario.outputs,
        "tags": scenario.tags,
        "created_at": scenario.created_at.isoformat()
    }

# ============= Admin Endpoints =============

@app.get("/api/v1/admin/users", response_model=List[User])
async def list_users(
    limit: int = Field(50, le=200),
    offset: int = 0,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """List all users (admin only)"""
    users = db.query(UserModel).limit(limit).offset(offset).all()
    return [User(
        id=u.id,
        username=u.username,
        email=u.email,
        full_name=u.full_name,
        role=u.role,
        is_active=u.is_active,
        is_superuser=u.is_superuser
    ) for u in users]

@app.put("/api/v1/admin/users/{user_id}")
async def update_user(
    user_id: str,
    user_update: UserUpdate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Update user details (admin only)"""
    user = db.query(UserModel).filter(UserModel.id == user_id).first()
    if not user:
        raise ResourceNotFoundException("User", user_id)
    
    # Update fields if provided
    if user_update.full_name is not None:
        user.full_name = user_update.full_name
    if user_update.email is not None:
        user.email = user_update.email
    if user_update.role is not None:
        user.role = user_update.role
    if user_update.is_active is not None:
        user.is_active = user_update.is_active
    
    user.updated_at = datetime.utcnow()
    db.commit()
    
    return {"message": f"User {user_id} updated successfully"}

# ============= Helper Functions =============

async def process_run_queue():
    """Process queued simulation runs"""
    while True:
        await asyncio.sleep(5)
        # TODO: Implement actual queue processing with Celery/Redis
        logger.debug("Processing run queue...")

async def queue_run_for_processing(run_id: str):
    """Add run to processing queue"""
    # TODO: Implement with Redis/RabbitMQ
    logger.info(f"Run {run_id} queued for processing")

def get_queue_position(run_id: str, db: Session) -> int:
    """Get position in queue"""
    # Count queued runs before this one
    position = db.query(RunModel).filter(
        RunModel.status == RunStatus.QUEUED.value,
        RunModel.created_at < db.query(RunModel.created_at).filter(
            RunModel.id == run_id
        ).scalar()
    ).count()
    return position + 1

# ============= Main Entry Point =============

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug,
        log_level=settings.log_level.lower()
    )