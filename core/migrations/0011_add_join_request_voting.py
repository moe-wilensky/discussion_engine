import uuid
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0010_update_invite_system'),
    ]

    operations = [
        # Add JoinRequestVote model
        migrations.CreateModel(
            name='JoinRequestVote',
            fields=[
                ('id', models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)),
                ('approve', models.BooleanField()),
                ('voted_at', models.DateTimeField(auto_now_add=True)),
                ('join_request', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='votes',
                    to='core.joinrequest'
                )),
                ('round', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='join_request_votes',
                    to='core.round'
                )),
                ('voter', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='join_request_votes_cast',
                    to='core.user'
                )),
            ],
            options={
                'db_table': 'join_request_votes',
            },
        ),

        # Add unique constraint
        migrations.AddConstraint(
            model_name='joinrequestvote',
            constraint=models.UniqueConstraint(
                fields=['round', 'voter', 'join_request'],
                name='unique_join_request_vote'
            ),
        ),

        # Add indexes for performance
        migrations.AddIndex(
            model_name='joinrequestvote',
            index=models.Index(
                fields=['round', 'join_request'],
                name='idx_jrv_round_request'
            ),
        ),
        migrations.AddIndex(
            model_name='joinrequestvote',
            index=models.Index(
                fields=['voter', 'voted_at'],
                name='idx_jrv_voter_time'
            ),
        ),

        # Add voting_credits_awarded to Round
        migrations.AddField(
            model_name='round',
            name='voting_credits_awarded',
            field=models.JSONField(default=list, blank=True),
        ),
    ]
