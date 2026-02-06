"""
URL configuration for discussion_platform project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from core import views

urlpatterns = [
    path("admin/", admin.site.urls),
    # API endpoints
    path("api/", include("core.urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    # Template-based views
    # Authentication
    path("register/", views.register_view, name="register"),
    path("auth/register/", views.register_page, name="register-page"),  # For E2E tests
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("verify-phone/", views.verify_phone_view, name="verify-phone"),
    path("resend-verification/", views.resend_verification_view, name="resend-verification"),
    path("password-reset/", views.password_reset_view, name="password-reset"),
    # Dashboard
    path("", views.dashboard_view, name="dashboard"),
    path("invites/", views.invites_view, name="invites"),
    path("notifications/", views.notifications_view, name="notifications"),
    path("settings/", views.user_settings_view, name="user-settings"),
    # Discussions
    path("discussions/", views.discussion_list_view, name="discussion-list"),
    path("discussions/create/", views.discussion_create_view, name="discussion-create"),
    path("discussions/create-wizard/", views.discussion_create_wizard_view, name="discussion-create-wizard"),
    path(
        "discussions/<int:discussion_id>/",
        views.discussion_detail_view,
        name="discussion-detail",
    ),
    path(
        "discussions/<int:discussion_id>/participate/",
        views.discussion_participate_view,
        name="discussion-participate",
    ),
    path(
        "discussions/<int:discussion_id>/voting/",
        views.discussion_voting_view,
        name="discussion-voting",
    ),
    # Discussion Views (new UI)
    path(
        "discussions/<int:discussion_id>/active/",
        views.discussion_active_view,
        name="discussion-active",
    ),
    path(
        "discussions/<int:discussion_id>/observer/",
        views.discussion_observer_view,
        name="discussion-observer",
    ),
    # Moderation
    path(
        "discussions/<int:discussion_id>/moderation/history/",
        views.moderation_history_view,
        name="moderation-history",
    ),
    # Admin
    path("admin-dashboard/", views.admin_dashboard_view, name="admin-dashboard"),
    path("admin-dashboard/config/", views.admin_config_view, name="admin-config"),
    path(
        "admin-dashboard/analytics/", views.admin_analytics_view, name="admin-analytics"
    ),
    path(
        "admin-dashboard/queue/",
        views.admin_moderation_queue_view,
        name="admin-moderation-queue",
    ),
    # HTMX endpoints
    path("api/users/search/", views.user_search, name="user-search"),
    path(
        "api/notifications/<int:notification_id>/mark-read/",
        views.mark_notification_read,
        name="mark-notification-read",
    ),
    path("api/notifications/mark-all-read/", views.mark_all_read, name="mark-all-read"),
    # Notification preferences HTML view
    path(
        "notifications/preferences/",
        views.notification_preferences_view,
        name="notification-preferences-view",
    ),
]

# Serve static and media files in development
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.BASE_DIR / "core" / "static")
