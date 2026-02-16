# Admin Section - Quick Start Guide

## 🚀 Quick Start

The admin section is now live! Here's how to get started.

## ✅ What Was Added

- **16 Admin Endpoints** organized in 3 categories
- **Services Layer** for clean business logic separation
- **Authentication** via Firebase ID tokens
- **Authorization** with admin role checking
- **Complete Documentation** for frontend integration

## 🔑 First-Time Setup

### 1. Set Your First Admin User

You need to manually set the first admin user. Run this Python code:

```python
from firebase_admin import auth

# Replace with actual user UID from Firebase Console
user_uid = "your-user-uid-here"

# Grant admin privileges
auth.set_custom_user_claims(user_uid, {'admin': True})

print(f"✓ Admin role granted to user {user_uid}")
```

### 2. Get Your ID Token

In your frontend app or using Firebase Console:

```javascript
// JavaScript
const user = firebase.auth().currentUser;
const token = await user.getIdToken();
console.log('Your ID Token:', token);
```

### 3. Test the Endpoints

```bash
# Replace TOKEN with your actual Firebase ID token
TOKEN="your-firebase-id-token"

# Get user statistics
curl -H "Authorization: Bearer $TOKEN" \
     http://localhost:8000/admin/users/stats/overview

# List users
curl -H "Authorization: Bearer $TOKEN" \
     http://localhost:8000/admin/users?pageSize=10
```

## 📋 Available Endpoints

### User Management
- `GET /admin/users` - List all users
- `GET /admin/users/{uid}` - User details
- `PATCH /admin/users/{uid}/status` - Enable/disable
- `DELETE /admin/users/{uid}` - Delete user
- `GET /admin/users/search/by-email` - Search
- `POST /admin/users/{uid}/admin-role` - Set admin
- `GET /admin/users/stats/overview` - Statistics

### OTP Management
- `GET /admin/otp/pending` - Pending OTPs
- `GET /admin/otp/{uid}` - OTP details
- `DELETE /admin/otp/expired` - Clear expired
- `GET /admin/otp/stats/overview` - Statistics
- `DELETE /admin/otp/{uid}` - Revoke OTP

### Analytics
- `GET /admin/analytics/registrations` - Registration stats
- `GET /admin/analytics/verification-rate` - Success rates
- `GET /admin/analytics/daily` - Today's metrics
- `GET /admin/analytics/weekly` - Weekly metrics

## 🌐 Interactive API Docs

The easiest way to test is using Swagger UI:

1. Start the server: `uvicorn app.main:app --reload`
2. Open browser: http://localhost:8000/docs
3. Click "Authorize" button
4. Enter: `Bearer your-token-here`
5. Try any endpoint!

## 📚 Full Documentation

- **Backend Guide**: `docs/ADMIN_SECTION_README.md`
- **Frontend Guide**: `docs/ADMIN_FRONTEND_REQUIREMENTS.md`

## 🎯 Example Use Cases

### Grant Admin to Another User
```bash
curl -X POST "http://localhost:8000/admin/users/{uid}/admin-role" \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"isAdmin": true}'
```

### Get Today's Metrics
```bash
curl "http://localhost:8000/admin/analytics/daily" \
     -H "Authorization: Bearer $TOKEN"
```

### Search for a User
```bash
curl "http://localhost:8000/admin/users/search/by-email?email=john" \
     -H "Authorization: Bearer $TOKEN"
```

### Disable a User Account
```bash
curl -X PATCH "http://localhost:8000/admin/users/{uid}/status" \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"disabled": true}'
```

## 🔐 Security Notes

- All endpoints require authentication
- Only users with `admin: true` claim can access
- Tokens expire after 1 hour (get a fresh one)
- Use HTTPS in production
- Never commit tokens to git

## ❓ Troubleshooting

**401 Unauthorized**
- Check your token is valid
- Token might be expired (get a new one)
- Make sure format is `Bearer <token>`

**403 Forbidden**
- User doesn't have admin role
- Grant admin: `auth.set_custom_user_claims(uid, {'admin': True})`

**404 Not Found**
- Check the endpoint URL
- Make sure user/resource exists

## 👥 Getting Help

- Check Swagger UI: http://localhost:8000/docs
- Read documentation in `docs/` folder
- Review sample code in frontend guide
- Check existing auth endpoints for patterns

## 🎉 You're Ready!

The admin section is fully functional. Start building your admin dashboard!
