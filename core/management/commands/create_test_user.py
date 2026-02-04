"""
Management command to create test users bypassing phone verification.
"""

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

User = get_user_model()


class Command(BaseCommand):
    help = "Create a test user with verified phone number (for development)"

    def add_arguments(self, parser):
        parser.add_argument("username", type=str, help="Username for the test user")
        parser.add_argument(
            "--phone",
            type=str,
            default=None,
            help="Phone number (defaults to +1555<random>)",
        )
        parser.add_argument(
            "--password",
            type=str,
            default="testpass123",
            help="Password (defaults to 'testpass123')",
        )
        parser.add_argument(
            "--email",
            type=str,
            default=None,
            help="Email address (optional)",
        )
        parser.add_argument(
            "--superuser",
            action="store_true",
            help="Create as superuser",
        )

    def handle(self, *args, **options):
        username = options["username"]
        password = options["password"]
        phone = options["phone"]
        email = options["email"]
        is_superuser = options["superuser"]

        # Check if user exists
        if User.objects.filter(username=username).exists():
            self.stdout.write(
                self.style.ERROR(f'User "{username}" already exists.')
            )
            return

        # Generate phone number if not provided
        if not phone:
            import random
            phone = f"+1555{random.randint(1000000, 9999999)}"

        # Create user
        try:
            if is_superuser:
                user = User.objects.create_superuser(
                    username=username,
                    phone_number=phone,
                    password=password,
                    email=email or f"{username}@test.com",
                )
                user.phone_verified = True
                user.save()
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Superuser "{username}" created successfully!'
                    )
                )
            else:
                user = User.objects.create_user(
                    username=username,
                    phone_number=phone,
                    password=password,
                    email=email or "",
                )
                user.phone_verified = True  # Skip verification for test users
                user.save()
                self.stdout.write(
                    self.style.SUCCESS(f'Test user "{username}" created successfully!')
                )

            # Display credentials
            self.stdout.write("")
            self.stdout.write("Login credentials:")
            self.stdout.write(f"  Username: {username}")
            self.stdout.write(f"  Password: {password}")
            self.stdout.write(f"  Phone: {phone}")
            if email:
                self.stdout.write(f"  Email: {email}")

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error creating user: {str(e)}"))
