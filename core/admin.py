# core/admin.py
from django.contrib import admin, messages
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.admin import SimpleListFilter
from django.utils import timezone
from django.utils.html import format_html, format_html_join
from django.urls import reverse

from .models import Election, Candidate, Invitation, UserGroup
from .forms import ElectionForm
from .utils import generate_password, create_group_invitations, send_invitation_email

# ──────────────────────────────────────────────
#  Custom user model (AUTH_USER_MODEL)
# ──────────────────────────────────────────────
CustomUser = get_user_model()

# Remove the default registration Django adds automatically
try:
    admin.site.unregister(CustomUser)
except admin.sites.NotRegistered:
    pass


# ──────────────────────────────────────────────
#  Election-related inlines & admin
# ──────────────────────────────────────────────
class InvitationInline(admin.TabularInline):
    model = Invitation
    extra = 1
    fields = ("email", "expires_at", "used")
    readonly_fields = ("used",)


class CandidateInline(admin.TabularInline):
    model = Candidate
    extra = 1


@admin.register(Election)
class ElectionAdmin(admin.ModelAdmin):
    form = ElectionForm
    inlines = [CandidateInline, InvitationInline]
    list_display = (
        "title", "start_date", "end_date",
        "is_public", "is_active", "max_choices",
        "turnout_status",  # NEW
    )
    list_filter = ("is_public", "is_active")
    search_fields = ("title", "description")
    readonly_fields = ("password", "invitation_links")

    # show generated invitation URLs
    def invitation_links(self, obj):
        invs = obj.invitations.all()
        if not invs:
            return "No invitations yet."
        html = format_html_join(
            "\n",
            "<li><a href='{}' target='_blank'>{}</a></li>",
            ((reverse("invitation_redeem", args=[inv.code]), inv.code) for inv in invs),
        )
        return format_html("<ul>{}</ul>", html)

    invitation_links.short_description = "Invitation links"

    # main save hook
    def save_model(self, request, obj, form, change):
        # 1️⃣ ensure NOT-NULL created_by
        if not change or obj.created_by_id is None:
            obj.created_by = request.user

        # 2️⃣ first save (creates the DB row so PK exists)
        super().save_model(request, obj, form, change)

        # 3️⃣ public elections need no invitations
        if obj.is_public:
            return

        # 4️⃣ generate password if requested and still empty
        if form.cleaned_data.get("auto_password") and not obj.password:
            obj.password = generate_password()
            obj.save(update_fields=["password"])

        # 5️⃣ create one Invitation per *group member*
        create_group_invitations(obj)

        # 6️⃣ send emails if requested
        if form.cleaned_data.get("send_emails"):
            for inv in obj.invitations.filter(used=False, email__isnull=False):
                send_invitation_email(inv, request)
            self.message_user(request, "Invitations saved and e-mails sent.", messages.SUCCESS)
        else:
            self.message_user(request, "Invitations saved (no e-mails).", messages.INFO)

    actions = ["toggle_active", "end_election_now"]

    @admin.action(description="Ενεργοποίηση / Απενεργοποίηση εκλογής")
    def toggle_active(self, request, queryset):
        updated = 0
        for election in queryset:
            election.is_active = not election.is_active
            election.save(update_fields=["is_active"])
            updated += 1
        self.message_user(request, f"Ενημερώθηκαν {updated} εκλογές.")

    @admin.action(description="Λήξη εκλογής τώρα")
    def end_election_now(self, request, queryset):
        now = timezone.now()
        for election in queryset:
            election.end_date = now
            election.is_active = False
            election.save(update_fields=["end_date", "is_active"])
        self.message_user(request, "Η εκλογή λήχθηκε με επιτυχία.")

    def turnout_status(self, obj):
        voters = obj.voter_logs.count()
        voted = obj.voter_logs.filter(has_voted=True).count()
        return f"{voted}/{voters} ({(voted / voters) * 100:.1f}%)" if voters else "—"

    turnout_status.short_description = "Συμμετοχή"


# ──────────────────────────────────────────────
#  User ↔ Group helpers
# ──────────────────────────────────────────────
class UserGroupInline(admin.TabularInline):
    model = UserGroup.members.through  # through table of the M2M
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


# ──────────────────────────────────────────────
#  Group screen itself
# ──────────────────────────────────────────────
@admin.register(UserGroup)
class UserGroupAdmin(admin.ModelAdmin):
    list_display = ("name", "created_by", "created_at", "member_count")
    search_fields = ("name",)
    filter_horizontal = ("members",)

    def member_count(self, obj):
        return obj.members.count()

    member_count.short_description = "Μέλη"
