import hashlib
import secrets

from django.core.mail import send_mail
from django.urls import reverse

from core.models import CustomUser, Invitation
from eBallot import settings


def generate_vote_receipt(candidate_id: int, election_id: int):
    """
    Return (salt, receipt_hash) where receipt_hash = SHA256(salt:candidate_id:election_id).
    The salt is given back to the voter as proof; only the hash is stored.
    """
    salt = secrets.token_hex(16)
    to_hash = f"{salt}:{candidate_id}:{election_id}".encode()
    return salt, hashlib.sha256(to_hash).hexdigest()


# -----------------------------------------
def generate_vote_hash(user_id, election_id, salt="my_secret_salt"):
    raw = f"{user_id}_{election_id}_{salt}"
    return hashlib.sha256(raw.encode()).hexdigest()


def generate_password() -> str:
    """Return a random 12-char password suitable for an election."""
    return secrets.token_urlsafe(9)  # 12 ish printable chars


def create_group_invitations(election):
    """Create (or reuse) one Invitation per user in election.groups."""
    for user in CustomUser.objects.filter(user_group__in=election.groups.all()).distinct():
        Invitation.objects.get_or_create(
            election=election,
            email=user.email,
            defaults={"expires_at": election.end_date},
        )


def send_invitation_email(invitation, request=None):
    """
    Send an invitation link to invitation.email.
    If `request` is None we build the absolute URL using settings.SITE_URL.
    """
    from django.conf import settings

    if request:
        url = request.build_absolute_uri(
            reverse("invitation_redeem", args=[invitation.code])
        )
    else:
        # console / management-command path
        site_url = getattr(settings, "SITE_URL", "http://localhost:8000")
        url = f"{site_url}{reverse('invitation_redeem', args=[invitation.code])}"

    subject = "You’re invited to vote!"
    body = (
        f"Hello!\n\n"
        f"You’ve been invited to vote in “{invitation.election.title}”.\n"
        f"Click the link below to accept your invitation:\n\n{url}\n\n"
        f"The link expires on {invitation.expires_at:%d %b %Y %H:%M}."
    )

    send_mail(
        subject,
        body,
        settings.DEFAULT_FROM_EMAIL,
        [invitation.email],
        fail_silently=False,
    )
