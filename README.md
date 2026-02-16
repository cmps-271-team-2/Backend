# Backend (FastAPI)

## Overview

This is the backend API for the AUB Email Verification System. It provides authentication services and an admin section for managing users, OTP requests, and viewing analytics.

## Features

- **User Authentication**: Email verification with OTP for @mail.aub.edu addresses
- **Admin Section**: Comprehensive admin panel with user management, OTP management, and analytics
- **Services Design Pattern**: Clean separation of business logic and API layer
- **Firebase Integration**: Uses Firebase Auth and Firestore

## Local development

1) Create and activate a virtual environment

```bash
python -m venv venv

# Windows (PowerShell)
venv\Scripts\Activate.ps1

# Windows (cmd)
venv\Scripts\activate.bat

# Linux/Mac
source venv/bin/activate
```

2) Install dependencies

```bash
pip install -r requirements.txt
```

3) Ensure `.env` is present and includes CORS origins

```bash
FRONTEND_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
```

4) Start the API

```bash
uvicorn app.main:app --reload --port 8000
```

Health check:
- http://127.0.0.1:8000/

API Documentation:
- http://127.0.0.1:8000/docs (Swagger UI)
- http://127.0.0.1:8000/redoc (ReDoc)

## API Endpoints

### Authentication (`/auth`)
- `POST /auth/register/request-otp` - Request OTP for registration
- `POST /auth/register/verify-otp` - Verify OTP and activate account
- `POST /auth/register/resend-otp` - Resend OTP code

### Admin (`/admin`)

**User Management:**
- `GET /admin/users` - List all users
- `GET /admin/users/{uid}` - Get user details
- `PATCH /admin/users/{uid}/status` - Enable/disable user
- `DELETE /admin/users/{uid}` - Delete user
- `GET /admin/users/search/by-email` - Search users
- `POST /admin/users/{uid}/admin-role` - Grant/revoke admin role
- `GET /admin/users/stats/overview` - User statistics

**OTP Management:**
- `GET /admin/otp/pending` - List pending OTP requests
- `GET /admin/otp/{uid}` - Get OTP details
- `DELETE /admin/otp/expired` - Clear expired OTPs
- `GET /admin/otp/stats/overview` - OTP statistics
- `DELETE /admin/otp/{uid}` - Revoke OTP

**Analytics:**
- `GET /admin/analytics/registrations` - Registration statistics
- `GET /admin/analytics/verification-rate` - Verification rates
- `GET /admin/analytics/daily` - Daily metrics
- `GET /admin/analytics/weekly` - Weekly metrics

## Admin Access

All admin endpoints require Firebase authentication with admin privileges.

To set the first admin user:
```python
from firebase_admin import auth
auth.set_custom_user_claims('user-uid', {'admin': True})
```

See `docs/ADMIN_SECTION_README.md` for details.

## Documentation

- **[Admin Section README](docs/ADMIN_SECTION_README.md)** - Backend implementation details
- **[Admin Frontend Requirements](docs/ADMIN_FRONTEND_REQUIREMENTS.md)** - Frontend integration guide

## Project Structure

```
Backend/
├── app/
│   ├── admin/              # Admin module
│   │   ├── middleware.py   # Authentication & authorization
│   │   ├── routes.py       # Admin API endpoints
│   │   └── schemas.py      # Pydantic models
│   ├── auth/               # Authentication module
│   │   ├── routes.py       # Auth endpoints
│   │   ├── schemas.py      # Auth models
│   │   └── otp_service.py  # OTP logic
│   ├── core/               # Core utilities
│   │   ├── firebase_admin.py
│   │   ├── firestore.py
│   │   └── email_sender.py
│   ├── services/           # Business logic layer
│   │   ├── firebase_service.py
│   │   ├── user_management_service.py
│   │   ├── otp_management_service.py
│   │   └── analytics_service.py
│   └── main.py             # FastAPI application
├── docs/                   # Documentation
├── requirements.txt        # Python dependencies
└── README.md              # This file
```

## Architecture

The backend follows a clean architecture with separation of concerns:

- **Routes Layer**: FastAPI endpoints, request/response handling
- **Services Layer**: Business logic, data operations
- **Core Layer**: Firebase and external service integrations

This design makes the code maintainable, testable, and easy to extend.
