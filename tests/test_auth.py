"""
Test authentication and authorization
"""

import pytest
from fastapi.testclient import TestClient
from datetime import timedelta
from services.api.auth import (
    verify_password,
    get_password_hash,
    authenticate_user,
    create_access_token,
    get_user
)

def test_password_hashing():
    """Test password hashing and verification"""
    password = "test_password_123"
    hashed = get_password_hash(password)
    
    assert hashed != password
    assert verify_password(password, hashed)
    assert not verify_password("wrong_password", hashed)

def test_authenticate_user():
    """Test user authentication"""
    # Test with demo user
    user = authenticate_user("demo_user", "secret")
    assert user is not None
    assert user.username == "demo_user"
    
    # Test with wrong password
    user = authenticate_user("demo_user", "wrong_password")
    assert user is None
    
    # Test with non-existent user
    user = authenticate_user("non_existent", "password")
    assert user is None

def test_create_access_token():
    """Test JWT token creation"""
    data = {"sub": "test_user"}
    token = create_access_token(data)
    
    assert token is not None
    assert isinstance(token, str)
    assert len(token) > 0
    
    # Test with custom expiration
    token_with_expiry = create_access_token(
        data, 
        expires_delta=timedelta(minutes=5)
    )
    assert token_with_expiry is not None

def test_get_user():
    """Test getting user from database"""
    user = get_user("demo_user")
    assert user is not None
    assert user.username == "demo_user"
    assert user.email == "demo@galvana.com"
    
    # Test non-existent user
    user = get_user("non_existent")
    assert user is None

@pytest.mark.asyncio
async def test_login_endpoint(client: TestClient):
    """Test login endpoint"""
    response = client.post(
        "/api/v1/auth/token",
        data={
            "username": "demo_user",
            "password": "secret"
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"

@pytest.mark.asyncio
async def test_login_invalid_credentials(client: TestClient):
    """Test login with invalid credentials"""
    response = client.post(
        "/api/v1/auth/token",
        data={
            "username": "demo_user",
            "password": "wrong_password"
        }
    )
    
    assert response.status_code == 401
    assert "Incorrect username or password" in response.json()["detail"]

@pytest.mark.asyncio
async def test_protected_endpoint_without_token(client: TestClient):
    """Test accessing protected endpoint without token"""
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401

@pytest.mark.asyncio
async def test_protected_endpoint_with_token(client: TestClient, auth_headers: dict):
    """Test accessing protected endpoint with valid token"""
    response = client.get("/api/v1/auth/me", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "demo_user"