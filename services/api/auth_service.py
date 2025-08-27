"""
Authentication service with database-backed user management
"""

from datetime import datetime, timedelta
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session
import secrets
import logging

from services.api.config import settings
from services.api.database import get_db, User as UserModel
from services.api.models import User, UserCreate, Token

logger = logging.getLogger(__name__)

# Security configuration
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against hash"""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """Hash password with bcrypt"""
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Create JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.access_token_expire_minutes)
    
    to_encode.update({"exp": expire, "type": "access"})
    encoded_jwt = jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return encoded_jwt

def create_refresh_token(data: dict) -> str:
    """Create refresh token (longer lived)"""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=7)
    to_encode.update({"exp": expire, "type": "refresh"})
    encoded_jwt = jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return encoded_jwt

def create_api_key() -> tuple[str, str]:
    """Generate API key (returns raw key and hash)"""
    raw_key = f"gvn_{secrets.token_urlsafe(32)}"
    key_hash = pwd_context.hash(raw_key)
    return raw_key, key_hash

def verify_api_key(raw_key: str, key_hash: str) -> bool:
    """Verify API key against hash"""
    return pwd_context.verify(raw_key, key_hash)

class AuthService:
    """Authentication service with database operations"""
    
    @staticmethod
    def authenticate_user(db: Session, username: str, password: str) -> Optional[UserModel]:
        """Authenticate user with username and password"""
        user = db.query(UserModel).filter(
            (UserModel.username == username) | (UserModel.email == username)
        ).first()
        
        if not user:
            logger.warning(f"Authentication failed: User not found {username}")
            return None
            
        if not verify_password(password, user.hashed_password):
            logger.warning(f"Authentication failed: Invalid password for {username}")
            return None
            
        if not user.is_active:
            logger.warning(f"Authentication failed: Inactive user {username}")
            return None
            
        # Update last login
        user.last_login = datetime.utcnow()
        db.commit()
        
        logger.info(f"User authenticated successfully: {username}")
        return user
    
    @staticmethod
    def create_user(db: Session, user_create: UserCreate) -> UserModel:
        """Create new user"""
        # Check if user exists
        existing = db.query(UserModel).filter(
            (UserModel.username == user_create.username) |
            (UserModel.email == user_create.email)
        ).first()
        
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username or email already registered"
            )
        
        # Create new user
        db_user = UserModel(
            username=user_create.username,
            email=user_create.email,
            full_name=user_create.full_name,
            hashed_password=get_password_hash(user_create.password),
            role=user_create.role or "user",
            is_active=True,
            is_superuser=user_create.is_superuser or False
        )
        
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        
        logger.info(f"New user created: {user_create.username}")
        return db_user
    
    @staticmethod
    def get_user_by_id(db: Session, user_id: str) -> Optional[UserModel]:
        """Get user by ID"""
        return db.query(UserModel).filter(UserModel.id == user_id).first()
    
    @staticmethod
    def get_user_by_username(db: Session, username: str) -> Optional[UserModel]:
        """Get user by username"""
        return db.query(UserModel).filter(UserModel.username == username).first()
    
    @staticmethod
    def update_password(db: Session, user_id: str, new_password: str) -> bool:
        """Update user password"""
        user = db.query(UserModel).filter(UserModel.id == user_id).first()
        if not user:
            return False
            
        user.hashed_password = get_password_hash(new_password)
        user.updated_at = datetime.utcnow()
        db.commit()
        
        logger.info(f"Password updated for user: {user.username}")
        return True
    
    @staticmethod
    def deactivate_user(db: Session, user_id: str) -> bool:
        """Deactivate user account"""
        user = db.query(UserModel).filter(UserModel.id == user_id).first()
        if not user:
            return False
            
        user.is_active = False
        user.updated_at = datetime.utcnow()
        db.commit()
        
        logger.info(f"User deactivated: {user.username}")
        return True

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> User:
    """Get current authenticated user from JWT token"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = jwt.decode(
            token, 
            settings.jwt_secret_key, 
            algorithms=[settings.jwt_algorithm]
        )
        
        # Verify token type
        if payload.get("type") != "access":
            raise credentials_exception
            
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
            
    except JWTError as e:
        logger.warning(f"JWT validation failed: {e}")
        raise credentials_exception
    
    # Get user from database
    user = AuthService.get_user_by_id(db, user_id)
    if user is None:
        raise credentials_exception
        
    return User(
        id=user.id,
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
        is_superuser=user.is_superuser
    )

async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """Get current active user"""
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
    return current_user

class RoleChecker:
    """Check if user has required role"""
    def __init__(self, allowed_roles: list):
        self.allowed_roles = allowed_roles

    def __call__(self, user: User = Depends(get_current_active_user)):
        if user.role not in self.allowed_roles and not user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Operation not permitted for your role"
            )
        return user

# Dependency functions for protected routes
require_user = Depends(get_current_active_user)
require_admin = Depends(RoleChecker(["admin", "superuser"]))
require_researcher = Depends(RoleChecker(["researcher", "admin", "superuser"]))