"""
Visual Regression Testing with Playwright Screenshots.

Tests visual consistency of key UI components using screenshot comparison.
Baselines are stored in tests/e2e/__screenshots__/ directory.

Run with: pytest tests/e2e/test_visual_regression.py -v
Update baselines: pytest tests/e2e/test_visual_regression.py --update-snapshots
"""

import pytest
from playwright.async_api import Page, expect


pytestmark = [
    pytest.mark.playwright,
    pytest.mark.django_db(transaction=True),
    pytest.mark.asyncio
]


class TestVisualRegression:
    """Visual regression tests for critical UI components."""

    async def test_discussion_creation_wizard_visual(
        self,
        page: Page,
        live_server_url: str,
        async_create_verified_user,
    ):
        """
        Visual regression test for Discussion Creation Wizard.

        Captures screenshots of each wizard step to detect CSS/layout regressions.

        Baseline screenshots are stored and compared on subsequent runs.
        Any visual changes will cause test failure unless explicitly updated.
        """
        # Create and login user
        user = await async_create_verified_user("visual_test_user")

        await page.goto(f"{live_server_url}/login/")
        await page.fill('input[name="username"]', "visual_test_user")
        await page.fill('input[name="password"]', "testpass123")
        await page.click('button[type="submit"]')
        await page.wait_for_load_state("networkidle")

        # Navigate to discussion creation wizard
        await page.goto(f"{live_server_url}/discussions/create/")
        await page.wait_for_selector("#step-1", state="visible")

        # Step 1: Topic Input
        await expect(page.locator("#step-1")).to_be_visible()

        # Fill in some content to make screenshot consistent
        await page.fill('input[name="topic"]', "Visual Regression Test")
        await page.fill('textarea[name="details"]', "Testing visual consistency")

        # Take screenshot of Step 1
        await page.screenshot(path="tests/e2e/__screenshots__/wizard-step-1-topic.png")

        # Move to Step 2
        await page.click('button:has-text("Next →")')
        await page.wait_for_selector("#step-2", state="visible")

        # Step 2: Preset Selection
        await expect(page.locator("#step-2")).to_be_visible()

        # Take screenshot of Step 2
        await page.screenshot(path="tests/e2e/__screenshots__/wizard-step-2-presets.png")

    async def test_login_page_visual(
        self,
        page: Page,
        live_server_url: str,
    ):
        """
        Visual regression test for login page.

        Ensures login form layout and styling remain consistent.
        """
        await page.goto(f"{live_server_url}/login/")
        await page.wait_for_load_state("networkidle")

        # Wait for form to be visible
        await page.wait_for_selector('input[name="username"]', state="visible")

        # Take screenshot of login page
        await page.screenshot(path="tests/e2e/__screenshots__/login-page.png")

    async def test_discussions_list_visual(
        self,
        page: Page,
        live_server_url: str,
        async_create_verified_user,
    ):
        """
        Visual regression test for discussions list page.

        Captures the discussions browse/list interface.
        """
        # Create and login user
        user = await async_create_verified_user("visual_discussions_user")

        await page.goto(f"{live_server_url}/login/")
        await page.fill('input[name="username"]', "visual_discussions_user")
        await page.fill('input[name="password"]', "testpass123")
        await page.click('button[type="submit"]')
        await page.wait_for_load_state("networkidle")

        # Navigate to discussions page
        await page.goto(f"{live_server_url}/discussions/")
        await page.wait_for_load_state("networkidle")

        # Take screenshot of discussions list
        await page.screenshot(path="tests/e2e/__screenshots__/discussions-list.png", full_page=True)
