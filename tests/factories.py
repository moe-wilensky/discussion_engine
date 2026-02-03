"""
Factory boy factories for test data generation.
"""

import factory
from factory.django import DjangoModelFactory
from faker import Faker
from django.contrib.auth import get_user_model
from core.models import (
    PlatformConfig,
    Discussion,
    DiscussionParticipant,
    Round,
    Response,
    Vote,
    RemovalVote,
    ModerationAction,
    Invite,
    JoinRequest,
    ResponseEdit,
    DraftResponse,
    NotificationPreference,
)

fake = Faker()
User = get_user_model()


class UserFactory(DjangoModelFactory):
    class Meta:
        model = User

    username = factory.Sequence(lambda n: f"user{n}")
    email = factory.LazyAttribute(lambda obj: f"{obj.username}@example.com")
    phone_number = factory.Sequence(lambda n: f"+1555{n:07d}")
    password = factory.PostGenerationMethodCall("set_password", "testpass123")

    platform_invites_acquired = 0
    platform_invites_used = 0
    platform_invites_banked = 0
    discussion_invites_acquired = 0
    discussion_invites_used = 0
    discussion_invites_banked = 0


class DiscussionFactory(DjangoModelFactory):
    class Meta:
        model = Discussion

    topic_headline = factory.Faker("sentence", nb_words=5)
    topic_details = factory.Faker("paragraph")
    max_response_length_chars = 500
    response_time_multiplier = 1.0
    min_response_time_minutes = 5
    initiator = factory.SubFactory(UserFactory)
    status = "active"


class DiscussionParticipantFactory(DjangoModelFactory):
    class Meta:
        model = DiscussionParticipant

    discussion = factory.SubFactory(DiscussionFactory)
    user = factory.SubFactory(UserFactory)
    role = "active"


class RoundFactory(DjangoModelFactory):
    class Meta:
        model = Round

    discussion = factory.SubFactory(DiscussionFactory)
    round_number = factory.Sequence(lambda n: n + 1)
    status = "in_progress"


class ResponseFactory(DjangoModelFactory):
    class Meta:
        model = Response

    round = factory.SubFactory(RoundFactory)
    user = factory.SubFactory(UserFactory)
    content = factory.Faker("paragraph", nb_sentences=3)
    character_count = factory.LazyAttribute(lambda obj: len(obj.content))


class VoteFactory(DjangoModelFactory):
    class Meta:
        model = Vote

    round = factory.SubFactory(RoundFactory)
    user = factory.SubFactory(UserFactory)
    mrl_vote = "no_change"
    rtm_vote = "no_change"


class RemovalVoteFactory(DjangoModelFactory):
    class Meta:
        model = RemovalVote

    round = factory.SubFactory(RoundFactory)
    voter = factory.SubFactory(UserFactory)
    target = factory.SubFactory(UserFactory)


class ModerationActionFactory(DjangoModelFactory):
    class Meta:
        model = ModerationAction

    discussion = factory.SubFactory(DiscussionFactory)
    action_type = "mutual_removal"
    initiator = factory.SubFactory(UserFactory)
    target = factory.SubFactory(UserFactory)
    round_occurred = factory.SubFactory(RoundFactory)
    is_permanent = False


class InviteFactory(DjangoModelFactory):
    class Meta:
        model = Invite

    inviter = factory.SubFactory(UserFactory)
    invitee = factory.SubFactory(UserFactory)
    invite_type = "platform"
    status = "sent"


class JoinRequestFactory(DjangoModelFactory):
    class Meta:
        model = JoinRequest

    discussion = factory.SubFactory(DiscussionFactory)
    requester = factory.SubFactory(UserFactory)
    approver = factory.SubFactory(UserFactory)
    status = "pending"


class ResponseEditFactory(DjangoModelFactory):
    class Meta:
        model = ResponseEdit

    response = factory.SubFactory(ResponseFactory)
    edit_number = 1
    previous_content = factory.Faker("paragraph")
    new_content = factory.Faker("paragraph")
    characters_changed = 50


class DraftResponseFactory(DjangoModelFactory):
    class Meta:
        model = DraftResponse

    discussion = factory.SubFactory(DiscussionFactory)
    round = factory.SubFactory(RoundFactory)
    user = factory.SubFactory(UserFactory)
    content = factory.Faker("paragraph")
    saved_reason = "user_saved"


class NotificationPreferenceFactory(DjangoModelFactory):
    class Meta:
        model = NotificationPreference

    user = factory.SubFactory(UserFactory)
    notification_type = "new_response"
    enabled = True
    delivery_method = {"email": True, "push": True, "in_app": True}
