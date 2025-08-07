import uuid
from django.conf import settings
from django.contrib.auth.models import AbstractUser, Permission, Group as DjangoGroup
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from hashlib import sha256
from django.urls import reverse


# Custom user model
class CustomUser(AbstractUser):
    GENDER_CHOICES = [
        ('Male', 'Male'),
        ('Female', 'Female'),
        ('Prefer not to say', 'Prefer not to say'),
        ('Unknown', 'Unknown'),
    ]

    AGE_GROUPS = [
        ('18-25', '18-25'),
        ('26-35', '26-35'),
        ('36-45', '36-45'),
        ('46-60', '46-60'),
        ('60+', '60+'),
        ('Unknown', 'Unknown'),
    ]

    role = models.CharField(
        max_length=20,
        choices=[('Admin', 'Admin'), ('Voter', 'Voter')],
        default='Voter'
    )

    gender = models.CharField(
        max_length=20,
        choices=GENDER_CHOICES,
        default='Unknown'
    )

    age_group = models.CharField(
        max_length=10, choices=AGE_GROUPS, default='Unknown'
    )

    country = models.CharField(max_length=100, default='Unknown')
    region = models.CharField(max_length=100, null=True, blank=True)

    groups = models.ManyToManyField(
        DjangoGroup,
        related_name='customuser_set',
        blank=True
    )

    user_permissions = models.ManyToManyField(
        Permission,
        related_name='customuser_set',
        blank=True
    )


# Custom group model (renamed to avoid conflict with Django's Group)
class UserGroup(models.Model):
    name = models.CharField(max_length=255, unique=True)
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='user_groups',
        related_query_name='user_group'
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="elections_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Election(models.Model):
    VISIBILITY_CHOICES = [
        ('public', 'Δημόσια Εκλογή'),
        ('private', 'Ιδιωτική Εκλογή'),
    ]

    title = models.CharField(max_length=255, verbose_name="Τίτλος")
    description = models.TextField(verbose_name="Περιγραφή")
    start_date = models.DateTimeField(verbose_name="Ημερομηνία Έναρξης")
    end_date = models.DateTimeField(verbose_name="Ημερομηνία Λήξης")
    is_active = models.BooleanField(default=False, verbose_name="Ενεργή")
    active_from = models.DateTimeField(null=True, blank=True, verbose_name="Έγινε Ενεργή Από")
    total_voters = models.IntegerField(default=0, verbose_name="Σύνολο Ψηφοφόρων")

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        verbose_name="Δημιουργός"
    )

    visibility = models.CharField(
        max_length=20,
        choices=VISIBILITY_CHOICES,
        default='public',
        verbose_name="Ορατότητα Εκλογής"
    )

    password = models.CharField(
        max_length=128,
        blank=True,
        null=True,
        verbose_name="Κωδικός Πρόσβασης (αν απαιτείται)"
    )

    groups = models.ManyToManyField(
        UserGroup,
        blank=True,
        related_name="elections",
        verbose_name="Ομάδες Ψηφοφόρων"
    )

    max_choices = models.PositiveSmallIntegerField(
        default=1,
        help_text="Πόσες επιλογές επιτρέπονται σε κάθε ψηφοφόρο",
        verbose_name="Μέγιστες Επιλογές Ανά Ψηφοφόρο"
    )

    def calculate_total_voters(self):
        return self.vote_set.values('user').distinct().count()

    def __str__(self):
        return self.title


class Candidate(models.Model):
    name = models.CharField(max_length=255)
    election = models.ForeignKey(
        Election,
        on_delete=models.CASCADE,
        related_name='candidates'
    )


class DemographicGroup(models.Model):
    age_group = models.CharField(max_length=20)
    gender = models.CharField(max_length=10)
    country = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.age_group} - {self.gender} - {self.country}"


class Vote(models.Model):
    election = models.ForeignKey(Election, on_delete=models.CASCADE)
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE)
    demographic_group = models.ForeignKey(DemographicGroup, on_delete=models.SET_NULL, null=True)
    receipt_hash = models.CharField(max_length=64, unique=True, editable=False)
    timestamp = models.DateTimeField(auto_now_add=True)


class Invitation(models.Model):
    election = models.ForeignKey(Election, on_delete=models.CASCADE, related_name='invitations')
    code = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    email = models.EmailField(null=True, blank=True)
    used = models.BooleanField(default=False)
    used_by = models.ForeignKey(settings.AUTH_USER_MODEL,
                                null=True,
                                blank=True,
                                on_delete=models.SET_NULL,
                                related_name='invitations'
                                )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    def link(self, request=None) -> str:
        """Return absolute URL for this invitation."""
        path = reverse("invitation_redeem", args=[self.code])
        if request:  # called from a view/admin – produce full URL
            return request.build_absolute_uri(path)
        return path

    def is_valid(self):
        # Αν είναι προσωποποιημένο και έχει χρησιμοποιηθεί -> άκυρο
        if self.email and self.used:
            return False
        if self.expires_at and timezone.now() > self.expires_at:
            return False
        return True


class VoterLog(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='voter_logs')
    election = models.ForeignKey(Election, on_delete=models.CASCADE, related_name='voter_logs')
    has_voted = models.BooleanField(default=False)

    class Meta:
        unique_together = ('user', 'election')  # Ensure user votes once per election

    def __str__(self):
        return f"VoterLog #{self.id} – {self.user.username}/{self.election.title}"
