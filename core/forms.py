# voting/forms.py
import json
from typing import Optional

from django.core.checks import messages
from django.utils.translation import gettext_lazy as _
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.forms import inlineformset_factory
from .models import CustomUser, Election, Candidate, Invitation, UserGroup
from django import forms



class SignUpForm(UserCreationForm):
    first_name = forms.CharField(
        max_length=30,
        required=True,
        label=_("Όνομα"),
        widget=forms.TextInput(attrs={'placeholder': 'Όνομα'})
    )
    last_name = forms.CharField(
        max_length=30,
        required=True,
        label=_("Επώνυμο"),
        widget=forms.TextInput(attrs={'placeholder': 'Επώνυμο'})
    )
    email = forms.EmailField(
        required=True,
        label=_("Email")
    )
    password1 = forms.CharField(
        label=_("Κωδικός πρόσβασης"),
        widget=forms.PasswordInput(attrs={'placeholder': 'Κωδικός πρόσβασης'})
    )
    password2 = forms.CharField(
        label=_("Επιβεβαίωση κωδικού"),
        widget=forms.PasswordInput(attrs={'placeholder': 'Επιβεβαίωση κωδικού'})
    )
    gender = forms.ChoiceField(
        choices=CustomUser.GENDER_CHOICES,
        required=True,
        label=_("Φύλο")
    )
    age_group = forms.ChoiceField(
        choices=CustomUser.AGE_GROUPS,
        required=True,
        label=_("Ηλικιακή ομάδα")
    )
    country = forms.ChoiceField(
        choices=[],
        required=True,
        label=_("Χώρα")
    )

    class Meta:
        model = CustomUser
        fields = [
            'username', 'first_name', 'last_name',
            'email', 'password1', 'password2',
            'gender', 'age_group', 'country'
        ]
        labels = {
            'username': _('Όνομα χρήστη'),
            'password1': _('Κωδικός πρόσβασης'),
            'password2': _('Επιβεβαίωση κωδικού πρόσβασης'),
        }

    def __init__(self, *args, **kwargs):
        super(SignUpForm, self).__init__(*args, **kwargs)

        # Load countries dynamically from a JSON file
        countries_data = []
        with open("core/static/core/data/countries+states.json", "r", encoding="utf-8") as f:
            countries_data = json.load(f)

        self.fields['country'].choices = [
            (country_data['name'], country_data['name'])
            for country_data in countries_data
        ]

        # If the country is pre-selected, load regions for that country
        if 'country' in kwargs.get('data', {}):
            selected_country = kwargs['data']['country']
            for country_data in countries_data:
                if country_data['name'] == selected_country:
                    self.fields['region'].choices = [
                        (region, region) for region in country_data['states']
                    ]
                    break




class ElectionForm(forms.ModelForm):
    visibility = forms.ChoiceField(
        choices=Election.VISIBILITY_CHOICES,
        label="Ορατότητα Εκλογής"
    )

    groups = forms.ModelMultipleChoiceField(
        queryset=UserGroup.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Ομάδες ψηφοφόρων (για ιδιωτικές εκλογές)",
    )

    password = forms.CharField(
        required=False,
        widget=forms.PasswordInput,
        help_text="Προαιρετικός κωδικός πρόσβασης για την εκλογή.",
        label="Κωδικός Πρόσβασης"
    )

    # send_emails = forms.BooleanField(
    #     required=False,
    #     initial=True,
    #     label="Αποστολή προσκλήσεων μέσω email",
    # )

    max_choices = forms.IntegerField(
        min_value=1,
        initial=1,
        label="Μέγιστες Επιλογές Ανά Ψηφοφόρο",
        help_text="Πόσους υποψηφίους μπορεί να επιλέξει κάθε ψηφοφόρος"
    )

    class Meta:
        model = Election
        fields = [
            "title", "description",
            "start_date", "end_date",
            "is_active", "visibility",
            "password", "groups",  "max_choices",
        ]

    def clean(self):
        cleaned_data = super().clean()

        visibility = cleaned_data.get("visibility")
        start = cleaned_data.get("start_date")
        end = cleaned_data.get("end_date")
        max_choices = cleaned_data.get("max_choices")

        # Έλεγχος ημερομηνιών
        if start and end and start >= end:
            raise forms.ValidationError("Η ημερομηνία λήξης πρέπει να είναι μετά την ημερομηνία έναρξης.")

        # Δεν απαιτούνται πλέον groups για private elections!

        # Έλεγχος μέγιστων επιλογών σε σχέση με τους υποψηφίους
        candidates = self.instance.candidates.count() if self.instance.pk else 0
        if max_choices and candidates and max_choices > candidates:
            raise forms.ValidationError(
                f"Το πλήθος επιλογών δεν μπορεί να ξεπερνά τους διαθέσιμους υποψηφίους ({candidates})."
            )

        return cleaned_data


class CandidateForm(forms.ModelForm):
    class Meta:
        model = Candidate
        fields = ['name']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Candidate Name'}),
        }


CandidateFormSet = inlineformset_factory(
    parent_model=Election,
    model=Candidate,
    form=CandidateForm,
    extra=2,  # Number of blank candidate fields to show initially
    can_delete=True
)


class InvitationForm(forms.ModelForm):
    class Meta:
        model = Invitation
        fields = ['email', 'expires_at']
        widgets = {
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Invitee email'}),
            'expires_at': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}),
        }


class VoteForm(forms.Form):
    candidates = forms.ModelMultipleChoiceField(
        queryset=Candidate.objects.none(),
        widget=forms.CheckboxSelectMultiple
    )

    def __init__(self, *args, **kwargs):
        election = kwargs.pop("election")
        super().__init__(*args, **kwargs)
        self.election = election
        self.fields["candidates"].queryset = election.candidates.all()
        self.fields["candidates"].label_from_instance = lambda obj: obj.name

    def clean_candidates(self):
        data = self.cleaned_data["candidates"]
        if not 1 <= len(data) <= self.election.max_choices:
            raise forms.ValidationError(
                f"Επιτρέπονται 1 έως {self.election.max_choices} επιλογές."
            )
        return data


User = get_user_model()


class EditProfileForm(forms.ModelForm):
    class Meta:
        model = CustomUser
        fields = [
            'username',
            'first_name',
            'last_name',
            'email',
            'gender',
            'age_group',

        ]
        labels = {
            'username': _('Όνομα χρήστη'),
            'first_name': _('Όνομα'),
            'last_name': _('Επώνυμο'),
            'email': _('Email'),
            'gender': _('Φύλο'),
            'age_group': _('Ηλικιακή ομάδα'),

        }
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'gender': forms.Select(attrs={'class': 'form-control'}),
            'age_group': forms.Select(attrs={'class': 'form-control'}),
        }


class ContactForm(forms.Form):
    name = forms.CharField(label="Όνομα", max_length=100)
    email = forms.EmailField(label="Email")
    subject = forms.CharField(label="Θέμα", max_length=150)
    message = forms.CharField(label="Μήνυμα", widget=forms.Textarea)


class GroupForm(forms.ModelForm):
    class Meta:
        model = UserGroup
        fields = ['name']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Group Name'}),
        }


class CustomLoginForm(AuthenticationForm):
    username = forms.CharField(
        label=_("Όνομα χρήστη"),
        widget=forms.TextInput(attrs={"autofocus": True, "class": "form-control", "placeholder": "Όνομα χρήστη"})
    )
    password = forms.CharField(
        label=_("Κωδικός πρόσβασης"),
        strip=False,
        widget=forms.PasswordInput(
            attrs={"autocomplete": "current-password", "class": "form-control", "placeholder": "Κωδικός πρόσβασης"}),
    )
