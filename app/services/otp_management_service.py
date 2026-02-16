"""
OTP Management Service - Business logic for OTP operations.
"""
from typing import List, Dict, Optional
from datetime import datetime, timezone
from app.services.firebase_service import get_firebase_service


class OTPManagementService:
    """Service class for OTP management operations."""
    
    def __init__(self):
        self.firebase_service = get_firebase_service()
    
    def list_pending_otp_requests(self, limit: int = 100) -> List[Dict]:
        """List all pending (not used and not expired) OTP requests."""
        otp_collection = self.firebase_service.get_firestore_collection("otp_requests")
        
        # Get all OTP requests
        otp_docs = otp_collection.where("used", "==", False).limit(limit).stream()
        
        now = datetime.now(timezone.utc)
        pending_requests = []
        
        for doc in otp_docs:
            data = doc.to_dict()
            expires_at = datetime.fromisoformat(data.get("expiresAt"))
            
            # Only include non-expired requests
            if expires_at > now:
                pending_requests.append({
                    "uid": doc.id,
                    "email": data.get("email"),
                    "createdAt": data.get("createdAt"),
                    "expiresAt": data.get("expiresAt"),
                    "verifyAttempts": data.get("verifyAttempts", 0),
                    "resendCount": data.get("resendCount", 0),
                })
        
        return pending_requests
    
    def get_otp_request_details(self, uid: str) -> Optional[Dict]:
        """Get details of a specific OTP request."""
        otp_doc = self.firebase_service.get_firestore_document("otp_requests", uid)
        
        if not otp_doc:
            return None
        
        return {
            "uid": uid,
            "email": otp_doc.get("email"),
            "createdAt": otp_doc.get("createdAt"),
            "expiresAt": otp_doc.get("expiresAt"),
            "verifyAttempts": otp_doc.get("verifyAttempts", 0),
            "resendCount": otp_doc.get("resendCount", 0),
            "used": otp_doc.get("used", False),
            "usedAt": otp_doc.get("usedAt"),
            "lastSentAt": otp_doc.get("lastSentAt"),
        }
    
    def clear_expired_otp_requests(self) -> Dict:
        """Clear all expired OTP requests from the database."""
        otp_collection = self.firebase_service.get_firestore_collection("otp_requests")
        
        now = datetime.now(timezone.utc)
        deleted_count = 0
        
        # Get all OTP requests
        otp_docs = otp_collection.stream()
        
        for doc in otp_docs:
            data = doc.to_dict()
            expires_at_str = data.get("expiresAt")
            
            if expires_at_str:
                expires_at = datetime.fromisoformat(expires_at_str)
                
                # Delete if expired
                if expires_at < now:
                    doc.reference.delete()
                    deleted_count += 1
        
        return {
            "deletedCount": deleted_count,
            "message": f"Cleared {deleted_count} expired OTP requests"
        }
    
    def get_otp_statistics(self) -> Dict:
        """Get OTP-related statistics."""
        otp_collection = self.firebase_service.get_firestore_collection("otp_requests")
        
        all_otp_docs = list(otp_collection.stream())
        total_requests = len(all_otp_docs)
        
        now = datetime.now(timezone.utc)
        
        used_count = 0
        expired_count = 0
        pending_count = 0
        total_attempts = 0
        total_resends = 0
        
        for doc in all_otp_docs:
            data = doc.to_dict()
            
            if data.get("used", False):
                used_count += 1
            else:
                expires_at = datetime.fromisoformat(data.get("expiresAt"))
                if expires_at < now:
                    expired_count += 1
                else:
                    pending_count += 1
            
            total_attempts += data.get("verifyAttempts", 0)
            total_resends += data.get("resendCount", 0)
        
        return {
            "totalRequests": total_requests,
            "usedRequests": used_count,
            "expiredRequests": expired_count,
            "pendingRequests": pending_count,
            "totalVerifyAttempts": total_attempts,
            "totalResends": total_resends,
            "averageAttempts": round(total_attempts / total_requests, 2) if total_requests > 0 else 0,
            "averageResends": round(total_resends / total_requests, 2) if total_requests > 0 else 0,
        }
    
    def revoke_otp_request(self, uid: str) -> Dict:
        """Manually revoke/delete an OTP request."""
        otp_collection = self.firebase_service.get_firestore_collection("otp_requests")
        otp_ref = otp_collection.document(uid)
        
        # Check if exists
        otp_doc = otp_ref.get()
        if not otp_doc.exists:
            return {
                "uid": uid,
                "success": False,
                "message": "OTP request not found"
            }
        
        otp_ref.delete()
        
        return {
            "uid": uid,
            "success": True,
            "message": "OTP request revoked successfully"
        }


# Singleton instance
_otp_management_service = None

def get_otp_management_service() -> OTPManagementService:
    """Get or create OTP Management service instance."""
    global _otp_management_service
    if _otp_management_service is None:
        _otp_management_service = OTPManagementService()
    return _otp_management_service
