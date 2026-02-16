"""
Analytics Service - Business logic for analytics and reporting.
"""
from typing import Dict, List
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from app.services.firebase_service import get_firebase_service


class AnalyticsService:
    """Service class for analytics and reporting operations."""
    
    def __init__(self):
        self.firebase_service = get_firebase_service()
    
    def get_registration_statistics(self, days: int = 30) -> Dict:
        """Get user registration statistics for the last N days."""
        users_collection = self.firebase_service.get_firestore_collection("users")
        
        now = datetime.now(timezone.utc)
        cutoff_date = now - timedelta(days=days)
        
        # Get all users
        all_users = list(users_collection.stream())
        
        # Group by date
        registrations_by_date = defaultdict(int)
        verifications_by_date = defaultdict(int)
        
        for doc in all_users:
            data = doc.to_dict()
            
            # Count registrations
            created_at_str = data.get("createdAt")
            if created_at_str:
                try:
                    created_at = datetime.fromisoformat(created_at_str)
                    # Ensure timezone awareness for comparison
                    if created_at.tzinfo is None:
                        created_at = created_at.replace(tzinfo=timezone.utc)
                    if created_at >= cutoff_date:
                        date_key = created_at.date().isoformat()
                        registrations_by_date[date_key] += 1
                except (ValueError, TypeError):
                    # Skip invalid datetime strings
                    pass
            
            # Count verifications
            verified_at_str = data.get("verifiedAt")
            if verified_at_str:
                try:
                    verified_at = datetime.fromisoformat(verified_at_str)
                    # Ensure timezone awareness for comparison
                    if verified_at.tzinfo is None:
                        verified_at = verified_at.replace(tzinfo=timezone.utc)
                    if verified_at >= cutoff_date:
                        date_key = verified_at.date().isoformat()
                        verifications_by_date[date_key] += 1
                except (ValueError, TypeError):
                    # Skip invalid datetime strings
                    pass
        
        # Convert to sorted lists
        daily_data = []
        for i in range(days):
            date = (now - timedelta(days=days - i - 1)).date()
            date_key = date.isoformat()
            daily_data.append({
                "date": date_key,
                "registrations": registrations_by_date.get(date_key, 0),
                "verifications": verifications_by_date.get(date_key, 0),
            })
        
        total_registrations = sum(d["registrations"] for d in daily_data)
        total_verifications = sum(d["verifications"] for d in daily_data)
        
        return {
            "periodDays": days,
            "dailyData": daily_data,
            "totalRegistrations": total_registrations,
            "totalVerifications": total_verifications,
            "verificationRate": round((total_verifications / total_registrations * 100) 
                                    if total_registrations > 0 else 0, 2)
        }
    
    def get_verification_success_rate(self) -> Dict:
        """Calculate verification success rate."""
        users_collection = self.firebase_service.get_firestore_collection("users")
        
        all_users = list(users_collection.stream())
        total_users = len(all_users)
        
        verified_users = sum(1 for doc in all_users if doc.to_dict().get("isVerified", False))
        
        # Get OTP statistics
        otp_collection = self.firebase_service.get_firestore_collection("otp_requests")
        all_otp_requests = list(otp_collection.stream())
        
        successful_verifications = sum(1 for doc in all_otp_requests 
                                      if doc.to_dict().get("used", False))
        
        total_otp_requests = len(all_otp_requests)
        
        return {
            "totalUsers": total_users,
            "verifiedUsers": verified_users,
            "unverifiedUsers": total_users - verified_users,
            "totalOTPRequests": total_otp_requests,
            "successfulOTPVerifications": successful_verifications,
            "userVerificationRate": round((verified_users / total_users * 100) 
                                         if total_users > 0 else 0, 2),
            "otpSuccessRate": round((successful_verifications / total_otp_requests * 100) 
                                   if total_otp_requests > 0 else 0, 2),
        }
    
    def get_daily_metrics(self) -> Dict:
        """Get metrics for today."""
        users_collection = self.firebase_service.get_firestore_collection("users")
        otp_collection = self.firebase_service.get_firestore_collection("otp_requests")
        
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Users created today
        users_today = 0
        verified_today = 0
        
        for doc in users_collection.stream():
            data = doc.to_dict()
            
            created_at_str = data.get("createdAt")
            if created_at_str:
                try:
                    created_at = datetime.fromisoformat(created_at_str)
                    # Ensure timezone awareness for comparison
                    if created_at.tzinfo is None:
                        created_at = created_at.replace(tzinfo=timezone.utc)
                    if created_at >= today_start:
                        users_today += 1
                except (ValueError, TypeError):
                    pass
            
            verified_at_str = data.get("verifiedAt")
            if verified_at_str:
                try:
                    verified_at = datetime.fromisoformat(verified_at_str)
                    # Ensure timezone awareness for comparison
                    if verified_at.tzinfo is None:
                        verified_at = verified_at.replace(tzinfo=timezone.utc)
                    if verified_at >= today_start:
                        verified_today += 1
                except (ValueError, TypeError):
                    pass
        
        # OTP requests today
        otp_requests_today = 0
        otp_verified_today = 0
        
        for doc in otp_collection.stream():
            data = doc.to_dict()
            
            created_at_str = data.get("createdAt")
            if created_at_str:
                try:
                    created_at = datetime.fromisoformat(created_at_str)
                    # Ensure timezone awareness for comparison
                    if created_at.tzinfo is None:
                        created_at = created_at.replace(tzinfo=timezone.utc)
                    if created_at >= today_start:
                        otp_requests_today += 1
                        
                        if data.get("used", False):
                            otp_verified_today += 1
                except (ValueError, TypeError):
                    pass
        
        return {
            "date": now.date().isoformat(),
            "newUsers": users_today,
            "verifiedUsers": verified_today,
            "otpRequests": otp_requests_today,
            "otpVerifications": otp_verified_today,
            "verificationRate": round((verified_today / users_today * 100) 
                                     if users_today > 0 else 0, 2)
        }
    
    def get_weekly_metrics(self) -> Dict:
        """Get metrics for the last 7 days."""
        users_collection = self.firebase_service.get_firestore_collection("users")
        otp_collection = self.firebase_service.get_firestore_collection("otp_requests")
        
        now = datetime.now(timezone.utc)
        week_start = now - timedelta(days=7)
        
        users_this_week = 0
        verified_this_week = 0
        
        for doc in users_collection.stream():
            data = doc.to_dict()
            
            created_at_str = data.get("createdAt")
            if created_at_str:
                try:
                    created_at = datetime.fromisoformat(created_at_str)
                    # Ensure timezone awareness for comparison
                    if created_at.tzinfo is None:
                        created_at = created_at.replace(tzinfo=timezone.utc)
                    if created_at >= week_start:
                        users_this_week += 1
                except (ValueError, TypeError):
                    pass
            
            verified_at_str = data.get("verifiedAt")
            if verified_at_str:
                try:
                    verified_at = datetime.fromisoformat(verified_at_str)
                    # Ensure timezone awareness for comparison
                    if verified_at.tzinfo is None:
                        verified_at = verified_at.replace(tzinfo=timezone.utc)
                    if verified_at >= week_start:
                        verified_this_week += 1
                except (ValueError, TypeError):
                    pass
        
        otp_requests_this_week = 0
        otp_verified_this_week = 0
        
        for doc in otp_collection.stream():
            data = doc.to_dict()
            
            created_at_str = data.get("createdAt")
            if created_at_str:
                try:
                    created_at = datetime.fromisoformat(created_at_str)
                    # Ensure timezone awareness for comparison
                    if created_at.tzinfo is None:
                        created_at = created_at.replace(tzinfo=timezone.utc)
                    if created_at >= week_start:
                        otp_requests_this_week += 1
                        
                        if data.get("used", False):
                            otp_verified_this_week += 1
                except (ValueError, TypeError):
                    pass
        
        return {
            "weekStart": week_start.date().isoformat(),
            "weekEnd": now.date().isoformat(),
            "newUsers": users_this_week,
            "verifiedUsers": verified_this_week,
            "otpRequests": otp_requests_this_week,
            "otpVerifications": otp_verified_this_week,
            "verificationRate": round((verified_this_week / users_this_week * 100) 
                                     if users_this_week > 0 else 0, 2)
        }


# Singleton instance
_analytics_service = None

def get_analytics_service() -> AnalyticsService:
    """Get or create Analytics service instance."""
    global _analytics_service
    if _analytics_service is None:
        _analytics_service = AnalyticsService()
    return _analytics_service
