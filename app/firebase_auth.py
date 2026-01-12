import os
import json
import firebase_admin
from firebase_admin import credentials, auth
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.config import settings
from app.logging_config import get_logger

logger = get_logger(__name__)
security = HTTPBearer()


def initialize_firebase():
    """
    Initialize Firebase Admin SDK.
    
    Loads credentials from file path or JSON string (for deployment).
    Only initializes once if not already initialized.
    """
    if firebase_admin._apps:
        logger.info("Firebase already initialized")
        return
    
    try:
        # Try to load from file path first
        credentials_path = settings.FIREBASE_CREDENTIALS_PATH
        
        if os.path.exists(credentials_path):
            logger.info(f"Loading Firebase credentials from file: {credentials_path}")
            cred = credentials.Certificate(credentials_path)
        else:
            logger.warning(f"Firebase credentials file not found at: {credentials_path}")
            raise FileNotFoundError(f"Firebase credentials file not found: {credentials_path}")
        
        firebase_admin.initialize_app(cred)
        logger.info("Firebase Admin SDK initialized successfully")
        
    except Exception as e:
        logger.error(f"Failed to initialize Firebase: {str(e)}")
        raise RuntimeError(f"Firebase initialization failed: {str(e)}")


async def verify_firebase_token(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict:
    """
    Verify Firebase ID token from Authorization header.
    
    Args:
        credentials: HTTP Bearer token credentials
        
    Returns:
        dict: Decoded token data containing user information
        
    Raises:
        HTTPException: If token is invalid or verification fails
    """
    try:
        token = credentials.credentials
        decoded_token = auth.verify_id_token(token)
        
        logger.debug(f"Token verified for user: {decoded_token.get('uid')}")
        return decoded_token
        
    except auth.InvalidIdTokenError:
        logger.warning("Invalid Firebase ID token provided")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except auth.ExpiredIdTokenError:
        logger.warning("Expired Firebase ID token provided")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        logger.error(f"Token verification failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user(token_data: dict = Depends(verify_firebase_token)) -> dict:
    """
    Get current authenticated user information from Firebase token.
    
    Args:
        token_data: Decoded Firebase token data
        
    Returns:
        dict: User information including uid, email, and verification status
    """
    return {
        "uid": token_data.get("uid"),
        "email": token_data.get("email"),
        "email_verified": token_data.get("email_verified", False),
        "name": token_data.get("name"),
    }


async def require_admin(token_data: dict = Depends(verify_firebase_token)) -> dict:
    """
    Verify that the authenticated user has admin privileges.
    
    Checks for 'admin' custom claim in the Firebase token.
    
    Args:
        token_data: Decoded Firebase token data
        
    Returns:
        dict: User information if admin
        
    Raises:
        HTTPException: If user does not have admin privileges
    """
    # Check if user has admin custom claim
    is_admin = token_data.get("admin", False)
    
    if not is_admin:
        logger.warning(
            f"Access denied: User {token_data.get('uid')} attempted to access admin endpoint"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required. You do not have sufficient permissions."
        )
    
    logger.info(f"Admin access granted for user: {token_data.get('uid')}")
    return {
        "uid": token_data.get("uid"),
        "email": token_data.get("email"),
        "email_verified": token_data.get("email_verified", False),
        "name": token_data.get("name"),
        "admin": True,
    }
