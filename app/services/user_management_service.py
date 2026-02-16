"""
User Management Service - Business logic for user operations.
"""
from typing import List, Dict, Optional
from datetime import datetime, timezone
from app.services.firebase_service import get_firebase_service


class UserManagementService:
    """Service class for user management operations."""
    
    def __init__(self):
        self.firebase_service = get_firebase_service()
    
    def list_users(self, page_size: int = 100, page_token: Optional[str] = None) -> Dict:
        """
        List all users with pagination.
        Returns users from both Firebase Auth and Firestore.
        """
        page = self.firebase_service.list_users(
            max_results=page_size, 
            page_token=page_token
        )
        
        users_list = []
        for user in page.users:
            # Get additional user data from Firestore
            firestore_data = self.firebase_service.get_firestore_document("users", user.uid)
            
            user_info = {
                "uid": user.uid,
                "email": user.email,
                "disabled": user.disabled,
                "emailVerified": user.email_verified,
                "creationTimestamp": user.user_metadata.creation_timestamp,
                "lastSignInTimestamp": user.user_metadata.last_sign_in_timestamp,
                "customClaims": user.custom_claims or {},
            }
            
            # Merge with Firestore data if available
            if firestore_data:
                user_info.update({
                    "isVerified": firestore_data.get("isVerified", False),
                    "createdAt": firestore_data.get("createdAt"),
                    "verifiedAt": firestore_data.get("verifiedAt"),
                })
            
            users_list.append(user_info)
        
        return {
            "users": users_list,
            "nextPageToken": page.next_page_token,
            "hasMore": page.has_next_page,
            "count": len(users_list)
        }
    
    def get_user_details(self, uid: str) -> Dict:
        """Get detailed user information."""
        # Get Firebase Auth data
        user = self.firebase_service.get_user_by_uid(uid)
        
        # Get Firestore data
        firestore_data = self.firebase_service.get_firestore_document("users", uid)
        
        user_details = {
            "uid": user.uid,
            "email": user.email,
            "disabled": user.disabled,
            "emailVerified": user.email_verified,
            "phoneNumber": user.phone_number,
            "displayName": user.display_name,
            "photoURL": user.photo_url,
            "creationTimestamp": user.user_metadata.creation_timestamp,
            "lastSignInTimestamp": user.user_metadata.last_sign_in_timestamp,
            "lastRefreshTimestamp": user.user_metadata.last_refresh_timestamp,
            "customClaims": user.custom_claims or {},
            "providerData": [
                {
                    "uid": provider.uid,
                    "providerId": provider.provider_id,
                    "email": provider.email,
                    "displayName": provider.display_name,
                    "photoUrl": provider.photo_url,
                }
                for provider in user.provider_data
            ],
        }
        
        # Add Firestore data
        if firestore_data:
            user_details["firestoreData"] = firestore_data
        
        return user_details
    
    def update_user_status(self, uid: str, disabled: bool) -> Dict:
        """Enable or disable a user account."""
        self.firebase_service.update_user(uid, disabled=disabled)
        return {
            "uid": uid,
            "disabled": disabled,
            "message": f"User {'disabled' if disabled else 'enabled'} successfully"
        }
    
    def delete_user(self, uid: str) -> Dict:
        """Delete a user account."""
        # Delete from Firebase Auth
        self.firebase_service.delete_user(uid)
        
        # Delete from Firestore
        users_ref = self.firebase_service.get_firestore_collection("users")
        users_ref.document(uid).delete()
        
        # Delete OTP requests if any
        otp_ref = self.firebase_service.get_firestore_collection("otp_requests")
        otp_ref.document(uid).delete()
        
        return {
            "uid": uid,
            "message": "User deleted successfully"
        }
    
    def search_users_by_email(self, email_query: str) -> List[Dict]:
        """Search users by email pattern."""
        users_collection = self.firebase_service.get_firestore_collection("users")
        
        # Query Firestore for emails containing the query
        # Note: This is a simple implementation. For production, consider using
        # a dedicated search service like Algolia or Elasticsearch
        query = users_collection.where("email", ">=", email_query.lower()).where(
            "email", "<=", email_query.lower() + "\uf8ff"
        ).limit(50)
        
        results = []
        for doc in query.stream():
            data = doc.to_dict()
            uid = doc.id
            
            # Get Firebase Auth data
            try:
                user = self.firebase_service.get_user_by_uid(uid)
                results.append({
                    "uid": uid,
                    "email": user.email,
                    "disabled": user.disabled,
                    "isVerified": data.get("isVerified", False),
                    "createdAt": data.get("createdAt"),
                })
            except Exception:
                # User might have been deleted from Firebase Auth
                continue
        
        return results
    
    def set_admin_role(self, uid: str, is_admin: bool = True) -> Dict:
        """Set or remove admin role for a user."""
        claims = {"admin": is_admin}
        self.firebase_service.set_custom_user_claims(uid, claims)
        
        return {
            "uid": uid,
            "isAdmin": is_admin,
            "message": f"Admin role {'granted' if is_admin else 'revoked'} successfully"
        }
    
    def get_user_statistics(self) -> Dict:
        """Get overall user statistics."""
        users_collection = self.firebase_service.get_firestore_collection("users")
        
        # Get all users
        all_users = list(users_collection.stream())
        total_users = len(all_users)
        
        # Count verified users
        verified_users = sum(1 for doc in all_users if doc.to_dict().get("isVerified", False))
        
        # Count users created in the last 24 hours
        now = datetime.now(timezone.utc)
        recent_users = 0
        for doc in all_users:
            created_at = doc.to_dict().get("createdAt")
            if created_at:
                created_dt = datetime.fromisoformat(created_at)
                if (now - created_dt).total_seconds() < 86400:  # 24 hours
                    recent_users += 1
        
        return {
            "totalUsers": total_users,
            "verifiedUsers": verified_users,
            "unverifiedUsers": total_users - verified_users,
            "recentUsers24h": recent_users,
            "verificationRate": round((verified_users / total_users * 100) if total_users > 0 else 0, 2)
        }


# Singleton instance
_user_management_service = None

def get_user_management_service() -> UserManagementService:
    """Get or create User Management service instance."""
    global _user_management_service
    if _user_management_service is None:
        _user_management_service = UserManagementService()
    return _user_management_service
