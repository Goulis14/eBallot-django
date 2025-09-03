from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.admin import SimpleListFilter
from django.utils.html import format_html, format_html_join
from django.urls import reverse
from django.core.mail import EmailMessage
from django.contrib import messages

from .models import Election, Candidate, Invitation, UserGroup
from .forms import ElectionForm

# ──────────────────────────────────────────────
#  Custom user model
# ──────────────────────────────────────────────
CustomUser = get_user_model()

# Ασφαλές unregister για reloads
try:
    admin.site.unregister(CustomUser)
except admin.sites.NotRegistered:
    pass

try:
    admin.site.unregister(Election)
except admin.sites.NotRegistered:
    pass

# ──────────────────────────────────────────────
#  Inlines
# ──────────────────────────────────────────────
class InvitationInline(admin.TabularInline):
    model = Invitation
    extra = 1
    fields = ("email", "expires_at", "used")
    readonly_fields = ("used",)

class CandidateInline(admin.TabularInline):
    model = Candidate
    extra = 1

# ──────────────────────────────────────────────
#  Election Admin
# ──────────────────────────────────────────────
@admin.register(Election)
class ElectionAdmin(admin.ModelAdmin):
    form = ElectionForm
    inlines = [CandidateInline, InvitationInline]
    list_display = (
        "title", "start_date", "end_date", "visibility", "max_choices", "turnout_status"
    )
    list_filter = ("visibility",)
    search_fields = ("title", "description")
    readonly_fields = ("invitation_links", "generated_password_display")

    fieldsets = (
        ("Βασικές Πληροφορίες", {
            "fields": ("title", "description", "start_date", "end_date")
        }),
        ("Ρυθμίσεις Ορατότητας και Ασφάλειας", {
            "fields": ("visibility", "password", "groups")
        }),
        ("Ορισμένος Κωδικός Πρόσβασης", {
            "fields": ("generated_password_display",)
        }),
        ("Προσκλήσεις", {
            "fields": ("invitation_links",)
        }),
        ("Επιλογές Ψηφοφορίας", {
            "fields": ("max_choices",)
        }),
    )

    def get_queryset(self, request):
        # Χρειαζόμαστε το request για absolute URLs στο invitation_links
        self.request = request
        return super().get_queryset(request)

    def save_model(self, request, obj, form, change):
        if not change or obj.created_by_id is None:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

        # Δημιουργία shared invitation αν είναι private και δεν υπάρχει ήδη
        if obj.visibility == "private":
            existing_shared = obj.invitations.filter(email__isnull=True).first()
            if not existing_shared:
                Invitation.objects.create(election=obj)

    # ---------- Readonly helpers ----------
    def invitation_links(self, obj):
        """Εμφάνιση clickable invitation links στο admin."""
        if not obj.pk:
            return "Αποθήκευσε πρώτα την εκλογή για να δεις τις προσκλήσεις."
        invs = obj.invitations.all()
        if not invs:
            return "Δεν υπάρχουν προσκλήσεις ακόμα."

        req = getattr(self, "request", None)
        rows = []
        for inv in invs:
            url = inv.link(req) if req is not None else reverse("invitation_redeem", args=[inv.code])
            rows.append((url, url))

        return format_html(
            "<ul>{}</ul>",
            format_html_join("\n", "<li><a href='{}' target='_blank'>{}</a></li>", rows),
        )
    invitation_links.short_description = "Invitation links"

    def turnout_status(self, obj):
        """Σύντομη εικόνα συμμετοχής."""
        voters = obj.voter_logs.count()
        voted = obj.voter_logs.filter(has_voted=True).count()
        return f"{voted}/{voters} ({(voted / voters) * 100:.1f}%)" if voters else "—"
    turnout_status.short_description = "Συμμετοχή"

    def generated_password_display(self, obj):
        """Προβολή κωδικού για private εκλογές (αν υπάρχει)."""
        if obj.visibility == "public":
            return "—"
        if obj.password:
            return obj.password
        return "Δεν έχει οριστεί"
    generated_password_display.short_description = "Ορισμένος Κωδικός"

    # ---------- Αποστολή email προσκλήσεων από inline ----------
    def _send_invitation_email(self, request, inv: Invitation) -> bool:
        """Στέλνει email πρόσκλησης για μία εγγραφή Invitation."""
        if not inv.email or inv.used:
            return False
        try:
            invite_url = inv.link(request)  # absolute URL χάρη στο request
            subject = f"Πρόσκληση συμμετοχής στην εκλογή: {inv.election.title}"
            expires_txt = (
                inv.expires_at.strftime("%d/%m/%Y %H:%M")
                if getattr(inv, "expires_at", None) else "χωρίς λήξη"
            )
            body = (
                f"Σας καλούμε να συμμετάσχετε στην εκλογή «{inv.election.title}».\n\n"
                f"Σύνδεσμος πρόσκλησης: {invite_url}\n"
                f"Ισχύει μέχρι: {expires_txt}\n\n"
                f"Αν δεν αναγνωρίζετε αυτό το μήνυμα, μπορείτε να το αγνοήσετε."
            )
            msg = EmailMessage(subject=subject, body=body, to=[inv.email])
            sent = msg.send()  # επιστρέφει 1 αν στάλθηκε
            if sent:
                messages.success(request, f"Στάλθηκε πρόσκληση σε {inv.email}.")
                return True
            messages.error(request, f"Αποτυχία αποστολής σε {inv.email} (unknown).")
            return False
        except Exception as e:
            messages.error(request, f"Αποτυχία αποστολής σε {inv.email}: {e}")
            return False

    def save_formset(self, request, form, formset, change):
        """
        Όταν αποθηκεύονται τα Invitation inlines:
        - Στείλε email για νέες προσκλήσεις με email.
        - Στείλε email όταν αλλάξει το πεδίο email σε υπάρχουσα πρόσκληση.
        - Μην στέλνεις αν used=True ή email κενό.

        Σημαντικό: Καλούμε ΠΡΩΤΑ super().save_formset ώστε να δημιουργηθούν
        new_objects/changed_objects/deleted_objects που περιμένει το admin.
        """
        if formset.model is not Invitation:
            return super().save_formset(request, form, formset, change)

        # Προ-εντοπισμός ποια invitations χρειάζονται email πριν το save,
        # ώστε να ξέρουμε αν είναι νέες ή αν άλλαξε το email.
        to_send = []
        for f in formset.forms:
            if not hasattr(f, "cleaned_data"):
                continue
            if f.cleaned_data.get("DELETE", False):
                continue

            inst = f.instance  # ίδιο object που θα σωθεί από το super
            is_new = inst.pk is None
            email = f.cleaned_data.get("email")
            used_val = f.cleaned_data.get("used", getattr(inst, "used", False))
            email_changed = "email" in getattr(f, "changed_data", [])

            if email and not used_val and (is_new or email_changed):
                to_send.append(inst)

        # Σώσε κανονικά το formset (δημιουργεί new_objects/changed_objects/…)
        super().save_formset(request, form, formset, change)

        # Τώρα τα instances έχουν pk/code σίγουρα. Στείλε emails.
        for inv in to_send:
            self._send_invitation_email(request, inv)

# ──────────────────────────────────────────────
#  User ↔ Group Admin
# ──────────────────────────────────────────────
class UserGroupInline(admin.TabularInline):
    model = UserGroup.members.through
    extra = 0
    verbose_name = "Group membership"
    verbose_name_plural = "Groups"

class UserGroupListFilter(SimpleListFilter):
    title = "group"
    parameter_name = "group"

    def lookups(self, request, model_admin):
        return [(g.id, g.name) for g in UserGroup.objects.all()]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(groups__id=self.value())
        return queryset

@admin.register(CustomUser)
class CustomUserAdmin(BaseUserAdmin):
    inlines = [UserGroupInline]
    list_filter = BaseUserAdmin.list_filter + (UserGroupListFilter,)

@admin.register(UserGroup)
class UserGroupAdmin(admin.ModelAdmin):
    list_display = ("name", "member_count", "created_at", "created_by")
    search_fields = ("name",)
    filter_horizontal = ("members",)

    def member_count(self, obj):
        return obj.members.count()
    member_count.short_description = "Μέλη"
