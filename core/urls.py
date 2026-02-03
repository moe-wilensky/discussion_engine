"""
URL configuration for core app API endpoints.

Maps URLs to view functions for auth, invites, onboarding, and join requests.
"""

from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from core.api import auth, invites, onboarding_join, discussions, responses, voting

app_name = 'core'

urlpatterns = [
    # Authentication endpoints
    path('auth/register/request-verification/', auth.request_verification, name='request-verification'),
    path('auth/register/verify/', auth.verify_and_register, name='verify-register'),
    path('auth/login/', auth.login_request, name='login-request'),
    path('auth/login/verify/', auth.login_verify, name='login-verify'),
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    
    # Invite endpoints
    path('invites/me/', invites.my_invites, name='my-invites'),
    path('invites/platform/send/', invites.send_platform_invite, name='send-platform-invite'),
    path('invites/platform/accept/', invites.accept_platform_invite, name='accept-platform-invite'),
    path('invites/discussion/send/', invites.send_discussion_invite, name='send-discussion-invite'),
    path('invites/received/', invites.received_invites, name='received-invites'),
    path('invites/<int:invite_id>/accept/', invites.accept_invite, name='accept-invite'),
    path('invites/<int:invite_id>/decline/', invites.decline_invite, name='decline-invite'),
    path('users/<int:user_id>/invite-metrics/', invites.user_invite_metrics, name='user-invite-metrics'),
    
    # Onboarding endpoints
    path('onboarding/tutorial/', onboarding_join.tutorial_steps, name='tutorial-steps'),
    path('onboarding/tutorial/complete/', onboarding_join.complete_tutorial, name='complete-tutorial'),
    path('onboarding/suggested-discussions/', onboarding_join.suggested_discussions, name='suggested-discussions'),
    
    # Join request endpoints
    path('discussions/<int:discussion_id>/join-request/', onboarding_join.create_join_request, name='create-join-request'),
    path('discussions/<int:discussion_id>/join-requests/', onboarding_join.discussion_join_requests, name='discussion-join-requests'),
    path('join-requests/<int:request_id>/approve/', onboarding_join.approve_join_request, name='approve-join-request'),
    path('join-requests/<int:request_id>/decline/', onboarding_join.decline_join_request, name='decline-join-request'),
    
    # Discussion endpoints
    path('discussions/presets/', discussions.get_presets, name='discussion-presets'),
    path('discussions/preview-parameters/', discussions.preview_parameters, name='preview-parameters'),
    path('discussions/', discussions.list_discussions, name='list-discussions'),
    path('discussions/create/', discussions.create_discussion, name='create-discussion'),
    path('discussions/<int:discussion_id>/', discussions.get_discussion, name='get-discussion'),
    
    # Response endpoints
    path('discussions/<int:discussion_id>/rounds/<int:round_number>/responses/', responses.list_responses, name='list-responses'),
    path('discussions/<int:discussion_id>/rounds/<int:round_number>/responses/create/', responses.create_response, name='create-response'),
    path('discussions/<int:discussion_id>/rounds/<int:round_number>/save-draft/', responses.save_draft_for_round, name='save-draft-round'),
    path('responses/<int:response_id>/', responses.edit_response, name='edit-response'),
    path('responses/<int:response_id>/save-draft/', responses.save_draft, name='save-draft'),
    path('responses/<int:response_id>/quote/', responses.create_quote, name='create-quote'),
    
    # Voting endpoints
    path('discussions/<int:discussion_id>/rounds/<int:round_number>/voting/status/', voting.voting_status, name='voting-status'),
    path('discussions/<int:discussion_id>/rounds/<int:round_number>/voting/parameter-results/', voting.parameter_results, name='parameter-results'),
    path('discussions/<int:discussion_id>/rounds/<int:round_number>/voting/parameters/', voting.cast_parameter_vote, name='cast-parameter-vote'),
    path('discussions/<int:discussion_id>/rounds/<int:round_number>/voting/removal-targets/', voting.removal_targets, name='removal-targets'),
    path('discussions/<int:discussion_id>/rounds/<int:round_number>/voting/removal/', voting.cast_removal_vote, name='cast-removal-vote'),
    path('discussions/<int:discussion_id>/rounds/<int:round_number>/voting/removal-results/', voting.removal_results, name='removal-results'),
    path('discussions/<int:discussion_id>/observer-status/', voting.observer_status, name='observer-status'),
    path('discussions/<int:discussion_id>/rejoin/', voting.rejoin_discussion, name='rejoin-discussion'),
]

