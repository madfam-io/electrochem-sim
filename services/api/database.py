"""
Database models and connection management
"""

from sqlalchemy import create_engine, Column, String, DateTime, Boolean, JSON, Integer, Float, ForeignKey, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from sqlalchemy.sql import func
from datetime import datetime
from typing import Optional
import uuid
from services.api.config import settings

# Create database engine
engine = create_engine(
    settings.database_url,
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
    pool_pre_ping=True,  # Verify connections before using
    echo=settings.debug,  # Log SQL in debug mode
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create base class for models
Base = declarative_base()

def get_db() -> Session:
    """Dependency to get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def generate_id(prefix: str) -> str:
    """Generate unique ID with prefix"""
    return f"{prefix}_{uuid.uuid4().hex[:12]}"

# Database Models

class User(Base):
    """User model with secure authentication"""
    __tablename__ = "users"
    
    id = Column(String, primary_key=True, default=lambda: generate_id("usr"))
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    full_name = Column(String(255))
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    is_superuser = Column(Boolean, default=False)
    role = Column(String(50), default="user")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    last_login = Column(DateTime(timezone=True))
    
    # Relationships
    runs = relationship("Run", back_populates="user", cascade="all, delete-orphan")
    scenarios = relationship("Scenario", back_populates="creator", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<User {self.username}>"

class Run(Base):
    """Simulation run model"""
    __tablename__ = "runs"
    
    id = Column(String, primary_key=True, default=lambda: generate_id("run"))
    type = Column(String(50), nullable=False)  # simulation or experiment
    status = Column(String(50), nullable=False, default="queued", index=True)
    scenario_id = Column(String, ForeignKey("scenarios.id", ondelete="SET NULL"))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    engine = Column(String(50), default="auto")
    
    # Metadata
    queue_position = Column(Integer)
    progress = Column(JSON)
    error = Column(JSON)
    tags = Column(JSON, default=list)
    metadata = Column(JSON, default=dict)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    
    # Results storage
    results_path = Column(String(500))  # S3/filesystem path
    artifacts = Column(JSON, default=list)  # List of artifact URLs
    
    # Performance metrics
    compute_time_seconds = Column(Float)
    memory_peak_mb = Column(Float)
    
    # Relationships
    user = relationship("User", back_populates="runs")
    scenario = relationship("Scenario", back_populates="runs")
    results = relationship("SimulationResult", back_populates="run", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Run {self.id} status={self.status}>"

class Scenario(Base):
    """Scenario configuration model"""
    __tablename__ = "scenarios"
    
    id = Column(String, primary_key=True, default=lambda: generate_id("scn"))
    name = Column(String(255), nullable=False)
    version = Column(String(20), default="0.1.0")
    description = Column(Text)
    creator_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    # Configuration (stored as JSON for flexibility)
    physics = Column(JSON, nullable=False)
    geometry = Column(JSON, nullable=False)
    materials = Column(JSON, nullable=False)
    boundaries = Column(JSON, nullable=False)
    kinetics = Column(JSON)
    drive = Column(JSON, nullable=False)
    numerics = Column(JSON, nullable=False)
    outputs = Column(JSON, nullable=False)
    
    # Metadata
    tags = Column(JSON, default=list)
    is_public = Column(Boolean, default=False)
    is_validated = Column(Boolean, default=False)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    creator = relationship("User", back_populates="scenarios")
    runs = relationship("Run", back_populates="scenario")
    
    def __repr__(self):
        return f"<Scenario {self.name} v{self.version}>"

class SimulationResult(Base):
    """Time-series simulation results"""
    __tablename__ = "simulation_results"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String, ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True)
    timestep = Column(Integer, nullable=False)
    time = Column(Float, nullable=False)
    
    # Key metrics
    current_density = Column(Float)
    voltage = Column(Float)
    temperature = Column(Float)
    
    # Full data stored as JSON or reference to blob storage
    data = Column(JSON)  # For small datasets
    data_url = Column(String(500))  # For large datasets in S3
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    run = relationship("Run", back_populates="results")
    
    # Create index for efficient time-series queries
    __table_args__ = (
        {"postgresql_partition_by": "RANGE (created_at)"},  # For time-series partitioning
    )
    
    def __repr__(self):
        return f"<SimulationResult run={self.run_id} t={self.time}>"

class APIKey(Base):
    """API key for programmatic access"""
    __tablename__ = "api_keys"
    
    id = Column(String, primary_key=True, default=lambda: generate_id("key"))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    key_hash = Column(String(255), nullable=False, unique=True)  # Store hashed version
    
    # Permissions
    scopes = Column(JSON, default=list)  # ["read:runs", "write:runs", etc.]
    rate_limit = Column(Integer, default=1000)  # Requests per hour
    
    # Metadata
    last_used = Column(DateTime(timezone=True))
    expires_at = Column(DateTime(timezone=True))
    is_active = Column(Boolean, default=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    def __repr__(self):
        return f"<APIKey {self.name} user={self.user_id}>"

class AuditLog(Base):
    """Audit log for security and compliance"""
    __tablename__ = "audit_logs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, index=True)
    action = Column(String(100), nullable=False, index=True)
    resource_type = Column(String(50))
    resource_id = Column(String)
    
    # Request details
    ip_address = Column(String(45))
    user_agent = Column(String(500))
    request_id = Column(String(100))
    
    # Response
    status_code = Column(Integer)
    error = Column(Text)
    
    # Timestamp
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    
    def __repr__(self):
        return f"<AuditLog {self.action} by {self.user_id}>"

# Create all tables
def init_db():
    """Initialize database tables"""
    Base.metadata.create_all(bind=engine)

def drop_db():
    """Drop all database tables (use with caution!)"""
    Base.metadata.drop_all(bind=engine)