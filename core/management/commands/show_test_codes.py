"""
Management command to show verification codes from cache (for testing).
"""

from django.core.management.base import BaseCommand
from django.core.cache import cache


class Command(BaseCommand):
    help = "Display all active verification codes (for development/testing)"

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING("\n=== ACTIVE VERIFICATION CODES ===\n"))
        self.stdout.write(
            "Note: This only works if you're using Redis cache. Check your logs for SMS codes.\n"
        )

        # Try to get verification codes from cache
        # This is a development-only utility
        from core.auth.registration import PhoneVerificationService

        self.stdout.write(
            self.style.SUCCESS(
                "\nTo see SMS verification codes in test mode, check your console output."
            )
        )
        self.stdout.write(
            "Look for lines starting with: [MOCK SMS] To: +1..., Code: xxxxxx\n"
        )

        self.stdout.write("\nAlternatively, use the create_test_user command:")
        self.stdout.write(
            "  python manage.py create_test_user <username> --phone +15551234567\n"
        )
