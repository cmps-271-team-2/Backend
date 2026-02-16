"""
Admin Schemas - Pydantic models for admin endpoints.
"""
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


# User Management Schemas
class ListUsersQuery(BaseModel):
    """Query parameters for listing users."""
    pageSize: int = Field(default=100, ge=1, le=1000, description="Number of users per page")
    pageToken: Optional[str] = Field(default=None, description="Token for pagination")


class UserDetailsResponse(BaseModel):
    """Response model for user details."""
    uid: str
    email: Optional[str]
    disabled: bool
    emailVerified: bool
    phoneNumber: Optional[str]
    displayName: Optional[str]
    photoURL: Optional[str]
    creationTimestamp: int
    lastSignInTimestamp: Optional[int]
    lastRefreshTimestamp: Optional[int]
    customClaims: Dict[str, Any]
    providerData: List[Dict[str, Any]]
    firestoreData: Optional[Dict[str, Any]]


class UpdateUserStatusBody(BaseModel):
    """Request body for updating user status."""
    disabled: bool = Field(description="Whether to disable or enable the user")


class SearchUsersQuery(BaseModel):
    """Query parameters for searching users."""
    email: str = Field(min_length=1, description="Email query string to search for")


class SetAdminRoleBody(BaseModel):
    """Request body for setting admin role."""
    isAdmin: bool = Field(description="Whether to grant or revoke admin role")


# OTP Management Schemas
class ListOTPRequestsQuery(BaseModel):
    """Query parameters for listing OTP requests."""
    limit: int = Field(default=100, ge=1, le=1000, description="Maximum number of OTP requests to return")


class OTPRequestResponse(BaseModel):
    """Response model for OTP request details."""
    uid: str
    email: str
    createdAt: str
    expiresAt: str
    verifyAttempts: int
    resendCount: int
    used: bool = False
    usedAt: Optional[str] = None
    lastSentAt: Optional[str] = None


# Analytics Schemas
class RegistrationStatsQuery(BaseModel):
    """Query parameters for registration statistics."""
    days: int = Field(default=30, ge=1, le=365, description="Number of days to include in statistics")


class DailyMetric(BaseModel):
    """Model for daily metric data."""
    date: str
    registrations: int
    verifications: int


class RegistrationStatsResponse(BaseModel):
    """Response model for registration statistics."""
    periodDays: int
    dailyData: List[DailyMetric]
    totalRegistrations: int
    totalVerifications: int
    verificationRate: float


class VerificationSuccessRateResponse(BaseModel):
    """Response model for verification success rate."""
    totalUsers: int
    verifiedUsers: int
    unverifiedUsers: int
    totalOTPRequests: int
    successfulOTPVerifications: int
    userVerificationRate: float
    otpSuccessRate: float


class DailyMetricsResponse(BaseModel):
    """Response model for daily metrics."""
    date: str
    newUsers: int
    verifiedUsers: int
    otpRequests: int
    otpVerifications: int
    verificationRate: float


class WeeklyMetricsResponse(BaseModel):
    """Response model for weekly metrics."""
    weekStart: str
    weekEnd: str
    newUsers: int
    verifiedUsers: int
    otpRequests: int
    otpVerifications: int
    verificationRate: float


# Generic Schemas
class SuccessResponse(BaseModel):
    """Generic success response."""
    message: str
    success: bool = True


class ErrorResponse(BaseModel):
    """Generic error response."""
    detail: str
    success: bool = False
