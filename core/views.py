"""
Django views for rendering frontend templates.

These views handle all template-based pages for the Discussion Engine platform,
including authentication, dashboards, discussions, moderation, and admin interfaces.
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import login, logout, authenticate
from django.contrib import messages
from django.http import JsonResponse, HttpResponseForbidden
from django.views.decorators.http import require_http_methods
from django.db.models import Q, Count
from django.utils import timezone
from datetime import timedelta

from core.models import (
    User,
    Discussion,
    DiscussionParticipant,
    Response,
    NotificationLog,
    PlatformConfig,
    Invite,
)
from core.services.notification_service import NotificationService
from core.services.admin_service import AdminService
from core.services.discussion_service import DiscussionService
from django.core.exceptions import ValidationError

# =============================================================================
# Authentication Views
# =============================================================================


def register_view(request):
    """User registration form."""
    if request.method == "POST":
        # This would integrate with the API endpoint
        # For now, render the phone verification page
        return render(
            request,
            "auth/verify_phone.html",
            {"phone_number": request.POST.get("phone_number")},
        )
    return render(request, "auth/register.html")


def verify_phone_view(request):
    """Phone verification form."""
    if request.method == "POST":
        # Integrate with API verification endpoint
        # On success, login and redirect to dashboard
        return redirect("dashboard")
    return render(request, "auth/verify_phone.html")


@require_http_methods(["POST"])
def resend_verification_view(request):
    """Resend verification code (HTMX endpoint)."""
    # TODO: Integrate with PhoneVerificationService to resend code
    return JsonResponse({"status": "success", "message": "Verification code resent"})


def login_view(request):
    """Login form."""
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            messages.success(request, f"Welcome back, {user.username}!")
            return redirect("dashboard")
        else:
            messages.error(request, "Invalid credentials. Please try again.")
    return render(request, "auth/login.html")


def logout_view(request):
    """Logout user."""
    logout(request)
    messages.info(request, "You have been logged out.")
    return redirect("login")


def password_reset_view(request):
    """Password reset form."""
    return render(request, "auth/password_reset.html")


# =============================================================================
# Dashboard Views
# =============================================================================


@login_required
def dashboard_view(request):
    """User dashboard with overview of activities."""
    user = request.user

    # Get active discussions where user is a participant
    active_participations = DiscussionParticipant.objects.filter(
        user=user, role__in=["active", "initiator"]
    ).select_related("discussion")

    active_discussions = [
        p.discussion for p in active_participations if p.discussion.status == "active"
    ]

    # Get pending invites
    pending_invites = Invite.objects.filter(
        invitee=user, status="pending"
    ).select_related("inviter", "discussion")[:5]

    # Get recent notifications
    recent_notifications = NotificationLog.objects.filter(user=user).order_by(
        "-created_at"
    )[:5]

    # Calculate stats
    stats = {
        "active_discussions": len(active_discussions),
        "responses_posted": Response.objects.filter(user=user).count(),
        "pending_invites": pending_invites.count(),
        "unread_notifications": NotificationLog.objects.filter(
            user=user, read_at__isnull=True
        ).count(),
    }

    context = {
        "stats": stats,
        "active_discussions": active_discussions,
        "pending_invites": pending_invites,
        "recent_notifications": recent_notifications,
    }

    return render(request, "dashboard/home.html", context)


@login_required
def invites_view(request):
    """Manage invites page."""
    user = request.user

    # Received invites
    received_invites = (
        Invite.objects.filter(invitee=user)
        .select_related("inviter", "discussion")
        .order_by("-sent_at")
    )

    # Sent invites
    sent_invites = (
        Invite.objects.filter(inviter=user)
        .select_related("invitee", "discussion")
        .order_by("-sent_at")
    )

    context = {
        "received_invites": received_invites,
        "sent_invites": sent_invites,
        "platform_invites_banked": user.platform_invites_banked,
        "discussion_invites_banked": user.discussion_invites_banked,
    }

    return render(request, "dashboard/invites.html", context)


@login_required
def notifications_view(request):
    """Notification center."""
    notifications = NotificationLog.objects.filter(user=request.user).order_by(
        "-created_at"
    )

    # Mark all as read if requested
    if request.GET.get("mark_all_read"):
        notifications.filter(read_at__isnull=True).update(read_at=timezone.now())
        messages.success(request, "All notifications marked as read.")
        return redirect("notifications")

    context = {
        "notifications": notifications,
        "unread_count": notifications.filter(read_at__isnull=True).count(),
    }

    return render(request, "dashboard/notifications.html", context)


@login_required
def user_settings_view(request):
    """User settings page."""
    if request.method == "POST":
        # Update notification preferences, etc.
        messages.success(request, "Settings updated successfully.")
        return redirect("user-settings")

    return render(request, "dashboard/settings.html")


# =============================================================================
# Discussion Views
# =============================================================================


@login_required
def discussion_create_view(request):
    """Discussion creation wizard."""
    if request.method == "POST":
        try:
            # Get form data
            headline = request.POST.get("headline", "").strip()
            details = request.POST.get("details", "").strip()

            # Get parameters (either from preset or custom)
            preset = request.POST.get("preset")

            if preset:
                from core.services.discussion_presets import DiscussionPreset
                preset_data = DiscussionPreset.get_preset(preset)
                mrm = preset_data["mrm_minutes"]
                rtm = preset_data["rtm"]
                mrl = preset_data["mrl_chars"]
            else:
                # Custom parameters
                mrm = int(request.POST.get("mrm_minutes", 30))
                rtm = float(request.POST.get("rtm", 1.0))
                mrl = int(request.POST.get("mrl_chars", 2000))

            # Create discussion using service
            discussion = DiscussionService.create_discussion(
                initiator=request.user,
                headline=headline,
                details=details,
                mrm=mrm,
                rtm=rtm,
                mrl=mrl,
                initial_invites=[],
            )

            messages.success(request, "Discussion created successfully!")
            return redirect("discussion-detail", discussion_id=discussion.id)

        except ValidationError as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f"Error creating discussion: {str(e)}")

    return render(request, "discussions/create.html")


@login_required
def discussion_list_view(request):
    """Browse discussions."""
    discussions = (
        Discussion.objects.filter(status__in=["active", "voting"])
        .annotate(participant_count=Count("participants"))
        .order_by("-created_at")
    )

    # Filter by search query
    query = request.GET.get("q")
    if query:
        discussions = discussions.filter(
            Q(topic_headline__icontains=query) | Q(topic_details__icontains=query)
        )

    context = {"discussions": discussions, "query": query}

    return render(request, "discussions/list.html", context)


@login_required
def discussion_detail_view(request, discussion_id):
    """Discussion detail view with responses."""
    discussion = get_object_or_404(Discussion, id=discussion_id)

    # Check if user is a participant
    try:
        participant = DiscussionParticipant.objects.get(
            discussion=discussion, user=request.user
        )
    except DiscussionParticipant.DoesNotExist:
        participant = None

    # Get all responses in order
    responses = (
        Response.objects.filter(round__discussion=discussion)
        .select_related("user", "round")
        .order_by("round__round_number", "created_at")
    )

    # Get all participants
    participants = DiscussionParticipant.objects.filter(
        discussion=discussion
    ).select_related("user")

    context = {
        "discussion": discussion,
        "participant": participant,
        "responses": responses,
        "participants": participants,
        "can_respond": participant and participant.role in ["initiator", "active"],
        "is_observer": participant and participant.role in ["temporary_observer", "permanent_observer"],
    }

    return render(request, "discussions/detail.html", context)


@login_required
def discussion_participate_view(request, discussion_id):
    """Response submission form."""
    discussion = get_object_or_404(Discussion, id=discussion_id)

    # Check if user can respond
    try:
        participant = DiscussionParticipant.objects.get(
            discussion=discussion, user=request.user
        )
    except DiscussionParticipant.DoesNotExist:
        messages.error(request, "You are not a participant in this discussion.")
        return redirect("discussion-detail", discussion_id=discussion_id)

    if participant.role not in ["initiator", "active"]:
        messages.error(request, "You cannot respond at this time.")
        return redirect("discussion-detail", discussion_id=discussion_id)

    if request.method == "POST":
        # This would integrate with the API endpoint
        messages.success(request, "Response submitted successfully!")
        return redirect("discussion-detail", discussion_id=discussion_id)

    # Get previous responses for quoting
    previous_responses = (
        Response.objects.filter(round__discussion=discussion)
        .select_related("user", "round")
        .order_by("round__round_number", "created_at")
    )

    context = {
        "discussion": discussion,
        "participant": participant,
        "previous_responses": previous_responses,
        "max_chars": discussion.max_response_length_chars,
    }

    return render(request, "discussions/participate.html", context)


@login_required
def discussion_voting_view(request, discussion_id):
    """Voting interface for inter-round voting."""
    discussion = get_object_or_404(Discussion, id=discussion_id)

    if discussion.status != "voting":
        messages.error(request, "This discussion is not in voting phase.")
        return redirect("discussion-detail", discussion_id=discussion_id)

    # Check if user is eligible to vote
    try:
        participant = DiscussionParticipant.objects.get(
            discussion=discussion, user=request.user, role__in=["active", "initiator"]
        )
    except DiscussionParticipant.DoesNotExist:
        messages.error(request, "You are not eligible to vote.")
        return redirect("discussion-detail", discussion_id=discussion_id)

    if request.method == "POST":
        # This would integrate with the API endpoint
        messages.success(request, "Votes submitted successfully!")
        return redirect("discussion-detail", discussion_id=discussion_id)

    # Get other participants for moderation voting
    other_participants = (
        DiscussionParticipant.objects.filter(discussion=discussion, role__in=["active", "initiator"])
        .exclude(user=request.user)
        .select_related("user")
    )

    context = {
        "discussion": discussion,
        "participant": participant,
        "other_participants": other_participants,
    }

    return render(request, "discussions/voting.html", context)


# =============================================================================
# Moderation Views
# =============================================================================


@login_required
def moderation_history_view(request, discussion_id):
    """Moderation history for a discussion."""
    discussion = get_object_or_404(Discussion, id=discussion_id)

    # Get moderation actions
    # This would query a ModerationAction model if it existed

    context = {"discussion": discussion}

    return render(request, "moderation/history.html", context)


# =============================================================================
# Admin Views
# =============================================================================


@staff_member_required
def admin_dashboard_view(request):
    """Admin dashboard with platform overview."""
    service = AdminService()

    # Get platform statistics
    stats = {
        "total_users": User.objects.count(),
        "active_users": User.objects.filter(
            last_login__gte=timezone.now() - timedelta(days=30)
        ).count(),
        "total_discussions": Discussion.objects.count(),
        "active_discussions": Discussion.objects.filter(status="active").count(),
        "total_responses": Response.objects.count(),
    }

    # Get recent moderation actions
    # This would come from the admin service

    context = {"stats": stats}

    return render(request, "admin/dashboard.html", context)


@staff_member_required
def admin_config_view(request):
    """Platform configuration editor."""
    if request.method == "POST":
        # Update configuration
        messages.success(request, "Configuration updated successfully.")
        return redirect("admin-config")

    config = PlatformConfig.load()

    context = {"config": config}

    return render(request, "admin/config.html", context)


@staff_member_required
def admin_analytics_view(request):
    """Analytics dashboard."""
    # Calculate analytics
    analytics = {
        "user_growth": [],  # Time series data
        "discussion_metrics": {},
        "engagement_metrics": {},
    }

    context = {"analytics": analytics}

    return render(request, "admin/analytics.html", context)


@staff_member_required
def admin_moderation_queue_view(request):
    """Moderation queue for flagged users."""
    # Get flagged users from abuse detection
    flagged_users = User.objects.filter(behavioral_flags__isnull=False).exclude(
        behavioral_flags={}
    )

    context = {"flagged_users": flagged_users}

    return render(request, "admin/moderation_queue.html", context)


# =============================================================================
# HTMX/AJAX Endpoints
# =============================================================================


@login_required
def user_search(request):
    """Search users for inviting (HTMX endpoint)."""
    query = request.GET.get("q", "")

    if len(query) < 2:
        return JsonResponse({"users": []})

    users = User.objects.filter(
        Q(username__icontains=query) | Q(email__icontains=query)
    ).exclude(id=request.user.id)[:10]

    results = [{"id": u.id, "username": u.username, "email": u.email} for u in users]

    return JsonResponse({"users": results})


@login_required
@require_http_methods(["POST"])
def mark_notification_read(request, notification_id):
    """Mark a notification as read (HTMX endpoint)."""
    notification = get_object_or_404(
        NotificationLog, id=notification_id, user=request.user
    )
    notification.read_at = timezone.now()
    notification.save()

    return JsonResponse({"status": "success"})


@login_required
def mark_all_read(request):
    """Mark all notifications as read (HTMX endpoint)."""
    if request.method == "POST":
        NotificationLog.objects.filter(user=request.user, read_at__isnull=True).update(
            read_at=timezone.now()
        )
        messages.success(request, "All notifications marked as read.")
        return redirect("notifications")
    return JsonResponse({"status": "error"}, status=400)


@login_required
def notification_preferences_view(request):
    """View/update notification preferences."""
    # This would render a preferences page or return JSON for HTMX
    return JsonResponse({"preferences": {}})
