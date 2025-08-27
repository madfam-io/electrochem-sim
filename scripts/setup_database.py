#!/usr/bin/env python3
"""
Database setup and initialization script
"""

import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from services.api.database import engine, init_db, Base
from services.api.auth_service import get_password_hash, AuthService
from services.api.models import UserCreate
from services.api.database import get_db, User as UserModel
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_database():
    """Create database if it doesn't exist"""
    try:
        # Try to connect to the database
        with engine.connect() as conn:
            logger.info("Database connection successful")
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        logger.info("Please ensure PostgreSQL is running and the database exists")
        logger.info("You may need to create the database manually:")
        logger.info("  psql -U postgres -c 'CREATE DATABASE galvana_dev;'")
        return False
    return True

def create_tables():
    """Create all database tables"""
    try:
        logger.info("Creating database tables...")
        init_db()
        logger.info("✅ Database tables created successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to create tables: {e}")
        return False

def create_admin_user():
    """Create initial admin user"""
    from sqlalchemy.orm import Session
    
    logger.info("Creating admin user...")
    
    # Get database session
    db = Session(bind=engine)
    
    try:
        # Check if admin already exists
        existing = db.query(UserModel).filter(
            UserModel.username == "admin"
        ).first()
        
        if existing:
            logger.info("Admin user already exists")
            return True
        
        # Create admin user
        admin = UserModel(
            username="admin",
            email="admin@galvana.local",
            full_name="System Administrator",
            hashed_password=get_password_hash("ChangeMe123!"),  # Default password
            role="superuser",
            is_active=True,
            is_superuser=True
        )
        
        db.add(admin)
        db.commit()
        
        logger.info("✅ Admin user created successfully")
        logger.info("  Username: admin")
        logger.info("  Password: ChangeMe123!")
        logger.info("  ⚠️  CHANGE THIS PASSWORD IMMEDIATELY!")
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to create admin user: {e}")
        db.rollback()
        return False
    finally:
        db.close()

def create_demo_user():
    """Create demo user for testing"""
    from sqlalchemy.orm import Session
    
    logger.info("Creating demo user...")
    
    db = Session(bind=engine)
    
    try:
        # Check if demo user exists
        existing = db.query(UserModel).filter(
            UserModel.username == "demo"
        ).first()
        
        if existing:
            logger.info("Demo user already exists")
            return True
        
        # Create demo user
        demo = UserModel(
            username="demo",
            email="demo@galvana.local",
            full_name="Demo User",
            hashed_password=get_password_hash("Demo123!"),
            role="user",
            is_active=True,
            is_superuser=False
        )
        
        db.add(demo)
        db.commit()
        
        logger.info("✅ Demo user created successfully")
        logger.info("  Username: demo")
        logger.info("  Password: Demo123!")
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to create demo user: {e}")
        db.rollback()
        return False
    finally:
        db.close()

def setup_alembic():
    """Initialize Alembic for migrations"""
    import subprocess
    
    try:
        logger.info("Initializing Alembic migrations...")
        
        # Check if migrations directory exists
        migrations_dir = Path(__file__).parent.parent / "migrations"
        if not migrations_dir.exists():
            # Initialize alembic
            result = subprocess.run(
                ["alembic", "init", "migrations"],
                cwd=Path(__file__).parent.parent,
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                logger.error(f"Failed to initialize Alembic: {result.stderr}")
                return False
        
        # Generate initial migration
        result = subprocess.run(
            ["alembic", "revision", "--autogenerate", "-m", "Initial migration"],
            cwd=Path(__file__).parent.parent,
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0 and "No changes" not in result.stdout:
            logger.error(f"Failed to generate migration: {result.stderr}")
            return False
        
        # Apply migrations
        result = subprocess.run(
            ["alembic", "upgrade", "head"],
            cwd=Path(__file__).parent.parent,
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            logger.error(f"Failed to apply migrations: {result.stderr}")
            return False
        
        logger.info("✅ Alembic migrations initialized")
        return True
        
    except Exception as e:
        logger.error(f"Failed to setup Alembic: {e}")
        return False

def main():
    """Main setup function"""
    logger.info("🚀 Setting up Galvana database...")
    
    # Check environment
    env_path = Path(__file__).parent.parent / ".env"
    if not env_path.exists():
        logger.error("❌ .env file not found!")
        logger.info("Please run: python scripts/generate_secrets.py")
        return 1
    
    # Load environment variables
    from dotenv import load_dotenv
    load_dotenv()
    
    # Setup steps
    steps = [
        ("Checking database connection", create_database),
        ("Creating database tables", create_tables),
        ("Creating admin user", create_admin_user),
        ("Creating demo user", create_demo_user),
        # ("Setting up Alembic migrations", setup_alembic),  # Optional
    ]
    
    for step_name, step_func in steps:
        logger.info(f"\n{step_name}...")
        if not step_func():
            logger.error(f"❌ Failed at: {step_name}")
            return 1
    
    logger.info("\n" + "="*50)
    logger.info("✅ Database setup complete!")
    logger.info("="*50)
    logger.info("\nNext steps:")
    logger.info("1. Start the API server: uvicorn services.api.main_fixed:app --reload")
    logger.info("2. Login with admin credentials and change the password")
    logger.info("3. Create additional users as needed")
    logger.info("\nAPI Documentation will be available at:")
    logger.info("  http://localhost:8080/api/docs")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())