# core/views.py
import json
from django.utils.translation import gettext_lazy as _
from collections import defaultdict
import logging
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.mixins import LoginRequiredMixin, AccessMixin
from django.core.mail import send_mail, EmailMessage
from django.core.serializers.json import DjangoJSONEncoder
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.http import HttpResponseForbidden, JsonResponse, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import ListView, View, FormView

from .forms import ContactForm, EditProfileForm, SignUpForm, VoteForm, CustomLoginForm
from .models import (
    DemographicGroup,
    Election,
    Invitation,
    VoterLog,
    Vote,
)
from .utils import generate_vote_receipt

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────
#  Basic static views
# ─────────────────────────────────────────────────────────


def index(request):
    return render(request, "core/index.html")


def about(request):
    return render(request, "core/about.html")


def services(request):
    return render(request, "core/services.html")


def team(request):
    return render(request, "core/team.html")


def portfolio(request):
    return render(request, "core/registration/profile.html")


# ─────────────────────────────────────────────────────────
#  Blog (placeholders)
# ─────────────────────────────────────────────────────────


def blog_list(request):
    return render(request, "core/election_list.html")


def blog_detail(request, post_id):
    return render(request, "core/vote.html", {"post_id": post_id})


# ─────────────────────────────────────────────────────────
#  Auth
# ─────────────────────────────────────────────────────────


def signup_view(request):
    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.role = "voter"
            user.save()
            login(request, user)

            # redeem invitation if present
            code = request.session.pop("invitation_code", None)
            if code:
                try:
                    inv = Invitation.objects.get(code=code, used=False)
                    inv.used = True
                    inv.used_by = user
                    inv.save()
                    messages.success(request, "Invitation redeemed.")
                except Invitation.DoesNotExist:
                    messages.warning(request, "Invitation invalid or used.")

            return redirect("home")
    else:
        form = SignUpForm()
    return render(request, "core/registration/signup.html", {"form": form})


def login_view(request):
    if request.method == "POST":
        form = CustomLoginForm(request, data=request.POST)
        if form.is_valid():
            login(request, form.get_user())
            return redirect("home")
        messages.error(request, "Λανθασμένα στοιχεία σύνδεσης.")
    else:
        form = CustomLoginForm()
    return render(request, "core/registration/login.html", {"form": form})


def logout_view(request):
    logout(request)
    return redirect("login")


# ─────────────────────────────────────────────────────────
#  Election list
# ─────────────────────────────────────────────────────────


class ElectionListView(ListView):
    model = Election
    template_name = "core/election_list.html"
    context_object_name = "elections"

    def get_queryset(self):
        user = self.request.user
        now = timezone.now()

        public_qs = Election.objects.filter(
            visibility="public",
            is_active=True,
            start_date__lte=now,
            end_date__gte=now
        )

        if user.is_authenticated:
            private_qs = Election.objects.filter(
                visibility="private",
                is_active=True,
                start_date__lte=now,
                end_date__gte=now
            ).filter(
                Q(groups__members=user) |
                Q(invitations__used_by=user, invitations__used=True)
            )
            return (public_qs | private_qs).distinct().order_by("-start_date")

        return public_qs.order_by("-start_date")

# ─────────────────────────────────────────────────────────
#  Alert mix-in
# ─────────────────────────────────────────────────────────


class AlertLoginRequiredMixin(AccessMixin):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.warning(request, "Please log in to vote.")
            return redirect("login")
        return super().dispatch(request, *args, **kwargs)


# ─────────────────────────────────────────────────────────
#  Vote View
# ─────────────────────────────────────────────────────────


class VoteView(LoginRequiredMixin, View):
    def get(self, request, pk):
        election = get_object_or_404(Election, pk=pk)

        # ----- Έλεγχος ορατότητας -----
        if election.visibility == "private":
            in_group = election.groups.filter(members=request.user).exists()
            invited = Invitation.objects.filter(
                election=election, used_by=request.user, used=True
            ).exists()

            if not in_group and not invited:
                raise Http404("Η εκλογή δεν υπάρχει.")  # 👈 Εξαφάνιση, όχι μήνυμα

            if election.password and not request.session.get(f"election_passed_{pk}"):
                return redirect("election_password", pk=pk)

        now = timezone.now()
        if now < election.start_date or now > election.end_date:
            messages.warning(request, "Η εκλογή δεν είναι ενεργή.")
            return redirect("election_list")

        if VoterLog.objects.filter(user=request.user, election=election, has_voted=True).exists():
            messages.info(request, "Έχετε ήδη ψηφίσει.")
            return redirect("results", election_id=election.pk)

        # ----- Φόρμα -----
        q = request.GET.get("q", "")
        candidates = (
            election.candidates.filter(name__icontains=q) if q else election.candidates.all()
        )
        form = VoteForm(election=election)
        ctx = {
            "election": election,
            "form": form,
            "candidates": candidates,
            "query": q,
        }
        return render(request, "core/vote.html", ctx)

    def post(self, request, pk):
        election = get_object_or_404(Election, pk=pk)
        form = VoteForm(request.POST, election=election)
        if not form.is_valid():
            messages.error(request, "Invalid vote.")
            return redirect("vote", pk=pk)

        try:
            with transaction.atomic():
                log, _ = VoterLog.objects.select_for_update().get_or_create(
                    user=request.user, election=election
                )
                if log.has_voted:
                    messages.error(request, "You have already voted.")
                    return redirect("results", election_id=pk)

                demo, _ = DemographicGroup.objects.get_or_create(
                    age_group=request.user.age_group,
                    gender=request.user.gender,
                    country=request.user.country,
                )

                salts = []
                for cand in form.cleaned_data["candidates"]:
                    salt, rhash = generate_vote_receipt(cand.id, election.id)
                    Vote.objects.create(
                        election=election,
                        candidate=cand,
                        demographic_group=demo,
                        receipt_hash=rhash,
                    )
                    salts.append(salt)

                log.has_voted = True
                log.save(update_fields=["has_voted"])
        except IntegrityError:
            messages.error(request, "DB error while voting.")
            return redirect("vote", pk=pk)

        # send receipts to session
        request.session["last_vote_salts"] = salts
        messages.success(request, "Vote recorded anonymously.")
        return redirect("results", election_id=pk)


# ─────────────────────────────────────────────────────────
#  Profile
# ─────────────────────────────────────────────────────────


@login_required
def profile(request):
    u = request.user
    ctx = {
        "user": u,
        "voter_logs": u.voter_logs.select_related("election"),
        "groups": u.user_groups.all(),
        "invitations": u.invitations.all(),
    }
    return render(request, "core/registration/profile.html", ctx)


# ─────────────────────────────────────────────────────────
#  Results view
# ─────────────────────────────────────────────────────────


GENDER_CATS = ["Male", "Female", "Prefer not to say", "Unknown"]
AGE_CATS = ["18-25", "26-35", "36-45", "46-60", "60+", "Unknown"]


def results(request, election_id):
    """Render the public results page with global + demographic charts."""
    election = get_object_or_404(Election, pk=election_id)
    total_votes = Vote.objects.filter(election=election).count()
    total_voters = VoterLog.objects.filter(election=election).count()

    # ── turnout summary ───────────────────────────────────
    if election.max_choices > 1:
        voters_voted = VoterLog.objects.filter(
            election=election, has_voted=True
        ).count()
        turnout_pct = round((voters_voted / total_voters) * 100, 2) if total_voters else 0
        turnout_text = {
            "label_1": "Total Voters Invited",
            "label_2": "Voters Who Voted",
            "label_3": "Turnout Percentage",
            "voters_voted": voters_voted,
        }
    else:
        turnout_pct = round((total_votes / total_voters) * 100, 2) if total_voters else 0
        turnout_text = {
            "label_1": "Total Voters",
            "label_2": "Votes Cast",
            "label_3": "Turnout Percentage",
            "voters_voted": total_votes,
        }

    # ── votes per candidate ───────────────────────────────
    cand_votes_qs = (
        Vote.objects.filter(election=election)
        .values("candidate__id", "candidate__name")
        .annotate(votes=Count("id"))
        .order_by("-votes")
    )
    results_list = [
        {
            "id": r["candidate__id"],
            "name": r["candidate__name"],
            "votes": r["votes"],
            "percentage": round((r["votes"] / total_votes) * 100, 2) if total_votes else 0,
        }
        for r in cand_votes_qs
    ]

    # ── demographic breakdown (overall + per-candidate) ──
    gender_counts = defaultdict(int)
    age_counts = defaultdict(int)
    gender_per_candidate = defaultdict(lambda: defaultdict(int))
    age_per_candidate = defaultdict(lambda: defaultdict(int))

    votes = Vote.objects.filter(election=election).select_related(
        "candidate", "demographic_group"
    )
    for v in votes:
        if not v.demographic_group:
            continue
        g = v.demographic_group.gender or "Unknown"
        a = v.demographic_group.age_group or "Unknown"
        c = v.candidate.name
        gender_counts[g] += 1
        age_counts[a] += 1
        gender_per_candidate[c][g] += 1
        age_per_candidate[c][a] += 1

    # Keep the overall label order tidy
    gender_labels = [g for g in GENDER_CATS if gender_counts[g] > 0]
    age_labels = [a for a in AGE_CATS if age_counts[a] > 0]

    ctx = {
        "election": election,
        "results": results_list,
        "total_votes": total_votes,
        "total_voters": total_voters,
        "turnout_percentage": turnout_pct,
        "turnout_text": turnout_text,
        "receipt_salts": request.session.pop("last_vote_salts", None),

        # ── JSON blobs (safe-escaped in template) ─────────
        "results_labels_json": [r["name"] for r in results_list],
        "results_votes_json": [r["votes"] for r in results_list],
        "gender_labels_json": gender_labels,
        "gender_counts_json": [gender_counts[g] for g in gender_labels],
        "age_labels_json": age_labels,
        "age_counts_json": [age_counts[a] for a in age_labels],
        "gender_per_candidate_json": gender_per_candidate,
        "age_per_candidate_json": age_per_candidate,
    }
    return render(request, "core/results.html", ctx)


# ─────────────────────────────────────────────────────────
#  Edit profile
# ─────────────────────────────────────────────────────────


@login_required
def edit_profile(request):
    if request.method == "POST":
        form = EditProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            return redirect("profile")
    else:
        form = EditProfileForm(instance=request.user)
    return render(request, "core/registration/edit_profile.html", {"form": form})


# ─────────────────────────────────────────────────────────
#  Invitation redeem
# ─────────────────────────────────────────────────────────


def invitation_redeem(request, code):
    inv = get_object_or_404(Invitation, code=code)
    if not inv.is_valid():
        messages.error(request, "Invitation expired or used.")
        return redirect("login")

    request.session["invitation_code"] = str(code)
    if request.user.is_authenticated:
        inv.used = True
        inv.used_by = request.user
        inv.save(update_fields=["used", "used_by"])
        return redirect("vote", pk=inv.election.pk)

    messages.info(request, "Please sign up or log in to vote.")
    return redirect("signup")


# ─────────────────────────────────────────────────────────
#  Password-protected election
# ─────────────────────────────────────────────────────────


def election_password(request, pk):
    election = get_object_or_404(Election, pk=pk)
    if election.visibility == "public":
        return redirect("vote", pk=pk)
    if not election.password:
        return HttpResponseForbidden("This election has no password.")

    if request.method == "POST":
        if request.POST.get("password", "").strip() == election.password.strip():
            request.session[f"election_passed_{pk}"] = True
            return redirect("vote", pk=pk)
        messages.error(request, "Wrong password.")
    return render(request, "core/election_password.html", {"election": election})


# ─────────────────────────────────────────────────────────
#  Public bulletin + verify
# ─────────────────────────────────────────────────────────


@login_required  # κάν' το public αν το θέλεις
def receipts_json(request, election_id):
    data = list(
        Vote.objects.filter(election_id=election_id).values("receipt_hash", "candidate_id")
    )
    return JsonResponse(data, safe=False)


def verify_receipt(request, election_id):
    if request.method == "POST":
        h = (request.POST.get("hash") or "").strip().lower()
        ok = Vote.objects.filter(election_id=election_id, receipt_hash=h).exists()
        return render(request, "core/verify.html", {"hash": h, "ok": ok})
    return render(request, "core/verify.html")


class ContactView(FormView):
    template_name = "core/contact.html"
    form_class = ContactForm
    success_url = reverse_lazy("contact")

    def form_valid(self, form):
        # ── Δημιουργία και αποστολή email ────────────────────────
        msg = EmailMessage(
            subject=form.cleaned_data["subject"],
            body=(
                f"Από: {form.cleaned_data['name']} "
                f"<{form.cleaned_data['email']}>\n\n"
                f"{form.cleaned_data['message']}"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,  # π.χ. t.goulianos@gmail.com
            to=[settings.CONTACT_EMAIL],  # ίδιο: t.goulianos@gmail.com
            reply_to=[form.cleaned_data["email"]],  # ο χρήστης ως reply-to
        )
        msg.send()

        # ── AJAX απάντηση ─────────────────────────────────────────
        if self.request.headers.get("x-requested-with") == "XMLHttpRequest":
            return HttpResponse("OK")

        # ── Κανονική υποβολή (redirect + flash message) ───────────
        messages.success(self.request, "Το μήνυμά σας στάλθηκε με επιτυχία!")
        return super().form_valid(form)
