"""
Django admin configuration for Discussion Engine models.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import (
    User,
    PlatformConfig,
    Discussion,
    DiscussionParticipant,
    Round,
    Response,
    Vote,
    RemovalVote,
    ModerationAction,
    Invite,
    JoinRequest,
    ResponseEdit,
    DraftResponse,
    NotificationPreference,
)


class DiscussionParticipantInline(admin.TabularInline):
    model = DiscussionParticipant
    extra = 0
    readonly_fields = ["joined_at", "observer_since"]


class RoundInline(admin.TabularInline):
    model = Round
    extra = 0
    readonly_fields = ["start_time", "end_time", "final_mrp_minutes"]


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    fieldsets = BaseUserAdmin.fieldsets + (
        (
            "Platform Info",
            {
                "fields": (
                    "phone_number",
                    "is_platform_admin",
                    "account_deletion_preference",
                )
            },
        ),
        (
            "Platform Invites",
            {
                "fields": (
                    "platform_invites_acquired",
                    "platform_invites_used",
                    "platform_invites_banked",
                )
            },
        ),
        (
            "Discussion Invites",
            {
                "fields": (
                    "discussion_invites_acquired",
                    "discussion_invites_used",
                    "discussion_invites_banked",
                )
            },
        ),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )

    readonly_fields = ["created_at", "updated_at"]
    list_display = [
        "username",
        "email",
        "phone_number",
        "is_platform_admin",
        "platform_invites_banked",
        "discussion_invites_banked",
        "created_at",
    ]
    list_filter = ["is_platform_admin", "is_staff", "is_active", "created_at"]
    search_fields = ["username", "email", "phone_number"]


@admin.register(PlatformConfig)
class PlatformConfigAdmin(admin.ModelAdmin):
    fieldsets = (
        (
            "Invite Configuration",
            {
                "fields": (
                    "new_user_platform_invites",
                    "new_user_discussion_invites",
                    "responses_to_unlock_invites",
                    "responses_per_platform_invite",
                    "responses_per_discussion_invite",
                    "invite_consumption_trigger",
                )
            },
        ),
        (
            "Discussion Limits",
            {
                "fields": (
                    "max_discussion_participants",
                    "n_responses_before_mrp",
                    "max_headline_length",
                    "max_topic_length",
                )
            },
        ),
        (
            "MRP Calculation",
            {
                "fields": (
                    "mrp_calculation_scope",
                    "mrp_calculation_x_rounds",
                )
            },
        ),
        (
            "Voting Configuration",
            {
                "fields": (
                    "voting_increment_percentage",
                    "vote_based_removal_threshold",
                )
            },
        ),
        (
            "Discussion Termination",
            {
                "fields": (
                    "max_discussion_duration_days",
                    "max_discussion_rounds",
                    "max_discussion_responses",
                    "round_1_phase_1_timeout_days",
                )
            },
        ),
        (
            "Response Settings",
            {
                "fields": (
                    "response_edit_percentage",
                    "response_edit_limit",
                )
            },
        ),
        (
            "Response Parameters",
            {
                "fields": (
                    "rtm_min",
                    "rtm_max",
                    "mrm_min_minutes",
                    "mrm_max_minutes",
                    "mrl_min_chars",
                    "mrl_max_chars",
                )
            },
        ),
        ("Other Settings", {"fields": ("allow_duplicate_discussions",)}),
    )

    def has_add_permission(self, request):
        # Singleton - only one instance allowed
        return not PlatformConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        # Cannot delete the singleton
        return False


@admin.register(Discussion)
class DiscussionAdmin(admin.ModelAdmin):
    list_display = [
        "topic_headline",
        "initiator",
        "status",
        "created_at",
        "archived_at",
    ]
    list_filter = ["status", "created_at"]
    search_fields = ["topic_headline", "topic_details", "initiator__username"]
    readonly_fields = ["created_at", "archived_at"]
    inlines = [DiscussionParticipantInline, RoundInline]

    fieldsets = (
        ("Topic", {"fields": ("topic_headline", "topic_details")}),
        (
            "Response Parameters",
            {
                "fields": (
                    "max_response_length_chars",
                    "response_time_multiplier",
                    "min_response_time_minutes",
                )
            },
        ),
        ("Management", {"fields": ("initiator", "delegated_approver", "status")}),
        ("Timestamps", {"fields": ("created_at", "archived_at")}),
    )


@admin.register(DiscussionParticipant)
class DiscussionParticipantAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "discussion",
        "role",
        "joined_at",
        "observer_reason",
        "removal_count",
    ]
    list_filter = ["role", "observer_reason", "joined_at"]
    search_fields = ["user__username", "discussion__topic_headline"]
    readonly_fields = ["joined_at", "observer_since"]

    fieldsets = (
        ("Participation", {"fields": ("discussion", "user", "role", "joined_at")}),
        (
            "Observer Status",
            {
                "fields": (
                    "observer_since",
                    "observer_reason",
                    "posted_in_round_when_removed",
                    "removal_count",
                )
            },
        ),
        ("Permissions", {"fields": ("can_invite_others",)}),
    )


@admin.register(Round)
class RoundAdmin(admin.ModelAdmin):
    list_display = [
        "discussion",
        "round_number",
        "status",
        "start_time",
        "end_time",
        "final_mrp_minutes",
    ]
    list_filter = ["status", "start_time"]
    search_fields = ["discussion__topic_headline"]
    readonly_fields = ["start_time", "end_time"]

    fieldsets = (
        ("Round Info", {"fields": ("discussion", "round_number", "status")}),
        ("Timing", {"fields": ("start_time", "end_time", "final_mrp_minutes")}),
    )


@admin.register(Response)
class ResponseAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "round",
        "character_count",
        "edit_count",
        "is_locked",
        "created_at",
    ]
    list_filter = ["is_locked", "created_at"]
    search_fields = ["user__username", "round__discussion__topic_headline", "content"]
    readonly_fields = ["created_at", "last_edited_at", "character_count"]

    fieldsets = (
        ("Response", {"fields": ("round", "user", "content", "character_count")}),
        (
            "Editing",
            {
                "fields": (
                    "edit_count",
                    "characters_changed_total",
                    "is_locked",
                    "last_edited_at",
                )
            },
        ),
        ("Timing", {"fields": ("time_since_previous_minutes", "created_at")}),
    )


@admin.register(Vote)
class VoteAdmin(admin.ModelAdmin):
    list_display = ["user", "round", "mrl_vote", "rtm_vote", "voted_at"]
    list_filter = ["mrl_vote", "rtm_vote", "voted_at"]
    search_fields = ["user__username", "round__discussion__topic_headline"]
    readonly_fields = ["voted_at"]


@admin.register(RemovalVote)
class RemovalVoteAdmin(admin.ModelAdmin):
    list_display = ["voter", "target", "round", "voted_at"]
    list_filter = ["voted_at"]
    search_fields = [
        "voter__username",
        "target__username",
        "round__discussion__topic_headline",
    ]
    readonly_fields = ["voted_at"]


@admin.register(ModerationAction)
class ModerationActionAdmin(admin.ModelAdmin):
    list_display = [
        "action_type",
        "initiator",
        "target",
        "discussion",
        "is_permanent",
        "action_at",
    ]
    list_filter = ["action_type", "is_permanent", "action_at"]
    search_fields = [
        "initiator__username",
        "target__username",
        "discussion__topic_headline",
    ]
    readonly_fields = ["action_at"]


@admin.register(Invite)
class InviteAdmin(admin.ModelAdmin):
    list_display = [
        "inviter",
        "invitee",
        "invite_type",
        "discussion",
        "status",
        "sent_at",
    ]
    list_filter = ["invite_type", "status", "sent_at"]
    search_fields = [
        "inviter__username",
        "invitee__username",
        "discussion__topic_headline",
    ]
    readonly_fields = ["sent_at", "accepted_at", "first_participation_at"]


@admin.register(JoinRequest)
class JoinRequestAdmin(admin.ModelAdmin):
    list_display = ["requester", "discussion", "status", "created_at", "resolved_at"]
    list_filter = ["status", "created_at"]
    search_fields = ["requester__username", "discussion__topic_headline"]
    readonly_fields = ["created_at", "resolved_at"]


@admin.register(ResponseEdit)
class ResponseEditAdmin(admin.ModelAdmin):
    list_display = ["response", "edit_number", "characters_changed", "edited_at"]
    list_filter = ["edit_number", "edited_at"]
    search_fields = ["response__user__username"]
    readonly_fields = ["edited_at"]


@admin.register(DraftResponse)
class DraftResponseAdmin(admin.ModelAdmin):
    list_display = ["user", "discussion", "round", "saved_reason", "created_at"]
    list_filter = ["saved_reason", "created_at"]
    search_fields = ["user__username", "discussion__topic_headline"]
    readonly_fields = ["created_at"]


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = ["user", "notification_type", "enabled"]
    list_filter = ["notification_type", "enabled"]
    search_fields = ["user__username"]
