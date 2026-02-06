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
    Round,
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


def register_page(request):
    """User registration page (alias for E2E tests)."""
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
    """User dashboard with invite economy and discussion state cards."""
    return dashboard_new_view(request)


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

    # Get user's own platform invite code (most recent active one)
    user_invite = (
        Invite.objects.filter(
            inviter=user, invite_type="platform", status="sent"
        )
        .order_by("-sent_at")
        .first()
    )

    # Calculate invite stats
    invite_stats = {
        "available": user.platform_invites_banked,
        "acquired": user.platform_invites_acquired,
        "sent": sent_invites.count(),
        "acceptance_rate": 0,  # TODO: Calculate actual acceptance rate
    }

    context = {
        "received_invites": received_invites,
        "sent_invites": sent_invites,
        "platform_invites_banked": user.platform_invites_banked,
        "discussion_invites_banked": user.discussion_invites_banked,
        "user_invite_code": user_invite.code if user_invite else None,
        "user_invite_expiration": user_invite.expires_at if user_invite else None,
        "invite_stats": invite_stats,
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
    """Redirect to discussion creation wizard."""
    return redirect("discussion-create-wizard")


@login_required
def discussion_list_view(request):
    """Browse discussions."""
    user = request.user
    discussions = (
        Discussion.objects.filter(status__in=["active", "voting", "archived"])
        .annotate(participant_count=Count("participants"))
        .order_by("-created_at")
    )

    # Filter by search query
    search_query = request.GET.get("search", "").strip()
    if search_query:
        discussions = discussions.filter(
            Q(topic_headline__icontains=search_query)
            | Q(topic_details__icontains=search_query)
        )

    # Filter by status/type
    filter_type = request.GET.get("filter", "all")
    if filter_type == "active":
        discussions = discussions.filter(status="active")
    elif filter_type == "archived":
        discussions = discussions.filter(status="archived")
    elif filter_type == "mine":
        # Get discussions where user is a participant
        user_discussion_ids = DiscussionParticipant.objects.filter(
            user=user
        ).values_list("discussion_id", flat=True)
        discussions = discussions.filter(id__in=user_discussion_ids)

    context = {
        "discussions": discussions,
        "search_query": search_query,
        "filter": filter_type,
    }

    # If HTMX request, only return the discussion list partial
    if request.headers.get("HX-Request"):
        return render(request, "discussions/partials/discussion_list.html", context)

    return render(request, "discussions/list.html", context)


@login_required
def discussion_detail_view(request, discussion_id):
    """Route to appropriate view based on participant role and discussion state."""
    discussion = get_object_or_404(Discussion, id=discussion_id)

    participant = DiscussionParticipant.objects.filter(
        discussion=discussion, user=request.user
    ).first()

    # Active participants: check for voting phase first, then active view
    if participant and participant.role in ["initiator", "active"]:
        current_round = Round.objects.filter(
            discussion=discussion
        ).order_by("-round_number").first()
        if current_round and current_round.status == "voting":
            return redirect("discussion-voting", discussion_id=discussion_id)
        return redirect("discussion-active", discussion_id=discussion_id)

    # Everyone else (observers, non-participants) gets observer view
    return redirect("discussion-observer", discussion_id=discussion_id)


@login_required
def discussion_participate_view(request, discussion_id):
    """Legacy response form - redirect to active view."""
    return redirect("discussion-active", discussion_id=discussion_id)



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
    from core.models import NotificationPreference
    from core.services.notification_service import NotificationService
    
    # Ensure all preferences exist
    NotificationService.create_notification_preferences(request.user)
    
    if request.method == "POST":
        # First, collect all notification types that have any checkboxes
        # Format: pref_{notification_type}_{delivery_method}
        # Where delivery_method is one of: email, push, in_app
        notif_types_in_form = set()
        delivery_methods = {'email', 'push', 'in_app'}
        
        for key in request.POST.keys():
            if key.startswith("pref_"):
                # Remove "pref_" prefix
                rest = key[5:]  # Skip "pref_"
                
                # Check which delivery method suffix it has
                for dm in delivery_methods:
                    if rest.endswith(f"_{dm}"):
                        # Extract notification type by removing the delivery method suffix
                        notif_type = rest[:-len(dm)-1]  # -1 for the underscore
                        notif_types_in_form.add(notif_type)
                        break
        
        # Update preferences for each notification type
        preferences_updated = 0
        for notif_type in notif_types_in_form:
            try:
                pref = NotificationPreference.objects.get(
                    user=request.user,
                    notification_type=notif_type
                )
                
                # For each delivery method, check if the checkbox was submitted
                # If not submitted, it means unchecked (set to False)
                new_delivery = {
                    "email": f"pref_{notif_type}_email" in request.POST,
                    "push": f"pref_{notif_type}_push" in request.POST,
                    "in_app": f"pref_{notif_type}_in_app" in request.POST,
                }
                
                pref.delivery_method = new_delivery
                pref.enabled = any(new_delivery.values())
                pref.save()
                preferences_updated += 1
            except NotificationPreference.DoesNotExist:
                pass
        
        messages.success(request, f"Updated {preferences_updated} notification preferences.")
        return redirect("notification-preferences-view")
    
    # Get all preferences organized by category
    preferences = NotificationPreference.objects.filter(user=request.user).order_by("notification_type")
    
    # Organize by category
    discussion_prefs = []
    system_prefs = []
    social_prefs = []
    
    for pref in preferences:
        pref_data = {
            "type": pref.notification_type,
            "label": pref.get_notification_type_display(),
            "enabled": pref.enabled,
            "delivery": pref.delivery_method or {"email": False, "push": False, "in_app": True},
            "is_critical": pref.notification_type in NotificationService.CRITICAL_NOTIFICATIONS
        }
        
        if pref.notification_type in ["new_response", "round_ending_soon", "voting_phase_started"]:
            discussion_prefs.append(pref_data)
        elif pref.notification_type in ["parameter_changed", "became_observer", "can_rejoin", "discussion_archived"]:
            system_prefs.append(pref_data)
        else:
            social_prefs.append(pref_data)
    
    return render(request, "dashboard/notification_preferences.html", {
        "discussion_prefs": discussion_prefs,
        "system_prefs": system_prefs,
        "social_prefs": social_prefs
    })


# =============================================================================
# New UI Views for Refactored Discussion Interface
# =============================================================================


@login_required
def dashboard_new_view(request):
    """New dashboard with invite economy and discussion state cards."""
    user = request.user
    
    # Get all discussions where user is involved
    participations = DiscussionParticipant.objects.filter(
        user=user
    ).select_related('discussion')
    
    discussions = []
    for participation in participations:
        disc = participation.discussion
        # Get the latest active round
        current_round = Round.objects.filter(
            discussion=disc
        ).order_by('-round_number').first()
        
        # Determine UI status and action
        ui_status = 'waiting'
        ui_icon = '⏸️'
        action_label = 'Waiting for others'
        button_text = 'View Discussion'
        urgency = None
        urgency_level = 'low'
        deadline_iso = None
        time_remaining = None
        
        if participation.role == 'active':
            if current_round and current_round.status == 'in_progress':
                # Check if user has responded
                has_responded = Response.objects.filter(
                    round=current_round,
                    user=user
                ).exists()
                
                if not has_responded:
                    ui_status = 'active-needs-response'
                    ui_icon = '✍️'
                    action_label = 'Your response needed'
                    button_text = 'Respond Now'
                    urgency = True
                    
                    # Calculate deadline
                    from core.services.round_service import RoundService
                    mrp_deadline = RoundService.get_mrp_deadline(current_round)
                    if mrp_deadline:
                        deadline_iso = mrp_deadline.isoformat()
                        remaining = mrp_deadline - timezone.now()
                        if remaining.total_seconds() > 0:
                            minutes = int(remaining.total_seconds() / 60)
                            if minutes < 10:
                                urgency_level = 'high'
                                time_remaining = f'{minutes}m remaining'
                            elif minutes < 60:
                                urgency_level = 'medium'
                                time_remaining = f'{minutes}m remaining'
                            else:
                                hours = minutes // 60
                                urgency_level = 'low'
                                time_remaining = f'{hours}h remaining'
                else:
                    ui_status = 'waiting'
                    action_label = 'Waiting for other responses'
            
            elif current_round and current_round.status == 'voting':
                # Check if user has voted
                has_voted = current_round.votes.filter(user=user).exists()
                
                if not has_voted:
                    ui_status = 'voting-available'
                    ui_icon = '🗳️'
                    action_label = 'Voting available'
                    button_text = 'Vote Now'
                    urgency = True
                    urgency_level = 'medium'
                    
                    # Calculate voting deadline
                    if current_round.end_time and current_round.final_mrp_minutes:
                        voting_deadline = current_round.end_time + timedelta(
                            minutes=current_round.final_mrp_minutes
                        )
                        deadline_iso = voting_deadline.isoformat()
                        remaining = voting_deadline - timezone.now()
                        if remaining.total_seconds() > 0:
                            minutes = int(remaining.total_seconds() / 60)
                            time_remaining = f'{minutes}m to vote'
                else:
                    ui_status = 'waiting'
                    action_label = 'Votes submitted'
        
        elif participation.role == 'observer':
            ui_status = 'observer'
            ui_icon = '👁️'
            action_label = 'Observing'
            button_text = 'View as Observer'
        
        discussions.append({
            'id': disc.id,
            'topic_headline': disc.topic_headline,
            'current_round': current_round.round_number if current_round else 1,
            'participant_count': DiscussionParticipant.objects.filter(
                discussion=disc,
                role__in=['active', 'initiator']
            ).count(),
            'ui_status': ui_status,
            'ui_icon': ui_icon,
            'action_label': action_label,
            'button_text': button_text,
            'urgency': urgency,
            'urgency_level': urgency_level,
            'deadline_iso': deadline_iso,
            'time_remaining': time_remaining,
        })
    
    context = {
        'discussions': discussions,
    }
    
    return render(request, 'dashboard/home_new.html', context)


@login_required
def discussion_active_view(request, discussion_id):
    """Active discussion view for users who can respond."""
    discussion = get_object_or_404(Discussion, id=discussion_id)
    user = request.user
    
    # Check user is active participant
    participation = DiscussionParticipant.objects.filter(
        discussion=discussion,
        user=user,
        role__in=['active', 'initiator']
    ).first()
    
    if not participation:
        return redirect('discussion-observer', discussion_id=discussion_id)
    
    # Get the latest active round
    current_round = Round.objects.filter(
        discussion=discussion
    ).order_by('-round_number').first()
    
    if not current_round:
        return redirect('dashboard')
    
    # Get all responses in this round
    responses = Response.objects.filter(
        round=current_round
    ).select_related('user').order_by('created_at')
    
    # Calculate MRP deadline
    from core.services.round_service import RoundService
    mrp_deadline = RoundService.get_mrp_deadline(current_round)
    mrp_time_remaining = ''
    if mrp_deadline:
        remaining = mrp_deadline - timezone.now()
        if remaining.total_seconds() > 0:
            hours = int(remaining.total_seconds() / 3600)
            minutes = int((remaining.total_seconds() % 3600) / 60)
            mrp_time_remaining = f'{hours}:{minutes:02d}'
    
    # Determine participant status
    has_responded = Response.objects.filter(round=current_round, user=user).exists()
    participant_status = 'Responded this round' if has_responded else 'Response pending'
    
    context = {
        'discussion': discussion,
        'current_round': current_round,
        'responses': responses,
        'mrp_deadline': mrp_deadline,
        'mrp_time_remaining': mrp_time_remaining,
        'participant_status': participant_status,
    }
    
    return render(request, 'discussions/active_view.html', context)


@login_required
def discussion_voting_view(request, discussion_id):
    """Inter-round voting view for active participants."""
    discussion = get_object_or_404(Discussion, id=discussion_id)
    user = request.user
    
    # Check user is active participant
    participation = DiscussionParticipant.objects.filter(
        discussion=discussion,
        user=user,
        role__in=['active', 'initiator']
    ).first()
    
    if not participation:
        return HttpResponseForbidden("You must be an active participant to vote")
    
    # Get the latest round
    current_round = Round.objects.filter(
        discussion=discussion
    ).order_by('-round_number').first()
    
    if not current_round or current_round.status != 'voting':
        messages.error(request, "Discussion is not in voting phase")
        return redirect('discussion-detail', discussion_id=discussion_id)
    
    # Get join requests
    from core.models import JoinRequest
    join_requests = JoinRequest.objects.filter(
        discussion=discussion,
        status='pending'
    ).select_related('requester')
    
    # Get active participants for removal voting
    active_participants = User.objects.filter(
        participations__discussion=discussion,
        participations__role__in=['active', 'initiator']
    ).exclude(id=user.id)
    
    # Calculate parameter previews
    current_mrl = discussion.max_response_length_chars
    current_rtm = discussion.response_time_multiplier
    
    mrl_decrease = int(current_mrl * 0.9)
    mrl_increase = int(current_mrl * 1.1)
    rtm_decrease = round(current_rtm * 0.9, 1)
    rtm_increase = round(current_rtm * 1.1, 1)
    
    # Calculate voting deadline
    voting_deadline = None
    voting_time_remaining = ''
    if current_round.end_time and current_round.final_mrp_minutes:
        voting_deadline = current_round.end_time + timedelta(
            minutes=current_round.final_mrp_minutes
        )
        remaining = voting_deadline - timezone.now()
        if remaining.total_seconds() > 0:
            hours = int(remaining.total_seconds() / 3600)
            minutes = int((remaining.total_seconds() % 3600) / 60)
            voting_time_remaining = f'{hours}:{minutes:02d}'
    
    context = {
        'discussion': discussion,
        'current_round': current_round,
        'join_requests': join_requests,
        'active_participants': active_participants,
        'mrl_decrease': mrl_decrease,
        'mrl_increase': mrl_increase,
        'rtm_decrease': rtm_decrease,
        'rtm_increase': rtm_increase,
        'voting_deadline': voting_deadline,
        'voting_time_remaining': voting_time_remaining,
    }
    
    return render(request, 'discussions/voting.html', context)


@login_required
def discussion_observer_view(request, discussion_id):
    """Observer view for read-only discussion viewing."""
    discussion = get_object_or_404(Discussion, id=discussion_id)
    user = request.user
    
    # Check if user is observer or can view
    participation = DiscussionParticipant.objects.filter(
        discussion=discussion,
        user=user
    ).first()
    
    observer_reason = 'viewing'
    if participation:
        if participation.role == 'observer':
            # Determine why they're observer
            if participation.observer_reason == 'mrp_timeout':
                observer_reason = 'mrp_timeout'
            elif participation.observer_reason == 'removed_by_vote':
                observer_reason = 'removed'
    
    # Get the latest active round
    current_round = Round.objects.filter(
        discussion=discussion
    ).order_by('-round_number').first()
    
    if not current_round:
        return redirect('dashboard')
    
    # Get all responses in this round
    responses = Response.objects.filter(
        round=current_round
    ).select_related('user').order_by('created_at')
    
    context = {
        'discussion': discussion,
        'current_round': current_round,
        'responses': responses,
        'observer_reason': observer_reason,
    }
    
    return render(request, 'discussions/observer_view.html', context)


@login_required
def discussion_create_wizard_view(request):
    """Multi-step wizard for creating new discussions."""
    # Get or create platform config
    config, _ = PlatformConfig.objects.get_or_create(
        pk=1,
        defaults={
            'max_headline_length': 100,
            'max_topic_length': 500,
        }
    )
    
    context = {
        'max_headline_length': config.max_headline_length,
        'max_topic_length': config.max_topic_length,
    }
    
    return render(request, 'discussions/create_wizard.html', context)
