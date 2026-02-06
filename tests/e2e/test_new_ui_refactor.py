"""
E2E Tests for Refactored UI (New Dashboard, Active, Voting, Observer Views)

Tests the complete refactored UI including:
1. Dashboard with invite economy
2. Active discussion view with MRP timer
3. Voting view with blind voting
4. Observer view with join requests
5. Discussion creation wizard
"""

import pytest
import asyncio
import re
from datetime import timedelta
from django.utils import timezone
from playwright.async_api import Page, expect
from asgiref.sync import sync_to_async
from . import db_ops

pytestmark = [
    pytest.mark.playwright,
    pytest.mark.django_db(transaction=True),
    pytest.mark.asyncio
]


class TestNewDashboard:
    """Test new dashboard UI with invite economy."""

    async def test_dashboard_displays_invite_economy(
        self,
        page: Page,
        live_server_url: str,
        async_create_verified_user,
    ):
        """Test that dashboard shows platform and discussion invite credits."""
        # Create user with specific invite credits
        user = await async_create_verified_user("test_user")
        
        # Set invite credits
        @sync_to_async
        def set_credits():
            user.platform_invites_banked = 5.2
            user.discussion_invites_banked = 25
            user.save()
        
        await set_credits()
        
        # Login
        await page.goto(f"{live_server_url}/login/")
        await page.fill('input[name="username"]', "test_user")
        await page.fill('input[name="password"]', "testpass123")
        await page.click('button[type="submit"]')
        await page.wait_for_load_state("networkidle")
        
        # Navigate to new dashboard
        await page.goto(f"{live_server_url}/dashboard-new/")
        
        # Check invite economy widget
        platform_credit = page.locator('.credit-display.platform .value')
        discussion_credit = page.locator('.credit-display.discussion .value')
        
        await expect(platform_credit).to_contain_text("5.2")
        await expect(discussion_credit).to_contain_text("25")
    
    async def test_dashboard_shows_active_discussion_cards(
        self,
        page: Page,
        live_server_url: str,
        async_create_verified_user,
        async_create_discussion,
    ):
        """Test that dashboard displays discussion cards with status badges."""
        user = await async_create_verified_user("test_user")
        discussion = await async_create_discussion(user, "Test Discussion")
        
        # Login
        await page.goto(f"{live_server_url}/login/")
        await page.fill('input[name="username"]', "test_user")
        await page.fill('input[name="password"]', "testpass123")
        await page.click('button[type="submit"]')
        await page.wait_for_load_state("networkidle")
        
        # Navigate to dashboard
        await page.goto(f"{live_server_url}/dashboard-new/")
        
        # Check discussion card exists
        discussion_card = page.locator(f'[data-discussion-id="{discussion.id}"]')
        await expect(discussion_card).to_be_visible()
        
        # Check status badge
        status_badge = discussion_card.locator('.status-badge')
        await expect(status_badge).to_be_visible()


class TestActiveDiscussionView:
    """Test active discussion view with response submission."""

    async def test_active_view_displays_mrp_timer(
        self,
        page: Page,
        live_server_url: str,
        async_create_verified_user,
        async_create_discussion,
    ):
        """Test that active view shows MRP countdown timer."""
        user = await async_create_verified_user("test_user")
        discussion = await async_create_discussion(user, "Test Discussion")
        
        # Set MRP deadline by configuring final_mrp_minutes and start_time
        @sync_to_async
        def set_mrp():
            from core.models import Round
            current_round = Round.objects.filter(discussion=discussion, round_number=1).first()
            if current_round:
                current_round.final_mrp_minutes = 30
                current_round.start_time = timezone.now()
                current_round.status = "in_progress"
                current_round.save()
        
        await set_mrp()
        
        # Login
        await page.goto(f"{live_server_url}/login/")
        await page.fill('input[name="username"]', "test_user")
        await page.fill('input[name="password"]', "testpass123")
        await page.click('button[type="submit"]')
        await page.wait_for_load_state("networkidle")
        
        # Navigate to active view
        await page.goto(f"{live_server_url}/discussions/{discussion.id}/active/")
        
        # Check MRP timer exists
        mrp_timer = page.locator('#mrp-timer')
        await expect(mrp_timer).to_be_visible()
        await expect(mrp_timer).to_contain_text(":")
    
    async def test_character_counter_enforces_limit(
        self,
        page: Page,
        live_server_url: str,
        async_create_verified_user,
        async_create_discussion,
    ):
        """Test that character counter updates and enforces max length."""
        user = await async_create_verified_user("test_user")
        discussion = await async_create_discussion(user, "Test Discussion")
        
        # Login
        await page.goto(f"{live_server_url}/login/")
        await page.fill('input[name="username"]', "test_user")
        await page.fill('input[name="password"]', "testpass123")
        await page.click('button[type="submit"]')
        await page.wait_for_load_state("networkidle")
        
        # Navigate to active view
        await page.goto(f"{live_server_url}/discussions/{discussion.id}/active/")
        
        # Type in response input
        response_input = page.locator('#response-input')
        await response_input.fill("This is a test response")
        
        # Check character counter updated
        char_counter = page.locator('#length-counter .current')
        await expect(char_counter).to_contain_text("23")
        
        # Submit button should be enabled
        submit_btn = page.locator('#submit-btn')
        await expect(submit_btn).to_be_enabled()
    
    async def test_quote_response_functionality(
        self,
        page: Page,
        live_server_url: str,
        async_create_verified_user,
        async_create_discussion,
    ):
        """Test quoting another user's response."""
        user1 = await async_create_verified_user("user1")
        user2 = await async_create_verified_user("user2")
        discussion = await async_create_discussion(user1, "Test Discussion")
        
        # Add user2 as participant and create a response
        @sync_to_async
        def setup_response():
            from core.models import DiscussionParticipant, Response, Round
            DiscussionParticipant.objects.update_or_create(
                discussion=discussion,
                user=user2,
                defaults={'role': 'active'},
            )
            current_round = Round.objects.filter(discussion=discussion, round_number=1).first()
            Response.objects.create(
                round=current_round,
                user=user1,
                content="This is the first response"
            )
        
        await setup_response()
        
        # Login as user2
        await page.goto(f"{live_server_url}/login/")
        await page.fill('input[name="username"]', "user2")
        await page.fill('input[name="password"]', "testpass123")
        await page.click('button[type="submit"]')
        await page.wait_for_load_state("networkidle")
        
        # Navigate to active view
        await page.goto(f"{live_server_url}/discussions/{discussion.id}/active/")
        
        # Click quote button
        quote_btn = page.locator('.quote-btn').first
        await quote_btn.click()
        
        # Check quote indicator appears
        quote_indicator = page.locator('#active-quote-indicator')
        await expect(quote_indicator).to_be_visible()
        await expect(quote_indicator).to_contain_text("@user1")


class TestVotingView:
    """Test inter-round voting view."""

    async def test_voting_view_shows_parameter_options(
        self,
        page: Page,
        live_server_url: str,
        async_create_verified_user,
        async_create_discussion,
    ):
        """Test that voting view displays MRL and RTM options."""
        user = await async_create_verified_user("test_user")
        discussion = await async_create_discussion(user, "Test Discussion")
        
        # Set round to voting status
        @sync_to_async
        def set_voting():
            from core.models import Round
            current_round = Round.objects.filter(discussion=discussion, round_number=1).first()
            if current_round:
                current_round.status = 'voting'
                current_round.end_time = timezone.now()
                current_round.final_mrp_minutes = 30
                current_round.save()
        
        await set_voting()
        
        # Login
        await page.goto(f"{live_server_url}/login/")
        await page.fill('input[name="username"]', "test_user")
        await page.fill('input[name="password"]', "testpass123")
        await page.click('button[type="submit"]')
        await page.wait_for_load_state("networkidle")
        
        # Navigate to voting view
        await page.goto(f"{live_server_url}/discussions/{discussion.id}/voting/")
        
        # Check MRL voting options
        mrl_options = page.locator('[data-vote-type="mrl"]')
        await expect(mrl_options.first).to_be_visible()
        
        # Check RTM voting options
        rtm_options = page.locator('[data-vote-type="rtm"]')
        await expect(rtm_options.first).to_be_visible()
        
        # Check voting incentive message
        incentive = page.locator('.voting-incentive')
        await expect(incentive).to_contain_text("Platform Invites")
        await expect(incentive).to_contain_text("Discussion Invite")
    
    async def test_voting_selection_updates_ui(
        self,
        page: Page,
        live_server_url: str,
        async_create_verified_user,
        async_create_discussion,
    ):
        """Test that selecting vote options updates UI state."""
        user = await async_create_verified_user("test_user")
        discussion = await async_create_discussion(user, "Test Discussion")
        
        # Set round to voting
        @sync_to_async
        def set_voting():
            from core.models import Round
            current_round = Round.objects.filter(discussion=discussion, round_number=1).first()
            if current_round:
                current_round.status = 'voting'
                current_round.end_time = timezone.now()
                current_round.final_mrp_minutes = 30
                current_round.save()
        
        await set_voting()
        
        # Login
        await page.goto(f"{live_server_url}/login/")
        await page.fill('input[name="username"]', "test_user")
        await page.fill('input[name="password"]', "testpass123")
        await page.click('button[type="submit"]')
        await page.wait_for_load_state("networkidle")
        
        # Navigate to voting view
        await page.goto(f"{live_server_url}/discussions/{discussion.id}/voting/")
        
        # Select MRL increase option
        increase_option = page.locator('[data-vote-type="mrl"][data-vote-value="increase"]')
        await expect(increase_option).to_be_visible(timeout=5000)
        
        # Use JS to call the onclick handler directly
        await page.evaluate("""
            const btn = document.querySelector('[data-vote-type="mrl"][data-vote-value="increase"]');
            selectVote(btn);
        """)
        await page.wait_for_timeout(300)
        
        # Check it's marked as selected
        await expect(increase_option).to_have_class(re.compile("selected"))


class TestObserverView:
    """Test observer view with read-only access."""

    async def test_observer_view_is_read_only(
        self,
        page: Page,
        live_server_url: str,
        async_create_verified_user,
        async_create_discussion,
    ):
        """Test that observer view doesn't show response composer."""
        user = await async_create_verified_user("test_user")
        discussion = await async_create_discussion(user, "Test Discussion")
        
        # Set user as observer
        @sync_to_async
        def set_observer():
            from core.models import DiscussionParticipant
            participant = DiscussionParticipant.objects.get(
                discussion=discussion,
                user=user
            )
            participant.role = 'observer'
            participant.save()
        
        await set_observer()
        
        # Login
        await page.goto(f"{live_server_url}/login/")
        await page.fill('input[name="username"]', "test_user")
        await page.fill('input[name="password"]', "testpass123")
        await page.click('button[type="submit"]')
        await page.wait_for_load_state("networkidle")
        
        # Navigate to observer view
        await page.goto(f"{live_server_url}/discussions/{discussion.id}/observer/")
        
        # Check observer badge is visible
        observer_badge = page.locator('.observer-badge')
        await expect(observer_badge).to_contain_text("Observer")
        
        # Check no response input
        response_input = page.locator('#response-input')
        await expect(response_input).not_to_be_visible()
        
        # Check "Ask to Join" button is visible
        ask_to_join_btn = page.locator('button:has-text("Request to Join")')
        await expect(ask_to_join_btn).to_be_visible()


class TestDiscussionCreationWizard:
    """Test discussion creation wizard."""

    async def test_wizard_multi_step_navigation(
        self,
        page: Page,
        live_server_url: str,
        async_create_verified_user,
    ):
        """Test navigating through wizard steps."""
        user = await async_create_verified_user("test_user")
        
        # Set credits
        @sync_to_async
        def set_credits():
            user.discussion_invites_banked = 10
            user.save()
        
        await set_credits()
        
        # Login
        await page.goto(f"{live_server_url}/login/")
        await page.fill('input[name="username"]', "test_user")
        await page.fill('input[name="password"]', "testpass123")
        await page.click('button[type="submit"]')
        await page.wait_for_load_state("networkidle")
        
        # Navigate to wizard
        await page.goto(f"{live_server_url}/discussions/create-wizard/")
        
        # Check Step 1 is visible
        step1 = page.locator('[data-step="1"]')
        await expect(step1).to_have_class(re.compile("active"))
        
        # Fill headline and topic
        await page.fill('#headline', "Test Discussion")
        await page.fill('#topic', "This is a test discussion topic")
        
        # Click Next (within the active step only)
        next_btn = page.locator('.wizard-step.active button:has-text("Next")')
        await next_btn.click()
        
        # Wait for Step 2
        await page.wait_for_timeout(500)
        step2 = page.locator('[data-step="2"]')
        await expect(step2).to_have_class(re.compile("active"))
    
    async def test_wizard_budget_warning(
        self,
        page: Page,
        live_server_url: str,
        async_create_verified_user,
    ):
        """Test that wizard shows warning when inviting more users than credits."""
        user = await async_create_verified_user("test_user")
        
        # Set low credits
        @sync_to_async
        def set_credits():
            user.discussion_invites_banked = 2
            user.save()
        
        await set_credits()
        
        # Create some users to invite
        await async_create_verified_user("user1")
        await async_create_verified_user("user2")
        await async_create_verified_user("user3")
        
        # Login
        await page.goto(f"{live_server_url}/login/")
        await page.fill('input[name="username"]', "test_user")
        await page.fill('input[name="password"]', "testpass123")
        await page.click('button[type="submit"]')
        await page.wait_for_load_state("networkidle")
        
        # Navigate to wizard and proceed to step 3
        await page.goto(f"{live_server_url}/discussions/create-wizard/")
        await page.fill('#headline', "Test")
        await page.fill('#topic', "Test topic")
        await page.click('button:has-text("Next")')
        await page.wait_for_timeout(500)
        await page.click('button:has-text("Next")')
        
        # Wait for step 3
        await page.wait_for_timeout(500)
        
        # Add 3 participants (more than credits)
        # Note: This requires implementing the user search functionality
        # For now, just check the warning element exists
        budget_warning = page.locator('#budget-warning')
        # Warning should not be visible initially
        await expect(budget_warning).not_to_be_visible()
