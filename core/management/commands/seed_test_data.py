"""
Management command to seed the database with test data.
"""

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from core.models import (
    Discussion,
    DiscussionParticipant,
    Round,
    Response,
    PlatformConfig,
)

User = get_user_model()


class Command(BaseCommand):
    help = "Seeds the database with test data for development"

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Clear existing data before seeding",
        )

    def handle(self, *args, **options):
        if options["clear"]:
            self.stdout.write("Clearing existing data...")
            Response.objects.all().delete()
            Round.objects.all().delete()
            DiscussionParticipant.objects.all().delete()
            Discussion.objects.all().delete()
            User.objects.filter(is_superuser=False).delete()
            self.stdout.write(self.style.SUCCESS("Data cleared."))

        config = PlatformConfig.load()

        # Create test users
        self.stdout.write("Creating test users...")
        users = []
        for i in range(1, 6):
            username = f"testuser{i}"
            if not User.objects.filter(username=username).exists():
                user = User.objects.create_user(
                    username=username,
                    phone_number=f"+1555000000{i}",
                    password="testpass123",
                    phone_verified=True,
                )
                users.append(user)
                self.stdout.write(f"  Created user: {username}")
            else:
                users.append(User.objects.get(username=username))
                self.stdout.write(f"  User exists: {username}")

        # Create test discussions
        self.stdout.write("\nCreating test discussions...")
        discussions_data = [
            {
                "topic_headline": "Should we implement a 4-day work week?",
                "topic_details": "Discuss the pros and cons of implementing a 4-day work week in modern workplaces.",
                "status": "active",
            },
            {
                "topic_headline": "Best practices for remote team collaboration",
                "topic_details": "Share experiences and strategies for effective remote team collaboration.",
                "status": "active",
            },
            {
                "topic_headline": "Climate change: Individual vs. Corporate responsibility",
                "topic_details": "Debate whether climate change action should focus more on individual or corporate responsibility.",
                "status": "voting",
            },
        ]

        for idx, disc_data in enumerate(discussions_data):
            initiator = users[idx % len(users)]

            if not Discussion.objects.filter(topic_headline=disc_data["topic_headline"]).exists():
                discussion = Discussion.objects.create(
                    initiator=initiator,
                    topic_headline=disc_data["topic_headline"],
                    topic_details=disc_data["topic_details"],
                    status=disc_data["status"],
                    max_response_length_chars=config.mrl_min_chars,
                    response_time_multiplier=1.0,
                    min_response_time_minutes=config.mrm_min_minutes,
                )

                # Create participant record for initiator
                DiscussionParticipant.objects.create(
                    discussion=discussion, user=initiator, role="initiator"
                )

                # Add a few more participants
                for i in range(1, min(4, len(users))):
                    other_user = users[(idx + i) % len(users)]
                    if other_user != initiator:
                        DiscussionParticipant.objects.create(
                            discussion=discussion, user=other_user, role="active"
                        )

                # Create first round
                round1 = Round.objects.create(
                    discussion=discussion,
                    round_number=1,
                    status="active" if disc_data["status"] == "active" else "completed",
                )

                # Add some responses
                Response.objects.create(
                    round=round1,
                    user=initiator,
                    content=f"This is the opening statement for: {disc_data['topic_headline']}",
                )

                self.stdout.write(
                    self.style.SUCCESS(f"  Created discussion: {disc_data['topic_headline']}")
                )
            else:
                self.stdout.write(f"  Discussion exists: {disc_data['topic_headline']}")

        self.stdout.write("\n" + self.style.SUCCESS("Test data seeded successfully!"))
        self.stdout.write("\nYou can now:")
        self.stdout.write("  - Login with: testuser1 / testpass123")
        self.stdout.write("  - Access discussions at: http://localhost:8002/discussions/")
        self.stdout.write("  - View discussion detail at: http://localhost:8002/discussions/1/")
