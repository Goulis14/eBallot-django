# core/signals.py

from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Election, Invitation


@receiver(post_save, sender=Election)
def create_invitation_no_email(sender, instance, created, **kwargs):
    if created and instance.visibility != 'public' and instance.invitations.count() == 0:
        Invitation.objects.create(election=instance)