# Quick Start Guide: Authentication & Invites

## Run All Tests

```bash
cd /home/wjgorr/discussion_engine
pytest tests/ -v
```

## Check Coverage

```bash
pytest tests/ --cov=core --cov-config=.coveragerc --cov-report=html
# Open htmlcov/index.html in browser
```

## View API Documentation

```bash
# Generate OpenAPI schema
python manage.py spectacular --file schema.yml

# Or run dev server and visit:
# http://localhost:8000/api/docs/  (Swagger UI)
# http://localhost:8000/api/redoc/  (ReDoc)
```

## Test API Endpoints Manually

### 1. Register New User

```bash
# Request verification code
curl -X POST http://localhost:8000/api/auth/register/request-verification/ \
  -H "Content-Type: application/json" \
  -d '{"phone_number": "+12025551234"}'

# Response: {"verification_id": "...", "expires_at": "..."}

# Verify code (check cache or test logs for code)
curl -X POST http://localhost:8000/api/auth/register/verify/ \
  -H "Content-Type: application/json" \
  -d '{
    "verification_id": "...",
    "code": "123456",
    "username": "testuser"
  }'

# Response: {"user_id": ..., "tokens": {"access": "...", "refresh": "..."}}
```

### 2. Send Platform Invite

```bash
# (After earning 3 responses)
curl -X POST http://localhost:8000/api/invites/platform/send/ \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json"

# Response: {"invite_code": "ABC12345", "invite_url": "..."}
```

### 3. Create Join Request

```bash
curl -X POST http://localhost:8000/api/discussions/1/join-request/ \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message": "I would like to join this discussion"}'
```

## Run Celery Worker (for background tasks)

```bash
# Terminal 1: Redis
redis-server

# Terminal 2: Celery Worker
celery -A discussion_platform worker --loglevel=info

# Terminal 3: Celery Beat (periodic tasks)
celery -A discussion_platform beat --loglevel=info

# Terminal 4: Django dev server
python manage.py runserver
```

## Run Migrations

```bash
python manage.py migrate
```

## Create Superuser

```bash
python manage.py createsuperuser
# Visit http://localhost:8000/admin/
```

## Key Configuration Files

- `discussion_platform/settings.py` - Main Django settings
- `discussion_platform/test_settings.py` - Test configuration
- `core/urls.py` - API URL routing
- `.coveragerc` - Coverage configuration
- `pytest.ini` - Pytest configuration

## Environment Variables

Create `.env` file:

```bash
# Django
SECRET_KEY=your-secret-key-here
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# Database (if using PostgreSQL in production)
DATABASE_URL=postgresql://user:pass@localhost/dbname

# Redis
REDIS_URL=redis://localhost:6379/0

# Twilio (for real SMS)
TWILIO_ACCOUNT_SID=your_account_sid
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_PHONE_NUMBER=+1234567890
TWILIO_TEST_MODE=False

# Celery
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
```

## Test Coverage by Module

```
core/admin.py                      98.02%
core/api/auth.py                   91.15%
core/api/invites.py                86.73%
core/api/onboarding_join.py        91.67%
core/api/serializers.py           100.00%
core/auth/registration.py          98.55%
core/models.py                     92.05%
core/security/abuse_detection.py   90.12%
core/services/invite_service.py    91.22%
core/services/join_request.py      86.21%
core/services/onboarding.py        93.55%
```

## Common Issues & Solutions

### Issue: Redis connection error
**Solution:** Ensure Redis is running: `redis-server`

### Issue: Celery tasks not executing
**Solution:** Check worker is running and `CELERY_TASK_ALWAYS_EAGER=True` in tests

### Issue: JWT authentication failing
**Solution:** Ensure token in header: `Authorization: Bearer <token>`

### Issue: Phone number validation failing
**Solution:** Use E.164 format: `+12025551234` (country code + number)

### Issue: Tests failing with cache errors
**Solution:** Tests use locmem cache automatically via test_settings.py

## Next Steps

Ready for Prompt 3 implementation:
- Discussion response submission
- Multi-round voting system
- Moderation and removal workflows
- Real-time updates
