#!/usr/bin/env python3
"""
Generate secure secrets for production deployment
"""

import secrets
import base64
import os
from pathlib import Path

def generate_jwt_secret(length: int = 64) -> str:
    """Generate cryptographically secure JWT secret"""
    return base64.b64encode(secrets.token_bytes(length)).decode('utf-8')

def generate_database_password(length: int = 32) -> str:
    """Generate secure database password"""
    # Use URL-safe characters to avoid escaping issues
    return secrets.token_urlsafe(length)

def generate_api_key() -> str:
    """Generate API key with prefix"""
    return f"gvn_{secrets.token_urlsafe(32)}"

def update_env_file():
    """Update .env file with secure values"""
    env_path = Path(__file__).parent.parent / ".env"
    
    # Generate secure values
    jwt_secret = generate_jwt_secret()
    db_password = generate_database_password()
    redis_password = generate_database_password(24)
    minio_password = generate_database_password(24)
    
    # Read existing .env or create from template
    if env_path.exists():
        print(f"Reading existing {env_path}")
        with open(env_path, 'r') as f:
            lines = f.readlines()
    else:
        template_path = Path(__file__).parent.parent / ".env.template"
        if template_path.exists():
            print(f"Creating .env from template")
            with open(template_path, 'r') as f:
                lines = f.readlines()
        else:
            print("No .env or .env.template found")
            return
    
    # Update with secure values
    replacements = {
        'JWT_SECRET_KEY=': f'JWT_SECRET_KEY={jwt_secret}',
        'POSTGRES_PASSWORD=': f'POSTGRES_PASSWORD={db_password}',
        'DATABASE_URL=': f'DATABASE_URL=postgresql://galvana:{db_password}@localhost:5432/galvana_dev',
        'REDIS_PASSWORD=': f'REDIS_PASSWORD={redis_password}',
        'REDIS_URL=': f'REDIS_URL=redis://:{redis_password}@localhost:6379/0',
        'MINIO_ROOT_PASSWORD=': f'MINIO_ROOT_PASSWORD={minio_password}',
        'S3_SECRET_KEY=': f'S3_SECRET_KEY={minio_password}',
    }
    
    updated_lines = []
    for line in lines:
        updated = False
        for key, value in replacements.items():
            if line.strip().startswith(key):
                updated_lines.append(f"{value}\n")
                updated = True
                print(f"✓ Updated {key.rstrip('=')}")
                break
        if not updated:
            updated_lines.append(line)
    
    # Write updated .env
    with open(env_path, 'w') as f:
        f.writelines(updated_lines)
    
    # Set restrictive permissions
    os.chmod(env_path, 0o600)
    
    print(f"\n✅ Secure .env file created at {env_path}")
    print("⚠️  Keep this file secret and never commit to version control!")
    
    # Create backup of secrets
    backup_path = Path(__file__).parent.parent / ".env.backup"
    with open(backup_path, 'w') as f:
        f.write(f"# Backup of generated secrets - {secrets.token_urlsafe(8)}\n")
        f.write(f"# Generated at: {os.popen('date').read()}\n")
        f.write(f"JWT_SECRET_KEY={jwt_secret}\n")
        f.write(f"DB_PASSWORD={db_password}\n")
        f.write(f"REDIS_PASSWORD={redis_password}\n")
        f.write(f"MINIO_PASSWORD={minio_password}\n")
    
    os.chmod(backup_path, 0o600)
    print(f"📁 Backup saved to {backup_path}")

def main():
    """Main function"""
    print("🔐 Generating secure secrets for Galvana platform\n")
    
    # Check if .env already exists
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        response = input("⚠️  .env file exists. Overwrite? (y/N): ")
        if response.lower() != 'y':
            print("Aborted.")
            return
    
    update_env_file()
    
    print("\n📝 Next steps:")
    print("1. Review the generated .env file")
    print("2. Update any environment-specific settings")
    print("3. Restart your services to use new secrets")
    print("4. Store backup securely (password manager/secret vault)")

if __name__ == "__main__":
    main()