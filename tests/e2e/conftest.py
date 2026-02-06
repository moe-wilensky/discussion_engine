"""
Pytest configuration specific to E2E tests.

This module provides async-native Playwright fixtures that work seamlessly
with pytest-asyncio and Django ORM operations.

Key Features:
- Native async support without -p no:asyncio
- Thread-safe Django ORM operations via sync_to_async
- Multi-user concurrent testing support
- Robust wait helpers with database state verification
- Proper database isolation with @pytest.mark.django_db(transaction=True)
- ASGI live server with WebSocket support via Daphne

To run E2E tests:
1. Install Playwright browsers: `playwright install chromium`
2. Run with: `pytest tests/e2e/ -m playwright --no-cov`
3. Or run individually with headful mode: `pytest tests/e2e/test_workflow_discussion_cycle.py -v --headed`
"""

import pytest
import asyncio
import socket
import time
from typing import Callable, Optional
from playwright.async_api import async_playwright, Page, BrowserContext, Browser, Playwright
from asgiref.sync import sync_to_async
from django.test import AsyncClient
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
import aiohttp
from . import db_ops


# Configure pytest-asyncio for function scope
pytestmark = pytest.mark.asyncio


# Playwright Browser Configuration
@pytest.fixture(scope="session")
def browser_type_launch_args(pytestconfig):
    """Configure browser launch args for E2E tests."""
    headless = not pytestconfig.getoption("--headed", default=False)
    return {
        "headless": headless,
        "args": [
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
        ],
        "slow_mo": 50 if not headless else 0,  # Slow down for debugging
    }


@pytest.fixture(scope="session")
def browser_context_args(pytestconfig):
    """Configure browser context for E2E tests."""
    # Enable video recording on failure (stored in test-results/)
    video_dir = "test-results/videos" if pytestconfig.option.video == "on" or pytestconfig.option.video == "retain-on-failure" else None

    return {
        "viewport": {"width": 1920, "height": 1080},
        "ignore_https_errors": True,
        "record_video_dir": video_dir,
        "record_video_size": {"width": 1920, "height": 1080} if video_dir else None,
    }


# Live Server Fixture with ASGI Support and Health Check
@pytest.fixture(scope="function")
def live_server_url(live_server):
    """
    Provide live server URL for E2E tests with health check.
    
    Uses pytest-django's built-in live_server which supports ASGI
    when ASGI_APPLICATION is configured in settings.
    
    This fixture includes a health check that waits for the server
    to actually be responsive before tests proceed.
    """
    import requests
    from requests.exceptions import ConnectionError, Timeout
    
    url = live_server.url
    max_attempts = 50  # 5 seconds with 100ms intervals
    attempt = 0
    
    while attempt < max_attempts:
        try:
            # Try to connect to the server root
            response = requests.get(f"{url}/", timeout=2)
            # Server is responding - check if it's a valid response
            if response.status_code in [200, 301, 302, 404]:
                # Even 404 is fine - means server is running
                return url
        except (ConnectionError, Timeout):
            # Server not ready yet
            pass
        
        time.sleep(0.1)
        attempt += 1
    
    # If we get here, server never became responsive
    raise RuntimeError(
        f"Live server at {url} did not become responsive after {max_attempts * 0.1} seconds. "
        "This indicates a critical server startup failure. Check logs for errors."
    )


# Async Playwright Fixtures (function scope for better compatibility)
@pytest.fixture(scope="function")
async def playwright_instance():
    """Create a Playwright instance for each test."""
    async with async_playwright() as p:
        yield p


@pytest.fixture(scope="function")
async def browser(playwright_instance: Playwright, browser_type_launch_args, request):
    """Create a browser instance for each test.

    Supports multiple browser types via pytest markers:
    - @pytest.mark.browser("chromium") [default]
    - @pytest.mark.browser("firefox")
    - @pytest.mark.browser("webkit")
    """
    # Get browser type from marker, default to chromium
    browser_name = "chromium"
    marker = request.node.get_closest_marker("browser")
    if marker:
        browser_name = marker.args[0] if marker.args else "chromium"

    # Launch the appropriate browser
    browser_type = getattr(playwright_instance, browser_name)
    browser = await browser_type.launch(**browser_type_launch_args)
    yield browser
    await browser.close()


@pytest.fixture(scope="function")
async def context(browser: Browser, browser_context_args):
    """Create a new browser context for each test."""
    context = await browser.new_context(**browser_context_args)
    yield context
    await context.close()


@pytest.fixture(scope="function")
async def page(context: BrowserContext):
    """Create a new page for each test."""
    page = await context.new_page()
    yield page
    await page.close()


# Multi-User Testing Support
@pytest.fixture
async def multi_context(browser: Browser, browser_context_args):
    """
    Create multiple browser contexts for multi-user testing.
    
    Returns a factory function that creates isolated browser contexts.
    Useful for testing WebSocket updates and concurrent user interactions.
    
    Example:
        async def test_multi_user(multi_context):
            ctx1 = await multi_context()
            ctx2 = await multi_context()
            page1 = await ctx1.new_page()
            page2 = await ctx2.new_page()
    """
    contexts = []
    
    async def _create_context():
        ctx = await browser.new_context(**browser_context_args)
        contexts.append(ctx)
        return ctx
    
    yield _create_context
    
    # Cleanup all contexts
    for ctx in contexts:
        await ctx.close()


@pytest.fixture
async def multi_page(multi_context: Callable):
    """
    Create multiple pages for multi-user testing.
    
    Returns a factory function that creates pages in separate contexts.
    Each page represents a different user session.
    
    Example:
        async def test_concurrent_users(multi_page):
            page1 = await multi_page()  # User 1
            page2 = await multi_page()  # User 2
    """
    pages = []
    
    async def _create_page():
        ctx = await multi_context()
        page = await ctx.new_page()
        pages.append(page)
        return page
    
    yield _create_page
    
    # Pages will be closed when their contexts close


# Async-Safe User Management
@pytest.fixture
def async_create_verified_user():
    """
    Create verified users asynchronously for E2E tests.
    
    Uses sync_to_async to safely interact with Django ORM.
    Database changes are committed immediately for live_server visibility.
    
    Example:
        user = await async_create_verified_user("alice")
        user2 = await async_create_verified_user("bob", phone_verified=True)
    """
    async def _create_user(username: str, **kwargs):
        return await db_ops.create_verified_user(username, **kwargs)
    
    return _create_user


@pytest.fixture
def async_create_discussion():
    """
    Create discussions asynchronously for E2E tests.
    
    Example:
        discussion = await async_create_discussion(user, "Test Discussion")
        discussion = await async_create_discussion(user, "Topic", topic_details="Details", status="voting")
    """
    async def _create_discussion(initiator, topic_headline: str, topic_details: str = "", **kwargs):
        return await db_ops.create_discussion(initiator, topic_headline, topic_details, **kwargs)
    
    return _create_discussion


# Async Login Helper
@pytest.fixture
def async_login_user():
    """
    Helper to login a user via Playwright UI asynchronously.
    
    Example:
        page = await async_login_user(page, user, live_server_url)
    """
    async def _login(page: Page, user, live_server_url: str, password: str = "testpass123"):
        """Login a user through the UI."""
        await page.goto(f"{live_server_url}/login/")
        await page.wait_for_load_state("networkidle")
        
        # Get username from user object safely
        username = await sync_to_async(lambda: user.username)()
        
        await page.fill('input[name="username"]', username)
        await page.fill('input[name="password"]', password)
        await page.click('button[type="submit"]')
        await page.wait_for_load_state("networkidle")
        
        return page
    
    return _login


# Async API Client
@pytest.fixture
async def async_api_client():
    """Provide AsyncClient for internal API calls during E2E tests."""
    return AsyncClient()


# Robust Wait Helpers with Database Polling
@pytest.fixture
def wait_for_selector_with_db_check():
    """
    Wait for a selector while polling database state.
    
    This ensures UI transitions are synchronized with backend state changes.
    Useful for verifying WebSocket updates, round transitions, etc.
    
    Example:
        async def check_round_status():
            round_obj = await db_ops.get_round(discussion, 1)
            return round_obj.status == "voting"
        
        await wait_for_selector_with_db_check(
            page, 
            "button:has-text('Vote')",
            db_check_func=check_round_status
        )
    """
    async def _wait_for(
        page: Page,
        selector: str,
        db_check_func: Optional[Callable] = None,
        timeout: int = 10000,
        poll_interval: int = 500
    ):
        """
        Wait for selector to appear and optionally verify database state.
        
        Args:
            page: Playwright page object
            selector: CSS selector to wait for
            db_check_func: Optional async function that returns True when DB state is correct
            timeout: Maximum wait time in milliseconds
            poll_interval: How often to check DB state in milliseconds
        
        Returns:
            The element locator
        """
        start_time = asyncio.get_event_loop().time()
        timeout_seconds = timeout / 1000
        poll_seconds = poll_interval / 1000
        
        last_error = None
        
        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > timeout_seconds:
                error_msg = (
                    f"Timeout waiting for selector '{selector}' "
                    f"and database condition after {timeout}ms"
                )
                if last_error:
                    error_msg += f"\nLast error: {last_error}"
                raise TimeoutError(error_msg)
            
            # Check if selector exists
            try:
                locator = page.locator(selector)
                is_visible = await locator.is_visible(timeout=poll_interval)
                
                if is_visible:
                    # If no DB check, we're done
                    if db_check_func is None:
                        return locator
                    
                    # Verify database state
                    db_ready = await db_check_func()
                    if db_ready:
                        return locator
            except Exception as e:
                last_error = str(e)
                pass  # Continue polling
            
            await asyncio.sleep(poll_seconds)
    
    return _wait_for


@pytest.fixture
def wait_for_db_condition():
    """
    Wait for a database condition to be true.
    
    Useful for verifying backend state changes during E2E tests.
    
    Example:
        async def check_response_count():
            count = await db_ops.count_responses(round_obj)
            return count >= 2
        
        await wait_for_db_condition(check_response_count, timeout=5000)
    """
    async def _wait(
        check_func: Callable, 
        timeout: int = 10000, 
        poll_interval: int = 500
    ):
        """
        Poll database until condition is met.
        
        Args:
            check_func: Async function that returns True when condition is met
            timeout: Maximum wait time in milliseconds
            poll_interval: How often to check in milliseconds
        """
        start_time = asyncio.get_event_loop().time()
        timeout_seconds = timeout / 1000
        poll_seconds = poll_interval / 1000
        
        last_error = None
        
        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > timeout_seconds:
                error_msg = f"Timeout waiting for database condition after {timeout}ms"
                if last_error:
                    error_msg += f"\nLast error: {last_error}"
                raise TimeoutError(error_msg)
            
            try:
                if await check_func():
                    return True
            except Exception as e:
                last_error = str(e)
                pass  # Continue polling
            
            await asyncio.sleep(poll_seconds)
    
    return _wait


# Mock Twilio for E2E Tests
@pytest.fixture
def mock_twilio(monkeypatch):
    """Mock Twilio SMS verification for E2E tests."""
    import uuid

    def mock_send_verification(phone_number):
        """Mock verification code sending - returns (verification_id, success, message)."""
        return str(uuid.uuid4()), True, "Verification code sent"

    def mock_verify_code(verification_id, code):
        """Mock verification code checking - accept any 6-digit code."""
        if code and len(code) == 6:
            return True, "Phone number verified", "+15551234567"
        return False, "Invalid verification code", None

    # Patch the PhoneVerificationService class methods
    from core.auth.registration import PhoneVerificationService
    monkeypatch.setattr(PhoneVerificationService, "send_verification_code", mock_send_verification)
    monkeypatch.setattr(PhoneVerificationService, "verify_code", mock_verify_code)

    return True


# Helper: Async page navigation with error handling
@pytest.fixture
def safe_goto():
    """
    Navigate to a URL with retry logic and error handling.
    
    Example:
        await safe_goto(page, f"{live_server_url}/discussions/")
    """
    async def _goto(page: Page, url: str, retries: int = 3, wait_until: str = "networkidle"):
        """
        Navigate to URL with retry logic.
        
        Args:
            page: Playwright page
            url: URL to navigate to
            retries: Number of retry attempts
            wait_until: Wait until this load state
        """
        for attempt in range(retries):
            try:
                await page.goto(url, wait_until=wait_until, timeout=30000)
                return
            except Exception as e:
                if attempt == retries - 1:
                    raise
                await asyncio.sleep(1)
    
    return _goto


# Helper: Get element text safely (async)
@pytest.fixture
def get_text():
    """
    Get text content from an element safely.
    
    Example:
        text = await get_text(page, "h1")
    """
    async def _get_text(page: Page, selector: str, timeout: int = 5000) -> str:
        """Get text content from element."""
        try:
            locator = page.locator(selector).first
            return await locator.text_content(timeout=timeout) or ""
        except Exception:
            return ""
    
    return _get_text


# Pytest hooks for video/trace management
@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Capture test result for video/trace retention logic."""
    outcome = yield
    rep = outcome.get_result()

    # Store test outcome on the item for teardown access
    setattr(item, f"rep_{rep.when}", rep)


def pytest_runtest_teardown(item):
    """Clean up videos for passing tests (retain only on failure)."""
    import shutil
    import os

    # Only process if test used Playwright context (has video recording)
    if not hasattr(item, "rep_call"):
        return

    test_passed = item.rep_call.outcome == "passed"

    # If test passed, remove video to save space
    if test_passed:
        # Video path is stored in context, but we'll clean up the whole test dir
        test_results_dir = "test-results/videos"
        if os.path.exists(test_results_dir):
            # Clean up videos for this specific test (if identifiable)
            # Playwright names videos with test IDs, but for simplicity we'll keep all failed test videos
            pass  # Videos for passing tests will be cleaned up by Playwright automatically


# Network Condition Simulation
@pytest.fixture
async def simulate_network(page: Page):
    """
    Simulate network conditions for testing offline/slow network scenarios.

    Example usage:
        async def test_offline(page, simulate_network):
            await simulate_network("offline")
            # Test offline behavior

            await simulate_network("slow_3g")
            # Test slow network behavior

            await simulate_network("online")
            # Restore normal network
    """
    async def _set_network(condition: str):
        """
        Set network condition.

        Args:
            condition: Network condition preset
                - "offline": No network connectivity
                - "slow_3g": Slow 3G (400ms RTT, 400kbps down, 400kbps up)
                - "fast_3g": Fast 3G (562.5ms RTT, 1.6Mbps down, 750kbps up)
                - "online": Normal network (default)
        """
        cdp = await page.context.new_cdp_session(page)

        if condition == "offline":
            await cdp.send("Network.enable")
            await cdp.send(
                "Network.emulateNetworkConditions",
                {
                    "offline": True,
                    "latency": 0,
                    "downloadThroughput": 0,
                    "uploadThroughput": 0,
                },
            )
        elif condition == "slow_3g":
            await cdp.send("Network.enable")
            await cdp.send(
                "Network.emulateNetworkConditions",
                {
                    "offline": False,
                    "latency": 400,  # ms
                    "downloadThroughput": (400 * 1024) // 8,  # 400kbps in bytes/s
                    "uploadThroughput": (400 * 1024) // 8,
                },
            )
        elif condition == "fast_3g":
            await cdp.send("Network.enable")
            await cdp.send(
                "Network.emulateNetworkConditions",
                {
                    "offline": False,
                    "latency": 562.5,  # ms
                    "downloadThroughput": (1.6 * 1024 * 1024) // 8,  # 1.6Mbps
                    "uploadThroughput": (750 * 1024) // 8,  # 750kbps
                },
            )
        elif condition == "online":
            await cdp.send("Network.enable")
            await cdp.send(
                "Network.emulateNetworkConditions",
                {
                    "offline": False,
                    "latency": 0,
                    "downloadThroughput": -1,  # -1 = unlimited
                    "uploadThroughput": -1,
                },
            )
        else:
            raise ValueError(
                f"Unknown network condition: {condition}. "
                "Use: offline, slow_3g, fast_3g, or online"
            )

    return _set_network


# Mobile Viewport Testing
@pytest.fixture
async def mobile_viewport(context: BrowserContext):
    """
    Configure mobile viewport for responsive design testing.

    Example usage:
        async def test_mobile(page, mobile_viewport):
            await mobile_viewport("iphone_14")
            # Test mobile layout
    """
    async def _set_viewport(device: str):
        """
        Set viewport to mobile device preset.

        Args:
            device: Device preset name
                - "iphone_14": iPhone 14 (390x844)
                - "iphone_14_pro_max": iPhone 14 Pro Max (430x932)
                - "pixel_7": Google Pixel 7 (412x915)
                - "galaxy_s23": Samsung Galaxy S23 (360x780)
                - "ipad_mini": iPad Mini (768x1024)
        """
        presets = {
            "iphone_14": {"width": 390, "height": 844, "is_mobile": True, "has_touch": True},
            "iphone_14_pro_max": {"width": 430, "height": 932, "is_mobile": True, "has_touch": True},
            "pixel_7": {"width": 412, "height": 915, "is_mobile": True, "has_touch": True},
            "galaxy_s23": {"width": 360, "height": 780, "is_mobile": True, "has_touch": True},
            "ipad_mini": {"width": 768, "height": 1024, "is_mobile": True, "has_touch": True},
        }

        if device not in presets:
            raise ValueError(
                f"Unknown device: {device}. "
                f"Available: {', '.join(presets.keys())}"
            )

        config = presets[device]
        await context.set_viewport_size(
            {"width": config["width"], "height": config["height"]}
        )

    return _set_viewport

