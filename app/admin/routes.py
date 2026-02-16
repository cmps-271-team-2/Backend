"""
Admin Routes - API endpoints for admin operations.
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional

from app.admin.middleware import get_current_admin
from app.admin.schemas import (
    ListUsersQuery,
    UserDetailsResponse,
    UpdateUserStatusBody,
    SearchUsersQuery,
    SetAdminRoleBody,
    ListOTPRequestsQuery,
    OTPRequestResponse,
    RegistrationStatsQuery,
    RegistrationStatsResponse,
    VerificationSuccessRateResponse,
    DailyMetricsResponse,
    WeeklyMetricsResponse,
    SuccessResponse,
)

from app.services.user_management_service import get_user_management_service
from app.services.otp_management_service import get_otp_management_service
from app.services.analytics_service import get_analytics_service

router = APIRouter()


# ============================================================================
# User Management Endpoints
# ============================================================================

@router.get("/users", tags=["Admin - User Management"])
def list_users(
    pageSize: int = Query(default=100, ge=1, le=1000),
    pageToken: Optional[str] = Query(default=None),
    admin: dict = Depends(get_current_admin)
):
    """
    List all users with pagination.
    Requires admin authentication.
    """
    try:
        service = get_user_management_service()
        result = service.list_users(page_size=pageSize, page_token=pageToken)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list users: {str(e)}")


@router.get("/users/{uid}", response_model=UserDetailsResponse, tags=["Admin - User Management"])
def get_user_details(
    uid: str,
    admin: dict = Depends(get_current_admin)
):
    """
    Get detailed information about a specific user.
    Requires admin authentication.
    """
    try:
        service = get_user_management_service()
        user_details = service.get_user_details(uid)
        return user_details
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"User not found: {str(e)}")


@router.patch("/users/{uid}/status", tags=["Admin - User Management"])
def update_user_status(
    uid: str,
    body: UpdateUserStatusBody,
    admin: dict = Depends(get_current_admin)
):
    """
    Enable or disable a user account.
    Requires admin authentication.
    """
    try:
        service = get_user_management_service()
        result = service.update_user_status(uid, body.disabled)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update user status: {str(e)}")


@router.delete("/users/{uid}", tags=["Admin - User Management"])
def delete_user(
    uid: str,
    admin: dict = Depends(get_current_admin)
):
    """
    Delete a user account completely (Firebase Auth + Firestore).
    Requires admin authentication.
    """
    try:
        service = get_user_management_service()
        result = service.delete_user(uid)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete user: {str(e)}")


@router.get("/users/search/by-email", tags=["Admin - User Management"])
def search_users(
    email: str = Query(min_length=1),
    admin: dict = Depends(get_current_admin)
):
    """
    Search users by email pattern.
    Requires admin authentication.
    """
    try:
        service = get_user_management_service()
        results = service.search_users_by_email(email)
        return {"results": results, "count": len(results)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to search users: {str(e)}")


@router.post("/users/{uid}/admin-role", tags=["Admin - User Management"])
def set_admin_role(
    uid: str,
    body: SetAdminRoleBody,
    admin: dict = Depends(get_current_admin)
):
    """
    Grant or revoke admin role for a user.
    Requires admin authentication.
    """
    try:
        service = get_user_management_service()
        result = service.set_admin_role(uid, body.isAdmin)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to set admin role: {str(e)}")


@router.get("/users/stats/overview", tags=["Admin - User Management"])
def get_user_statistics(
    admin: dict = Depends(get_current_admin)
):
    """
    Get overall user statistics.
    Requires admin authentication.
    """
    try:
        service = get_user_management_service()
        stats = service.get_user_statistics()
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get user statistics: {str(e)}")


# ============================================================================
# OTP Management Endpoints
# ============================================================================

@router.get("/otp/pending", tags=["Admin - OTP Management"])
def list_pending_otp_requests(
    limit: int = Query(default=100, ge=1, le=1000),
    admin: dict = Depends(get_current_admin)
):
    """
    List all pending (not used and not expired) OTP requests.
    Requires admin authentication.
    """
    try:
        service = get_otp_management_service()
        requests = service.list_pending_otp_requests(limit=limit)
        return {"requests": requests, "count": len(requests)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list OTP requests: {str(e)}")


@router.get("/otp/{uid}", response_model=OTPRequestResponse, tags=["Admin - OTP Management"])
def get_otp_request_details(
    uid: str,
    admin: dict = Depends(get_current_admin)
):
    """
    Get details of a specific OTP request.
    Requires admin authentication.
    """
    try:
        service = get_otp_management_service()
        details = service.get_otp_request_details(uid)
        
        if not details:
            raise HTTPException(status_code=404, detail="OTP request not found")
        
        return details
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get OTP details: {str(e)}")


@router.delete("/otp/expired", tags=["Admin - OTP Management"])
def clear_expired_otp_requests(
    admin: dict = Depends(get_current_admin)
):
    """
    Clear all expired OTP requests from the database.
    Requires admin authentication.
    """
    try:
        service = get_otp_management_service()
        result = service.clear_expired_otp_requests()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clear expired OTPs: {str(e)}")


@router.get("/otp/stats/overview", tags=["Admin - OTP Management"])
def get_otp_statistics(
    admin: dict = Depends(get_current_admin)
):
    """
    Get OTP-related statistics.
    Requires admin authentication.
    """
    try:
        service = get_otp_management_service()
        stats = service.get_otp_statistics()
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get OTP statistics: {str(e)}")


@router.delete("/otp/{uid}", tags=["Admin - OTP Management"])
def revoke_otp_request(
    uid: str,
    admin: dict = Depends(get_current_admin)
):
    """
    Manually revoke/delete an OTP request.
    Requires admin authentication.
    """
    try:
        service = get_otp_management_service()
        result = service.revoke_otp_request(uid)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to revoke OTP request: {str(e)}")


# ============================================================================
# Analytics Endpoints
# ============================================================================

@router.get("/analytics/registrations", response_model=RegistrationStatsResponse, tags=["Admin - Analytics"])
def get_registration_statistics(
    days: int = Query(default=30, ge=1, le=365),
    admin: dict = Depends(get_current_admin)
):
    """
    Get user registration statistics for the last N days.
    Requires admin authentication.
    """
    try:
        service = get_analytics_service()
        stats = service.get_registration_statistics(days=days)
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get registration stats: {str(e)}")


@router.get("/analytics/verification-rate", response_model=VerificationSuccessRateResponse, tags=["Admin - Analytics"])
def get_verification_success_rate(
    admin: dict = Depends(get_current_admin)
):
    """
    Get verification success rate statistics.
    Requires admin authentication.
    """
    try:
        service = get_analytics_service()
        stats = service.get_verification_success_rate()
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get verification rate: {str(e)}")


@router.get("/analytics/daily", response_model=DailyMetricsResponse, tags=["Admin - Analytics"])
def get_daily_metrics(
    admin: dict = Depends(get_current_admin)
):
    """
    Get metrics for today.
    Requires admin authentication.
    """
    try:
        service = get_analytics_service()
        metrics = service.get_daily_metrics()
        return metrics
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get daily metrics: {str(e)}")


@router.get("/analytics/weekly", response_model=WeeklyMetricsResponse, tags=["Admin - Analytics"])
def get_weekly_metrics(
    admin: dict = Depends(get_current_admin)
):
    """
    Get metrics for the last 7 days.
    Requires admin authentication.
    """
    try:
        service = get_analytics_service()
        metrics = service.get_weekly_metrics()
        return metrics
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get weekly metrics: {str(e)}")
