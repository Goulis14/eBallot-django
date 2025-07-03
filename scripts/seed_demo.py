"""
Δημιουργεί demo χρήστες, ένα ιδιωτικό και ένα δημόσιο election,
ρίχνει τυχαίες ψήφους και τυπώνει τα στατιστικά.

Ασφαλές να το ξανατρέχεις: κάνει cleanup πριν γράψει οτιδήποτε.
"""

from core.models import (
    CustomUser,
    UserGroup,
    Election,
    Candidate,
    Vote,
    DemographicGroup,
    VoterLog,
)
from django.utils import timezone
from datetime import timedelta
from core.utils import generate_vote_hash
import random

# ---------------------------------------------------------
# 1) Καθαρισμός προηγούμενων demo δεδομένων
# ---------------------------------------------------------
Vote.objects.all().delete()
VoterLog.objects.all().delete()
Candidate.objects.filter(
    election__title__in=[
        "Εκλογές Προέδρου Φοιτητών",
        "Δημόσια Δοκιμαστική Ψηφοφορία",
    ]
).delete()
Election.objects.filter(
    title__in=[
        "Εκλογές Προέδρου Φοιτητών",
        "Δημόσια Δοκιμαστική Ψηφοφορία",
    ]
).delete()

# ---------------------------------------------------------
# 2) Δημιουργία χρηστών
# ---------------------------------------------------------
users_data = [
    {"username": "nikos", "gender": "Male", "age_group": "18-25"},
    {"username": "maria", "gender": "Female", "age_group": "26-35"},
    {"username": "giorgos", "gender": "Male", "age_group": "36-45"},
    {"username": "eva", "gender": "Female", "age_group": "18-25"},
]
users = []
for u in users_data:
    usr, _ = CustomUser.objects.get_or_create(
        username=u["username"],
        defaults={
            "email": f'{u["username"]}@demo.com',
            "gender": u["gender"],
            "age_group": u["age_group"],
            "country": "Greece",
            "role": "Voter",
        },
    )
    # ορίζω/επαναφέρω κωδικό κάθε φορά
    usr.set_password("test1234")
    usr.save(update_fields=["password"])
    users.append(usr)

print("✅ Χρήστες:", [u.username for u in users])

# ---------------------------------------------------------
# 3) Φοιτητικό group
# ---------------------------------------------------------
if users:
    group, _ = UserGroup.objects.get_or_create(
        name="Φοιτητές", defaults={"created_by": users[0]}
    )
    group.members.set(users)
else:
    raise RuntimeError("Δεν βρέθηκαν χρήστες – έλεγξε το users_data.")

# ---------------------------------------------------------
# 4) Ιδιωτική εκλογή
# ---------------------------------------------------------
start = timezone.now()
end = start + timedelta(days=1)

priv_elec, _ = Election.objects.get_or_create(
    title="Εκλογές Προέδρου Φοιτητών",
    defaults={
        "description": "Ιδιωτική εκλογή μόνο για Φοιτητές",
        "start_date": start,
        "end_date": end,
        "is_active": True,
        "is_public": False,
        "created_by": users[0],
        "total_voters": len(users),
    },
)
priv_elec.groups.set([group])

priv_candidates = [
    "Αντώνης Παπαδόπουλος",
    "Ελένη Καραγιάννη",
    "Σπύρος Δημητρίου",
]
priv_cand_objs = [
    Candidate.objects.get_or_create(name=name, election=priv_elec)[0]
    for name in priv_candidates
]

# ---------------------------------------------------------
# 5) Δημόσια εκλογή
# ---------------------------------------------------------
pub_elec, _ = Election.objects.get_or_create(
    title="Δημόσια Δοκιμαστική Ψηφοφορία",
    defaults={
        "description": "Όλοι μπορούν να ψηφίσουν",
        "start_date": start,
        "end_date": end,
        "is_active": True,
        "is_public": True,
        "created_by": users[0],
        "total_voters": 0,  # 0 → απεριόριστο κοινό
    },
)

pub_candidates = ["YES", "NO"]
pub_cand_objs = [
    Candidate.objects.get_or_create(name=name, election=pub_elec)[0]
    for name in pub_candidates
]

# ---------------------------------------------------------
# 6) Συνάρτηση ρίψης ψήφου
# ---------------------------------------------------------

def cast_vote(user, election, cand_objs):
    """Ρίχνει ψήφο αν δεν υπάρχει ήδη στο log."""
    vote_hash = generate_vote_hash(user.id, election.id)
    if Vote.objects.filter(vote_hash=vote_hash).exists():
        return False  # έχει ήδη ψηφίσει

    demo, _ = DemographicGroup.objects.get_or_create(
        age_group=user.age_group, gender=user.gender, country=user.country
    )

    Vote.objects.create(
        election=election,
        candidate=random.choice(cand_objs),
        demographic_group=demo,
        vote_hash=vote_hash,
    )
    VoterLog.objects.get_or_create(user=user, election=election)
    return True

# ---------------------------------------------------------
# 7) Ρίχνουμε τις ψήφους
# ---------------------------------------------------------
for user in users:
    cast_vote(user, priv_elec, priv_cand_objs)
    cast_vote(user, pub_elec, pub_cand_objs)

# ---------------------------------------------------------
# 8) Στατιστικά
# ---------------------------------------------------------
print(
    "🗳️  Ιδιωτική εκλογή - ψήφοι:",
    Vote.objects.filter(election=priv_elec).count(),
)
print(
    "🗳️  Δημόσια  εκλογή - ψήφοι:",
    Vote.objects.filter(election=pub_elec).count(),
)

print("✅ Script ολοκληρώθηκε.")
