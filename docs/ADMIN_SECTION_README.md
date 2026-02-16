# Admin Section - Backend Implementation

## Overview
This directory contains the admin section implementation using the services design pattern. The admin section provides endpoints for managing users, OTP requests, and viewing analytics.

## Architecture

### Services Layer (`/app/services/`)
The services layer encapsulates business logic and provides a clean interface for operations:

- **firebase_service.py**: Wrapper for Firebase Admin operations
- **user_management_service.py**: User management business logic
- **otp_management_service.py**: OTP request management logic
- **analytics_service.py**: Analytics and reporting logic

### Admin Module (`/app/admin/`)
The admin module contains the API layer:

- **routes.py**: FastAPI endpoints for admin operations
- **schemas.py**: Pydantic models for request/response validation
- **middleware.py**: Authentication and authorization middleware

## Authentication

All admin endpoints require:
1. Valid Firebase ID token in Authorization header
2. User must have `admin: true` custom claim

### Setting Admin Role

To set the first admin user, use Firebase Admin SDK:

```python
from firebase_admin import auth

# Set admin claim for a user
auth.set_custom_user_claims(uid, {'admin': True})
```

Or use the admin endpoint (if you already have an admin):
```bash
POST /admin/users/{uid}/admin-role
Authorization: Bearer <admin-token>
{
  "isAdmin": true
}
```

## API Endpoints

### User Management
- `GET /admin/users` - List all users
- `GET /admin/users/{uid}` - Get user details
- `PATCH /admin/users/{uid}/status` - Enable/disable user
- `DELETE /admin/users/{uid}` - Delete user
- `GET /admin/users/search/by-email` - Search users
- `POST /admin/users/{uid}/admin-role` - Set admin role
- `GET /admin/users/stats/overview` - User statistics

### OTP Management
- `GET /admin/otp/pending` - List pending OTP requests
- `GET /admin/otp/{uid}` - Get OTP details
- `DELETE /admin/otp/expired` - Clear expired OTPs
- `GET /admin/otp/stats/overview` - OTP statistics
- `DELETE /admin/otp/{uid}` - Revoke OTP request

### Analytics
- `GET /admin/analytics/registrations` - Registration stats
- `GET /admin/analytics/verification-rate` - Verification rates
- `GET /admin/analytics/daily` - Daily metrics
- `GET /admin/analytics/weekly` - Weekly metrics

## Usage Example

```python
from app.services.user_management_service import get_user_management_service

# Get service instance
service = get_user_management_service()

# List users
users = service.list_users(page_size=50)

# Get user details
user = service.get_user_details(uid="some-uid")

# Update user status
result = service.update_user_status(uid="some-uid", disabled=True)
```

## Testing Admin Endpoints

### Using curl:
```bash
# Get your Firebase ID token first
TOKEN="your-firebase-id-token"

# List users
curl -H "Authorization: Bearer $TOKEN" \
     http://localhost:8000/admin/users

# Get user statistics
curl -H "Authorization: Bearer $TOKEN" \
     http://localhost:8000/admin/users/stats/overview
```

### Using Python requests:
```python
import requests

token = "your-firebase-id-token"
headers = {"Authorization": f"Bearer {token}"}

# List users
response = requests.get(
    "http://localhost:8000/admin/users",
    headers=headers
)
print(response.json())
```

## Security Notes

1. **Authentication**: All endpoints verify Firebase ID token
2. **Authorization**: All endpoints check for admin claim
3. **Rate Limiting**: Consider adding rate limiting for production
4. **Audit Logging**: Consider logging admin actions
5. **Input Validation**: Pydantic schemas validate all inputs

## Integration with Existing Code

The admin section was designed to:
- **Leave existing code untouched**: All existing routes remain unchanged
- **Use services pattern**: Business logic is in services, not routes
- **Share Firebase instances**: Uses existing `get_firebase_auth()` and `get_db()`
- **Follow conventions**: Uses same patterns as existing auth code

## Frontend Integration

See `docs/ADMIN_FRONTEND_REQUIREMENTS.md` for:
- Complete API documentation
- Request/response examples
- Frontend implementation guide
- Sample code (JavaScript/React)
- Authentication flow
- Security best practices

## Development

### Adding New Admin Features

1. Add business logic to appropriate service in `/app/services/`
2. Add Pydantic schemas to `/app/admin/schemas.py`
3. Add route handler to `/app/admin/routes.py`
4. Use `Depends(get_current_admin)` for authentication

Example:
```python
@router.get("/admin/new-feature")
def new_feature(admin: dict = Depends(get_current_admin)):
    service = get_some_service()
    result = service.do_something()
    return result
```

### Testing

```bash
# Start the server
uvicorn app.main:app --reload --port 8000

# Visit Swagger UI
# http://localhost:8000/docs

# Test endpoints using Swagger UI or curl
```

## Dependencies

No new dependencies were added. Uses existing:
- fastapi
- firebase-admin
- pydantic

## Future Enhancements

Potential improvements:
1. Add audit logging for admin actions
2. Implement rate limiting
3. Add more detailed analytics
4. Export data functionality
5. Batch operations
6. Advanced search/filtering
7. Real-time dashboard updates
