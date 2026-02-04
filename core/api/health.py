"""
Health check endpoint for load balancers and monitoring.
"""
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from django.db import connection
from django.core.cache import cache
from django.conf import settings


@api_view(['GET'])
@permission_classes([AllowAny])
def health_check(request):
    """
    Health check endpoint for load balancers and monitoring.
    
    Returns:
    - 200 OK if all systems healthy
    - 503 Service Unavailable if any critical system down
    """
    health = {
        'status': 'healthy',
        'checks': {}
    }
    
    # Database check
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
        health['checks']['database'] = 'ok'
    except Exception as e:
        health['status'] = 'unhealthy'
        health['checks']['database'] = f'error: {str(e)}'
    
    # Cache check
    try:
        cache.set('health_check', 'ok', 10)
        assert cache.get('health_check') == 'ok'
        health['checks']['cache'] = 'ok'
    except Exception as e:
        health['status'] = 'unhealthy'
        health['checks']['cache'] = f'error: {str(e)}'
    
    # Redis/Celery check (optional - don't fail if not configured)
    try:
        import redis
        if hasattr(settings, 'CELERY_BROKER_URL'):
            r = redis.from_url(settings.CELERY_BROKER_URL)
            r.ping()
            health['checks']['redis'] = 'ok'
        else:
            health['checks']['redis'] = 'not_configured'
    except Exception as e:
        # Redis is optional, so just note the error but don't mark unhealthy
        health['checks']['redis'] = f'warning: {str(e)}'
    
    status_code = 200 if health['status'] == 'healthy' else 503
    return Response(health, status=status_code)
