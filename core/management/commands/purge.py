from django.core.management.base import BaseCommand
from core.models import Vote, VoterLog, Candidate, Election
from django.contrib.auth import get_user_model

User = get_user_model()

class Command(BaseCommand):
    help = "Σβήνει όλα τα demo δεδομένα που δημιουργήθηκαν από seed_test_election"

    def handle(self, *args, **opts):
        demo_elections = Election.objects.filter(title__icontains="Demo Public Election")
        votes_deleted      = Vote.objects.filter(election__in=demo_elections).delete()
        voterlogs_deleted  = VoterLog.objects.filter(election__in=demo_elections).delete()
        candidates_deleted = Candidate.objects.filter(election__in=demo_elections).delete()
        elections_deleted  = demo_elections.delete()
        users_deleted      = User.objects.filter(username__startswith="user").delete()

        self.stdout.write(self.style.SUCCESS(
            f"Purged demo data:\n"
            f"  Votes:      {votes_deleted[0]}\n"
            f"  VoterLogs:  {voterlogs_deleted[0]}\n"
            f"  Candidates: {candidates_deleted[0]}\n"
            f"  Elections:  {elections_deleted[0]}\n"
            f"  Users:      {users_deleted[0]}"
        ))
