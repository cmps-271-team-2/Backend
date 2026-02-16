"""
Admin Middleware - Authentication and authorization for admin endpoints.
"""
from fastapi import HTTPException, Header, Depends
from typing import Optional
from firebase_admin import auth as firebase_auth


async def verify_admin_token(authorization: Optional[str] = Header(None)) -> dict:
    """
    Verify Firebase ID token and check for admin role.
    
    Args:
        authorization: Authorization header with Bearer token
        
    Returns:
        dict: Decoded token with user claims
        
    Raises:
        HTTPException: If token is invalid or user is not an admin
    """
    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="Authorization header missing"
        )
    
    # Extract token from "Bearer <token>"
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail="Invalid authorization header format. Expected: Bearer <token>"
        )
    
    token = parts[1]
    
    try:
        # Verify the ID token
        decoded_token = firebase_auth.verify_id_token(token)
        
        # Check if user has admin claim
        if not decoded_token.get("admin", False):
            raise HTTPException(
                status_code=403,
                detail="Access denied. Admin privileges required."
            )
        
        return decoded_token
        
    except firebase_auth.InvalidIdTokenError:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token"
        )
    except firebase_auth.ExpiredIdTokenError:
        raise HTTPException(
            status_code=401,
            detail="Token has expired"
        )
    except firebase_auth.RevokedIdTokenError:
        raise HTTPException(
            status_code=401,
            detail="Token has been revoked"
        )
    except Exception as e:
        raise HTTPException(
            status_code=401,
            detail=f"Token verification failed: {str(e)}"
        )


async def get_current_admin(token_data: dict = Depends(verify_admin_token)) -> dict:
    """
    Dependency to get current admin user information.
    
    Args:
        token_data: Decoded token data from verify_admin_token
        
    Returns:
        dict: Admin user information
    """
    return {
        "uid": token_data.get("uid"),
        "email": token_data.get("email"),
        "admin": token_data.get("admin", False),
    }
