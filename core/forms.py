# voting/forms.py
import json
from typing import Optional

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django.forms import inlineformset_factory
from .models import CustomUser, Election, Candidate, Invitation, UserGroup


class SignUpForm(UserCreationForm):
    first_name = forms.CharField(max_length=30, required=True,
                                 widget=forms.TextInput(attrs={'placeholder': 'First Name'}))
    last_name = forms.CharField(max_length=30, required=True,
                                widget=forms.TextInput(attrs={'placeholder': 'Last Name'}))

    email = forms.EmailField(required=True)
    role = forms.ChoiceField(choices=CustomUser._meta.get_field('role').choices, required=True)
    gender = forms.ChoiceField(choices=CustomUser.GENDER_CHOICES, required=True)
    age_group = forms.ChoiceField(choices=CustomUser.AGE_GROUPS, required=True)

    # We will set choices for these fields dynamically later
    country = forms.ChoiceField(choices=[], required=True)

    # region = forms.ChoiceField(choices=[], required=False)

    class Meta:
        model = CustomUser
        fields = ['username', "first_name", "last_name", 'email', 'password1', 'password2', 'role', 'gender',
                  'age_group', 'country']

    def __init__(self, *args, **kwargs):
        super(SignUpForm, self).__init__(*args, **kwargs)

        # Load countries dynamically from a JSON file
        countries_data = []
        with open("core/static/core/data/countries+states.json", "r", encoding="utf-8") as f:
            countries_data = json.load(f)

        # Populate the 'country' dropdown with country names
        self.fields['country'].choices = [(country_data['name'], country_data['name'])
                                          for country_data in countries_data]

        # If the country is pre-selected, load regions for that country
        if 'country' in kwargs.get('data', {}):
            selected_country = kwargs['data']['country']
            for country_data in countries_data:
                if country_data['name'] == selected_country:
                    self.fields['region'].choices = [(region, region) for region in country_data['states']]
                    break


class ElectionForm(forms.ModelForm):
    # normal election fields …
    is_public = forms.BooleanField(required=False, initial=True, label="Public election")
    groups = forms.ModelMultipleChoiceField(
        queryset=UserGroup.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Invite groups (if private)",
    )
    max_choices = forms.IntegerField(min_value=1, initial=1, label="Max choices per voter",
                                     help_text="Πόσους υποψηφίους μπορεί να επιλέξει κάθε ψηφοφόρος")
    password = forms.CharField(
        required=False,
        widget=forms.PasswordInput,
        help_text="Leave blank and tick auto-generate to get a random one.",
    )

    # extra controls for the workflow
    auto_password = forms.BooleanField(
        required=False,
        initial=False,
        label="Generate a random password",
    )
    send_emails = forms.BooleanField(
        required=False,
        initial=True,
        label="Send invitation e-mails immediately",
    )

    class Meta:
        model = Election
        fields = [
            "title", "description",
            "start_date", "end_date",
            "is_active", "is_public",
            "password", "auto_password",
            "groups", "send_emails", "max_choices",
        ]

    # guard: private election must have *some* password
    def clean(self):
        cleaned = super().clean()

        start = cleaned.get("start_date")
        end = cleaned.get("end_date")
        password = cleaned.get("password")
        auto_pass = cleaned.get("auto_password")
        is_public = cleaned.get("is_public")
        candidates = self.instance.candidates.count()
        max_choices = cleaned.get("max_choices")

        if start and end and start >= end:
            raise forms.ValidationError("Η ημερομηνία λήξης πρέπει να είναι μετά την ημερομηνία έναρξης.")

        if not is_public and not (password or auto_pass):
            raise forms.ValidationError(
                "Οι ιδιωτικές εκλογές πρέπει να έχουν κωδικό ή να ζητείται αυτόματη δημιουργία.")

        if max_choices and candidates and max_choices > candidates:
            raise forms.ValidationError(
                f"Το πλήθος επιλογών δεν μπορεί να ξεπερνά τους διαθέσιμους υποψηφίους ({candidates}).")

        return cleaned


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
        model = User
        fields = ['first_name', 'last_name', 'email']  # adjust fields as you want editable
        widgets = {
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
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
