"""
Deprecated mutual removal API endpoints.

All endpoints in this file return 410 Gone as the mutual removal (kamikaze)
feature has been removed from the UI. The endpoints are maintained for
backwards compatibility with legacy clients.

Deprecated: 2026-02
"""

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def initiate_mutual_removal(request, discussion_id):
    """
    DEPRECATED: Mutual removal feature has been removed from UI.

    This endpoint is maintained for backwards compatibility but returns 410 Gone.
    All kamikaze mechanics remain functional for historical records.

    Deprecated: 2026-02
    """
    return Response({
        'error': 'Feature deprecated',
        'message': 'Mutual removal (kamikaze) feature has been deprecated and removed from the platform. '
                   'This functionality is no longer available for new attacks. '
                   'Existing records are maintained for historical purposes.',
        'deprecated_date': '2026-02',
        'alternative': 'Use the removal voting system during inter-round voting phases'
    }, status=status.HTTP_410_GONE)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def respond_mutual_removal(request, discussion_id, attack_id):
    """
    DEPRECATED: Mutual removal feature has been removed from UI.

    This endpoint is maintained for backwards compatibility but returns 410 Gone.

    Deprecated: 2026-02
    """
    return Response({
        'error': 'Feature deprecated',
        'message': 'Mutual removal (kamikaze) feature has been removed from the platform.',
        'deprecated_date': '2026-02'
    }, status=status.HTTP_410_GONE)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def check_mutual_removal_status(request, discussion_id):
    """
    DEPRECATED: Mutual removal feature has been removed from UI.

    This endpoint is maintained for backwards compatibility but returns 410 Gone.

    Deprecated: 2026-02
    """
    return Response({
        'error': 'Feature deprecated',
        'message': 'Mutual removal (kamikaze) feature has been removed from the platform.',
        'deprecated_date': '2026-02',
        'status': 'no_active_attacks'  # For any legacy clients
    }, status=status.HTTP_410_GONE)
