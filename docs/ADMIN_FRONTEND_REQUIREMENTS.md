# Admin Section - Frontend Requirements Documentation

## Overview
This document outlines the frontend requirements for the Admin Section of the AUB Email Verification System.

## Authentication

### Admin Authentication
All admin endpoints require Firebase authentication with admin privileges.

**Headers Required:**
```
Authorization: Bearer <firebase-id-token>
```

### Getting Admin Access
To set a user as admin, use the Firebase Admin SDK or the admin endpoint:
```bash
POST /admin/users/{uid}/admin-role
{
  "isAdmin": true
}
```

**Note:** The first admin must be set manually using Firebase Console or Admin SDK.

## API Endpoints

### Base URL
All admin endpoints are prefixed with `/admin`

For complete API documentation with request/response examples for all 16 admin endpoints, see the full version of this document or visit the FastAPI Swagger UI at `/docs`.

## Key Endpoint Categories

### User Management (7 endpoints)
1. **GET /admin/users** - List all users with pagination
2. **GET /admin/users/{uid}** - Get detailed user information
3. **PATCH /admin/users/{uid}/status** - Enable/disable user account
4. **DELETE /admin/users/{uid}** - Delete user account
5. **GET /admin/users/search/by-email** - Search users by email
6. **POST /admin/users/{uid}/admin-role** - Grant/revoke admin role
7. **GET /admin/users/stats/overview** - Get user statistics

### OTP Management (5 endpoints)
8. **GET /admin/otp/pending** - List pending OTP requests
9. **GET /admin/otp/{uid}** - Get OTP request details
10. **DELETE /admin/otp/expired** - Clear expired OTP requests
11. **GET /admin/otp/stats/overview** - Get OTP statistics
12. **DELETE /admin/otp/{uid}** - Revoke an OTP request

### Analytics (4 endpoints)
13. **GET /admin/analytics/registrations** - Get registration statistics over time
14. **GET /admin/analytics/verification-rate** - Get verification success rates
15. **GET /admin/analytics/daily** - Get today's metrics
16. **GET /admin/analytics/weekly** - Get last 7 days metrics

## Frontend Architecture Recommendations

### 1. State Management
- Use React Context or Redux for admin state
- Cache user lists and statistics
- Implement optimistic updates

### 2. Components to Build
- **AdminDashboard**: Overview with key metrics
- **UserManagement**: User list and management
- **UserDetails**: Detailed user view
- **OTPManagement**: OTP requests list
- **Analytics**: Charts and graphs
- **AdminAuth**: Login and auth check

### 3. UI Libraries
Recommended:
- **Material-UI** or **Ant Design** for components
- **Chart.js** or **Recharts** for analytics
- **React Table** for data tables
- **React Router** for navigation

### 4. Authentication Flow
```javascript
// Example authentication check
const checkAdminAuth = async (idToken) => {
  try {
    const response = await fetch('/admin/users/stats/overview', {
      headers: {
        'Authorization': `Bearer ${idToken}`
      }
    });
    return response.ok;
  } catch (error) {
    return false;
  }
};
```

### 5. Error Handling
Handle these HTTP status codes:
- **401**: Token invalid/expired - redirect to login
- **403**: Not an admin - show access denied
- **404**: Resource not found - show error message
- **500**: Server error - show error and retry option

### 6. Data Refresh
- Auto-refresh statistics every 30-60 seconds
- Manual refresh button for user lists
- Real-time updates using Firebase listeners (optional)

## Security Considerations

### Frontend Security
1. **Never store admin credentials** in localStorage
2. **Validate admin token** on every page load
3. **Use HTTPS** for all requests
4. **Implement session timeout**
5. **Log admin actions** (implement on backend)

### Token Management
```javascript
// Get token from Firebase Auth
const getIdToken = async () => {
  const user = firebase.auth().currentUser;
  if (user) {
    return await user.getIdToken();
  }
  return null;
};

// Use token in requests
const makeAdminRequest = async (endpoint) => {
  const token = await getIdToken();
  return fetch(endpoint, {
    headers: {
      'Authorization': `Bearer ${token}`
    }
  });
};
```

## Sample Frontend Code

### Admin API Service
```javascript
// adminService.js
import { getIdToken } from './auth';

const API_BASE = 'http://localhost:8000/admin';

class AdminService {
  async request(endpoint, options = {}) {
    const token = await getIdToken();
    const response = await fetch(`${API_BASE}${endpoint}`, {
      ...options,
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
        ...options.headers,
      },
    });
    
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Request failed');
    }
    
    return response.json();
  }

  // User Management
  listUsers(pageSize = 100, pageToken = null) {
    const params = new URLSearchParams({ pageSize });
    if (pageToken) params.append('pageToken', pageToken);
    return this.request(`/users?${params}`);
  }

  getUserDetails(uid) {
    return this.request(`/users/${uid}`);
  }

  updateUserStatus(uid, disabled) {
    return this.request(`/users/${uid}/status`, {
      method: 'PATCH',
      body: JSON.stringify({ disabled }),
    });
  }

  deleteUser(uid) {
    return this.request(`/users/${uid}`, {
      method: 'DELETE',
    });
  }

  searchUsers(email) {
    return this.request(`/users/search/by-email?email=${email}`);
  }

  setAdminRole(uid, isAdmin) {
    return this.request(`/users/${uid}/admin-role`, {
      method: 'POST',
      body: JSON.stringify({ isAdmin }),
    });
  }

  getUserStats() {
    return this.request('/users/stats/overview');
  }

  // OTP Management
  listPendingOTPs(limit = 100) {
    return this.request(`/otp/pending?limit=${limit}`);
  }

  getOTPDetails(uid) {
    return this.request(`/otp/${uid}`);
  }

  clearExpiredOTPs() {
    return this.request('/otp/expired', {
      method: 'DELETE',
    });
  }

  getOTPStats() {
    return this.request('/otp/stats/overview');
  }

  revokeOTP(uid) {
    return this.request(`/otp/${uid}`, {
      method: 'DELETE',
    });
  }

  // Analytics
  getRegistrationStats(days = 30) {
    return this.request(`/analytics/registrations?days=${days}`);
  }

  getVerificationRate() {
    return this.request('/analytics/verification-rate');
  }

  getDailyMetrics() {
    return this.request('/analytics/daily');
  }

  getWeeklyMetrics() {
    return this.request('/analytics/weekly');
  }
}

export default new AdminService();
```

### React Component Example
```jsx
// AdminDashboard.jsx
import React, { useState, useEffect } from 'react';
import adminService from './adminService';

function AdminDashboard() {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadStats();
    const interval = setInterval(loadStats, 60000); // Refresh every minute
    return () => clearInterval(interval);
  }, []);

  const loadStats = async () => {
    try {
      const [userStats, otpStats, dailyMetrics] = await Promise.all([
        adminService.getUserStats(),
        adminService.getOTPStats(),
        adminService.getDailyMetrics(),
      ]);
      setStats({ userStats, otpStats, dailyMetrics });
    } catch (error) {
      console.error('Failed to load stats:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) return <div>Loading...</div>;

  return (
    <div className="admin-dashboard">
      <h1>Admin Dashboard</h1>
      
      <div className="stats-grid">
        <div className="stat-card">
          <h3>Total Users</h3>
          <p className="stat-value">{stats.userStats.totalUsers}</p>
        </div>
        
        <div className="stat-card">
          <h3>Verified Users</h3>
          <p className="stat-value">{stats.userStats.verifiedUsers}</p>
          <p className="stat-label">
            {stats.userStats.verificationRate}% verification rate
          </p>
        </div>
        
        <div className="stat-card">
          <h3>Today's New Users</h3>
          <p className="stat-value">{stats.dailyMetrics.newUsers}</p>
        </div>
        
        <div className="stat-card">
          <h3>Pending OTPs</h3>
          <p className="stat-value">{stats.otpStats.pendingRequests}</p>
        </div>
      </div>
    </div>
  );
}

export default AdminDashboard;
```

## Support

For questions or issues, contact the backend team or refer to:
- Backend API documentation: `/docs` (FastAPI Swagger UI)
- Backend repository: github.com/cmps-271-team-2/Backend
