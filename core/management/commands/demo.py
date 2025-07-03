from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.utils import timezone
from faker import Faker
import random

from core.models import (
    Election,
    Candidate,
    DemographicGroup,
    VoterLog,
    Vote,
)
from core.utils import generate_vote_receipt

fake = Faker()
User = get_user_model()


class Command(BaseCommand):
    help = "Σπέρνει demo δεδομένα: n χρήστες, m εκλογές, υποψήφιους, ψήφους + superuser."

    def add_arguments(self, parser):
        parser.add_argument("--users", type=int, default=120, help="Πλήθος demo χρηστών (default 120)")
        parser.add_argument("--elections", type=int, default=3, help="Πλήθος δημοσίων εκλογών (default 3)")
        parser.add_argument("--candidates", type=int, default=6, help="Υποψήφιοι ανά εκλογή (default 6)")

    # ------------------------------------------------------------------ #
    # helper: superuser
    # ------------------------------------------------------------------ #
    def _ensure_superuser(self):
        username = "thanos"
        password = "paok1234!"
        if not User.objects.filter(username=username).exists():
            User.objects.create_superuser(
                username=username,
                email="thanos@example.com",
                password=password,
                first_name="Thanos",
                last_name="Demo",
            )
            self.stdout.write(self.style.SUCCESS(f"✓ Superuser '{username}' ➜ pw: {password}"))
        else:
            self.stdout.write(self.style.WARNING(f"• Superuser '{username}' ήδη υπάρχει – δεν τον άγγιξα."))

    # ------------------------------------------------------------------ #
    # main
    # ------------------------------------------------------------------ #
    def handle(self, *args, **opts):
        num_users = opts["users"]
        num_elections = opts["elections"]
        cands_per_election = opts["candidates"]

        # 0. superuser
        self._ensure_superuser()

        # 1. Χρήστες
        self.stdout.write(self.style.NOTICE(f"→ Δημιουργώ {num_users} demo χρήστες…"))
        users = []
        for i in range(num_users):
            u = User.objects.create(
                username=f"user{i}",
                first_name=fake.first_name(),
                last_name=fake.last_name(),
                email=fake.email(),
                password=make_password("demo1234!"),
                gender=random.choice([g for g, _ in User.GENDER_CHOICES]),
                age_group=random.choice([a for a, _ in User.AGE_GROUPS]),
                country=fake.country(),
            )
            users.append(u)

        # 2. Εκλογές
        self.stdout.write(self.style.NOTICE(f"→ Δημιουργώ {num_elections} εκλογές…"))
        elections = []
        now = timezone.now()
        for i in range(num_elections):
            e = Election.objects.create(
                title=f"Demo Election #{i+1}",
                description="Αυτοπαραγόμενο seed",
                start_date=now,
                end_date=now + timezone.timedelta(days=1),
                is_active=True,
                is_public=True,
                max_choices=random.choice([1, 2, 3]),
                created_by=users[0],
            )
            elections.append(e)

            # Υποψήφιοι
            for _ in range(cands_per_election):
                Candidate.objects.create(name=fake.name(), election=e)

        # 3. Κάθε χρήστης ψηφίζει τυχαία σε κάθε εκλογή
        self.stdout.write(self.style.NOTICE("→ Ψηφοφορία…"))
        total_votes = 0
        for e in elections:
            cands = list(e.candidates.all())
            for user in users:
                demo, _ = DemographicGroup.objects.get_or_create(
                    age_group=user.age_group,
                    gender=user.gender,
                    country=user.country,
                )
                log, _ = VoterLog.objects.get_or_create(user=user, election=e)
                if log.has_voted:
                    continue

                # ο χρήστης επιλέγει 1-max_choices τυχαίους υποψηφίους
                k = random.randint(1, e.max_choices)
                chosen = random.sample(cands, k=k)

                for cand in chosen:
                    salt, rhash = generate_vote_receipt(cand.id, e.id)
                    Vote.objects.create(
                        election=e,
                        candidate=cand,
                        demographic_group=demo,
                        receipt_hash=rhash,
                    )
                    total_votes += 1

                log.has_voted = True
                log.save(update_fields=["has_voted"])

        # 4. Σύνοψη
        self.stdout.write(self.style.SUCCESS(
            f"✓ Έτοιμο! Δημιουργήθηκαν {num_users} χρήστες, "
            f"{num_elections} εκλογές, {total_votes} ψήφοι."
        ))
