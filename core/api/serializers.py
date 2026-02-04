"""
DRF serializers for API endpoints.

Handles validation and serialization of requests/responses.
"""

from rest_framework import serializers
from phonenumber_field.serializerfields import PhoneNumberField

from core.models import (
    User,
    Invite,
    Discussion,
    JoinRequest,
    DiscussionParticipant,
    Round,
    Response,
    ResponseEdit,
    DraftResponse,
)


class PhoneVerificationRequestSerializer(serializers.Serializer):
    """Request phone verification code."""

    phone_number = PhoneNumberField()


class PhoneVerificationResponseSerializer(serializers.Serializer):
    """Response with verification ID."""

    verification_id = serializers.UUIDField()
    expires_at = serializers.DateTimeField()
    message = serializers.CharField()


class VerifyCodeSerializer(serializers.Serializer):
    """Verify code and optional invite."""

    verification_id = serializers.UUIDField()
    code = serializers.CharField(min_length=6, max_length=6)
    invite_code = serializers.CharField(required=False, allow_blank=True)
    username = serializers.CharField(min_length=3, max_length=150)


class LoginSerializer(serializers.Serializer):
    """Login request."""

    phone_number = PhoneNumberField()


class TokenRefreshSerializer(serializers.Serializer):
    """Token refresh request."""

    refresh = serializers.CharField()


class UserSerializer(serializers.ModelSerializer):
    """User serialization."""

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "phone_number",
            "platform_invites_acquired",
            "platform_invites_used",
            "platform_invites_banked",
            "discussion_invites_acquired",
            "discussion_invites_used",
            "discussion_invites_banked",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class InviteMetricsSerializer(serializers.Serializer):
    """Invite metrics for a user."""

    acquired = serializers.IntegerField()
    used = serializers.IntegerField()
    banked = serializers.IntegerField()
    can_send = serializers.BooleanField()
    responses_needed_to_unlock = serializers.IntegerField(required=False)


class UserInviteStatsSerializer(serializers.Serializer):
    """Complete invite statistics for user."""

    platform_invites = InviteMetricsSerializer()
    discussion_invites = InviteMetricsSerializer()
    total_responses = serializers.IntegerField()


class InviteSerializer(serializers.ModelSerializer):
    """Invite serialization."""

    inviter_username = serializers.CharField(source="inviter.username", read_only=True)
    invitee_username = serializers.CharField(source="invitee.username", read_only=True)
    discussion_headline = serializers.CharField(
        source="discussion.topic_headline", read_only=True
    )

    class Meta:
        model = Invite
        fields = [
            "id",
            "invite_type",
            "status",
            "inviter",
            "inviter_username",
            "invitee",
            "invitee_username",
            "discussion",
            "discussion_headline",
            "sent_at",
            "accepted_at",
            "first_participation_at",
        ]
        read_only_fields = ["id", "sent_at", "accepted_at", "first_participation_at"]


class PlatformInviteCreateSerializer(serializers.Serializer):
    """Create platform invite - no input needed."""

    pass


class PlatformInviteResponseSerializer(serializers.Serializer):
    """Platform invite creation response."""

    invite_code = serializers.CharField()
    invite_url = serializers.CharField()
    invite_id = serializers.IntegerField()


class PlatformInviteAcceptSerializer(serializers.Serializer):
    """Accept platform invite."""

    invite_code = serializers.CharField(min_length=8, max_length=8)


class DiscussionInviteSendSerializer(serializers.Serializer):
    """Send discussion invite."""

    discussion_id = serializers.IntegerField()
    invitee_user_id = serializers.IntegerField()


class DiscussionInviteResponseSerializer(serializers.Serializer):
    """Discussion invite response."""

    invite_id = serializers.IntegerField()
    invitee = serializers.CharField()
    discussion = serializers.CharField()


class JoinRequestCreateSerializer(serializers.Serializer):
    """Create join request."""

    message = serializers.CharField(required=False, allow_blank=True, max_length=500)


class JoinRequestSerializer(serializers.ModelSerializer):
    """Join request serialization."""

    requester_username = serializers.CharField(
        source="requester.username", read_only=True
    )
    discussion_headline = serializers.CharField(
        source="discussion.topic_headline", read_only=True
    )
    approver_username = serializers.CharField(
        source="approver.username", read_only=True
    )

    # Include invite metrics for requester
    requester_platform_invites = serializers.SerializerMethodField()
    requester_discussion_invites = serializers.SerializerMethodField()

    class Meta:
        model = JoinRequest
        fields = [
            "id",
            "status",
            "requester",
            "requester_username",
            "approver",
            "approver_username",
            "discussion",
            "discussion_headline",
            "request_message",
            "response_message",
            "created_at",
            "resolved_at",
            "requester_platform_invites",
            "requester_discussion_invites",
        ]
        read_only_fields = ["id", "created_at", "resolved_at"]

    def get_requester_platform_invites(self, obj):
        """Get requester's platform invite metrics."""
        return {
            "acquired": obj.requester.platform_invites_acquired,
            "used": obj.requester.platform_invites_used,
            "banked": obj.requester.platform_invites_banked,
        }

    def get_requester_discussion_invites(self, obj):
        """Get requester's discussion invite metrics."""
        return {
            "acquired": obj.requester.discussion_invites_acquired,
            "used": obj.requester.discussion_invites_used,
            "banked": obj.requester.discussion_invites_banked,
        }


class JoinRequestActionSerializer(serializers.Serializer):
    """Approve/decline join request."""

    response_message = serializers.CharField(
        required=False, allow_blank=True, max_length=500
    )


class DiscussionSummarySerializer(serializers.ModelSerializer):
    """Discussion summary for onboarding."""

    participant_count = serializers.IntegerField(read_only=True)
    response_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Discussion
        fields = [
            "id",
            "topic_headline",
            "topic_details",
            "status",
            "created_at",
            "participant_count",
            "response_count",
        ]
        read_only_fields = fields


class TutorialStepSerializer(serializers.Serializer):
    """Tutorial step."""

    step = serializers.IntegerField()
    title = serializers.CharField()
    content = serializers.CharField()
    media = serializers.CharField(required=False, allow_null=True)


# Discussion and Round Serializers


class DiscussionPresetSerializer(serializers.Serializer):
    """Discussion preset configuration."""

    id = serializers.CharField()
    name = serializers.CharField()
    description = serializers.CharField()
    mrm_minutes = serializers.IntegerField()
    rtm = serializers.FloatField()
    mrl_chars = serializers.IntegerField()
    explanation = serializers.CharField()


class PreviewParametersSerializer(serializers.Serializer):
    """Preview discussion parameters."""

    mrm = serializers.IntegerField()
    rtm = serializers.FloatField()
    mrl = serializers.IntegerField()


class DiscussionCreateSerializer(serializers.Serializer):
    """Create a new discussion."""

    headline = serializers.CharField(max_length=100)
    details = serializers.CharField(max_length=500)
    preset = serializers.CharField(required=False, allow_null=True)
    mrm_minutes = serializers.IntegerField(required=False, allow_null=True)
    rtm = serializers.FloatField(required=False, allow_null=True)
    mrl_chars = serializers.IntegerField(required=False, allow_null=True)
    initial_invites = serializers.ListField(
        child=serializers.IntegerField(), required=False, allow_empty=True
    )


class DiscussionParticipantSerializer(serializers.ModelSerializer):
    """Discussion participant."""

    username = serializers.CharField(source="user.username", read_only=True)
    user_id = serializers.IntegerField(source="user.id", read_only=True)

    class Meta:
        model = DiscussionParticipant
        fields = [
            "user_id",
            "username",
            "role",
            "joined_at",
            "observer_since",
            "observer_reason",
            "can_invite_others",
        ]


class RoundInfoSerializer(serializers.ModelSerializer):
    """Round information."""

    phase = serializers.IntegerField(read_only=True)
    responses_count = serializers.IntegerField(read_only=True)
    responses_needed_for_phase_2 = serializers.IntegerField(read_only=True)
    mrp_minutes = serializers.FloatField(source="final_mrp_minutes", read_only=True)
    mrp_deadline = serializers.DateTimeField(read_only=True)

    class Meta:
        model = Round
        fields = [
            "round_number",
            "status",
            "phase",
            "start_time",
            "end_time",
            "responses_count",
            "responses_needed_for_phase_2",
            "mrp_minutes",
            "mrp_deadline",
        ]


class DiscussionDetailSerializer(serializers.ModelSerializer):
    """Detailed discussion information."""

    initiator_username = serializers.CharField(
        source="initiator.username", read_only=True
    )
    participants = DiscussionParticipantSerializer(many=True, read_only=True)
    current_round = RoundInfoSerializer(read_only=True)
    user_status = serializers.SerializerMethodField()
    parameters = serializers.SerializerMethodField()

    class Meta:
        model = Discussion
        fields = [
            "id",
            "topic_headline",
            "topic_details",
            "status",
            "initiator",
            "initiator_username",
            "parameters",
            "participants",
            "current_round",
            "user_status",
            "created_at",
        ]

    def get_parameters(self, obj):
        """Get discussion parameters."""
        return {
            "mrm": obj.min_response_time_minutes,
            "rtm": obj.response_time_multiplier,
            "mrl": obj.max_response_length_chars,
        }

    def get_user_status(self, obj):
        """Get user-specific status."""
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return None

        from core.services.discussion_service import DiscussionService

        return DiscussionService.get_discussion_status(obj, request.user)


class ResponseSerializer(serializers.ModelSerializer):
    """Response serialization."""

    author_username = serializers.CharField(source="user.username", read_only=True)
    author_id = serializers.IntegerField(source="user.id", read_only=True)
    response_number = serializers.SerializerMethodField()
    quotes = serializers.SerializerMethodField()

    class Meta:
        model = Response
        fields = [
            "id",
            "author_id",
            "author_username",
            "content",
            "character_count",
            "created_at",
            "last_edited_at",
            "edit_count",
            "time_since_previous_minutes",
            "response_number",
            "quotes",
        ]

    def get_response_number(self, obj):
        """Get response position in round."""
        from core.services.response_service import ResponseService

        return ResponseService.get_response_number(obj)

    def get_quotes(self, obj):
        """Extract quotes from content."""
        from core.services.quote_service import QuoteService

        return QuoteService.extract_quotes_from_content(obj.content)


class ResponseCreateSerializer(serializers.Serializer):
    """Create a response."""

    content = serializers.CharField()


class ResponseEditSerializer(serializers.Serializer):
    """Edit a response."""

    content = serializers.CharField()


class DraftResponseSerializer(serializers.Serializer):
    """Save a draft response."""

    content = serializers.CharField()
    reason = serializers.ChoiceField(
        choices=["mrp_expired", "user_saved", "round_ended"]
    )


class QuoteCreateSerializer(serializers.Serializer):
    """Create a quote from a response."""

    quoted_text = serializers.CharField()
    start_index = serializers.IntegerField(default=0)
    end_index = serializers.IntegerField(required=False, allow_null=True)


class ResponseListSerializer(serializers.Serializer):
    """List of responses with MRP info."""

    responses = ResponseSerializer(many=True)
    current_mrp_minutes = serializers.FloatField(allow_null=True)
    mrp_deadline = serializers.DateTimeField(allow_null=True)
