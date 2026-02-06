"""
Response API endpoints.

Handles response submission, editing, drafts, and quotes.
"""

import logging
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response as DRFResponse

from core.models import Round, Response, PlatformConfig
from core.api.serializers import (
    ResponseSerializer,
    ResponseCreateSerializer,
    ResponseEditSerializer,
    DraftResponseSerializer,
    QuoteCreateSerializer,
    ResponseListSerializer,
)
from core.services.response_service import ResponseService
from core.services.quote_service import QuoteService
from core.services.round_service import RoundService

logger = logging.getLogger(__name__)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_responses(request, discussion_id, round_number):
    """
    GET /api/discussions/{discussion_id}/rounds/{round_number}/responses/

    Get all responses for a round.
    """
    try:
        round_obj = Round.objects.get(
            discussion_id=discussion_id, round_number=round_number
        )
    except Round.DoesNotExist:
        return DRFResponse(
            {"error": "Round not found"}, status=status.HTTP_404_NOT_FOUND
        )

    # Check if user is a participant
    if not round_obj.discussion.participants.filter(user=request.user).exists():
        return DRFResponse(
            {"error": "Not a participant in this discussion"},
            status=status.HTTP_403_FORBIDDEN,
        )

    # Get responses
    responses = round_obj.responses.all().order_by("created_at")

    serializer = ResponseSerializer(responses, many=True)

    # Get MRP info
    config = PlatformConfig.load()
    mrp_deadline = RoundService.get_mrp_deadline(round_obj)

    return DRFResponse(
        {
            "responses": serializer.data,
            "current_mrp_minutes": round_obj.final_mrp_minutes,
            "mrp_deadline": mrp_deadline,
        }
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_response(request, discussion_id, round_number):
    """
    POST /api/discussions/{discussion_id}/rounds/{round_number}/responses/

    Submit a response to a round.

    Request:
        {
            "content": "My response text..."
        }

    Response:
        {
            "response": {...},
            "mrp_updated": true,
            "new_mrp_minutes": 55.3,
            "new_mrp_deadline": "...",
            "invites_earned": {"platform": 0, "discussion": 1}
        }
    """
    serializer = ResponseCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    try:
        round_obj = Round.objects.get(
            discussion_id=discussion_id, round_number=round_number
        )
    except Round.DoesNotExist:
        return DRFResponse(
            {"error": "Round not found"}, status=status.HTTP_404_NOT_FOUND
        )

    config = PlatformConfig.load()

    # Track MRP before submission
    old_mrp = round_obj.final_mrp_minutes

    # Submit response
    try:
        response = ResponseService.submit_response(
            user=request.user,
            round=round_obj,
            content=serializer.validated_data["content"],
        )
    except Exception as e:
        logger.exception(f"Error submitting response: {e}")
        return DRFResponse(
            {"error": "Failed to submit response. Please try again."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Refresh round to get updated MRP
    round_obj.refresh_from_db()

    # Check if MRP was updated
    mrp_updated = round_obj.final_mrp_minutes != old_mrp
    mrp_deadline = RoundService.get_mrp_deadline(round_obj)

    # Serialize response
    response_serializer = ResponseSerializer(response)

    # Get invite earnings (this is a simplified version - actual tracking would be more complex)
    # For now, return placeholder
    invites_earned = {"platform": 0, "discussion": 0}

    return DRFResponse(
        {
            "response": response_serializer.data,
            "mrp_updated": mrp_updated,
            "new_mrp_minutes": round_obj.final_mrp_minutes,
            "new_mrp_deadline": mrp_deadline,
            "invites_earned": invites_earned,
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def respond_to_discussion(request, discussion_id):
    """
    POST /api/discussions/{discussion_id}/respond/

    Submit a response to the current active round of a discussion.
    Used by the active_view.html JS submitResponse() function.
    """
    import json
    from core.models import Discussion, DiscussionParticipant

    try:
        discussion = Discussion.objects.get(id=discussion_id)
    except Discussion.DoesNotExist:
        return DRFResponse(
            {"error": "Discussion not found"}, status=status.HTTP_404_NOT_FOUND
        )

    # Check participant
    if not DiscussionParticipant.objects.filter(
        discussion=discussion, user=request.user, role__in=["initiator", "active"]
    ).exists():
        return DRFResponse(
            {"error": "Not an active participant"}, status=status.HTTP_403_FORBIDDEN
        )

    # Get current round
    round_obj = Round.objects.filter(
        discussion=discussion, status="in_progress"
    ).order_by("-round_number").first()

    if not round_obj:
        return DRFResponse(
            {"error": "No active round"}, status=status.HTTP_400_BAD_REQUEST
        )

    # Parse JSON body
    try:
        body = request.data
        content = body.get("response_text", "").strip()
    except Exception:
        content = ""

    if not content:
        return DRFResponse(
            {"error": "Response text is required"}, status=status.HTTP_400_BAD_REQUEST
        )

    try:
        response = ResponseService.submit_response(
            user=request.user,
            round=round_obj,
            content=content,
        )
    except Exception as e:
        return DRFResponse(
            {"error": str(e)}, status=status.HTTP_400_BAD_REQUEST
        )

    return DRFResponse({"status": "ok"}, status=status.HTTP_201_CREATED)


@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
def edit_response(request, response_id):
    """
    PATCH /api/responses/{response_id}/

    Edit an existing response.

    Request:
        {
            "content": "Updated response text..."
        }

    Response:
        {
            "response": {...},
            "edit_number": 1,
            "characters_changed": 87,
            "budget_remaining": 313
        }
    """
    serializer = ResponseEditSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    try:
        response = Response.objects.get(id=response_id)
    except Response.DoesNotExist:
        return DRFResponse(
            {"error": "Response not found"}, status=status.HTTP_404_NOT_FOUND
        )

    # Check ownership
    if response.user != request.user:
        return DRFResponse(
            {"error": "Can only edit your own responses"},
            status=status.HTTP_403_FORBIDDEN,
        )

    config = PlatformConfig.load()

    # Edit response
    try:
        updated_response = ResponseService.edit_response(
            user=request.user,
            response=response,
            new_content=serializer.validated_data["content"],
            config=config,
        )
    except Exception as e:
        logger.exception(f"Error editing response: {e}")
        return DRFResponse(
            {"error": "Failed to edit response. Please try again."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Get latest edit
    latest_edit = updated_response.edits.latest("edited_at")

    # Calculate remaining budget
    budget_remaining = ResponseService.calculate_edit_budget(updated_response, config)

    # Serialize response
    response_serializer = ResponseSerializer(updated_response)

    return DRFResponse(
        {
            "response": response_serializer.data,
            "edit_number": latest_edit.edit_number,
            "characters_changed": latest_edit.characters_changed,
            "budget_remaining": budget_remaining,
        }
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def save_draft(request, response_id):
    """
    POST /api/responses/{response_id}/save-draft/

    Save a draft response (when MRP expires or round ends).

    Request:
        {
            "content": "...",
            "reason": "mrp_expired"
        }

    Response:
        {
            "draft_id": "uuid",
            "message": "Draft saved"
        }
    """
    # Note: This endpoint is a bit awkward - it takes a response_id but creates a draft
    # In practice, this might be called differently, but following the spec

    serializer = DraftResponseSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    try:
        response = Response.objects.get(id=response_id)
    except Response.DoesNotExist:
        return DRFResponse(
            {"error": "Response not found"}, status=status.HTTP_404_NOT_FOUND
        )

    # Save draft
    draft = ResponseService.save_draft(
        user=request.user,
        round=response.round,
        content=serializer.validated_data["content"],
        reason=serializer.validated_data.get("reason"),
    )

    return DRFResponse(
        {"draft_id": draft.id, "message": "Draft saved"}, status=status.HTTP_201_CREATED
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def save_draft_for_round(request, discussion_id, round_number):
    """
    POST /api/discussions/{discussion_id}/rounds/{round_number}/save-draft/

    Save a draft response for a round (better endpoint design).

    Request:
        {
            "content": "...",
            "reason": "mrp_expired"
        }
    """
    serializer = DraftResponseSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    try:
        round_obj = Round.objects.get(
            discussion_id=discussion_id, round_number=round_number
        )
    except Round.DoesNotExist:
        return DRFResponse(
            {"error": "Round not found"}, status=status.HTTP_404_NOT_FOUND
        )

    # Save draft
    draft = ResponseService.save_draft(
        user=request.user,
        round=round_obj,
        content=serializer.validated_data["content"],
        reason=serializer.validated_data.get("reason"),
    )

    return DRFResponse(
        {"draft_id": draft.id, "message": "Draft saved"}, status=status.HTTP_201_CREATED
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_quote(request, response_id):
    """
    POST /api/responses/{response_id}/quote/

    Create a quote from a response.

    Request:
        {
            "quoted_text": "selected text",
            "start_index": 0,
            "end_index": 50
        }

    Response:
        {
            "quote_markdown": "> [Username] (Response #3):\\n> \"selected text\""
        }
    """
    serializer = QuoteCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    try:
        response = Response.objects.get(id=response_id)
    except Response.DoesNotExist:
        return DRFResponse(
            {"error": "Response not found"}, status=status.HTTP_404_NOT_FOUND
        )

    # Create quote
    try:
        quote_markdown = QuoteService.create_quote_markdown(
            source_response=response,
            quoted_text=serializer.validated_data["quoted_text"],
        )
    except Exception as e:
        logger.exception(f"Error creating quote: {e}")
        return DRFResponse(
            {"error": "Failed to create quote. Please try again."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    return DRFResponse({"quote_markdown": quote_markdown})
