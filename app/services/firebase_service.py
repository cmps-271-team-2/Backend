"""
Firebase Service - Wrapper for Firebase operations.
Provides a clean interface for Firebase Admin operations.
"""
from typing import List, Dict, Optional
from firebase_admin import auth, firestore
from app.core.firebase_admin import get_firebase_auth
from app.core.firestore import get_db


class FirebaseService:
    """Service class for Firebase operations."""
    
    def __init__(self):
        self.auth = get_firebase_auth()
        self.db = get_db()
    
    def get_user_by_email(self, email: str):
        """Get Firebase user by email."""
        return self.auth.get_user_by_email(email)
    
    def get_user_by_uid(self, uid: str):
        """Get Firebase user by UID."""
        return self.auth.get_user(uid)
    
    def update_user(self, uid: str, **kwargs):
        """Update Firebase user."""
        return self.auth.update_user(uid, **kwargs)
    
    def delete_user(self, uid: str):
        """Delete Firebase user."""
        return self.auth.delete_user(uid)
    
    def list_users(self, max_results: int = 1000, page_token: Optional[str] = None):
        """List Firebase users with pagination."""
        return self.auth.list_users(max_results=max_results, page_token=page_token)
    
    def set_custom_user_claims(self, uid: str, claims: Dict):
        """Set custom claims for user (e.g., admin role)."""
        return self.auth.set_custom_user_claims(uid, claims)
    
    def get_firestore_collection(self, collection_name: str):
        """Get Firestore collection reference."""
        return self.db.collection(collection_name)
    
    def get_firestore_document(self, collection_name: str, document_id: str):
        """Get Firestore document."""
        doc = self.db.collection(collection_name).document(document_id).get()
        return doc.to_dict() if doc.exists else None


# Singleton instance
_firebase_service = None

def get_firebase_service() -> FirebaseService:
    """Get or create Firebase service instance."""
    global _firebase_service
    if _firebase_service is None:
        _firebase_service = FirebaseService()
    return _firebase_service
