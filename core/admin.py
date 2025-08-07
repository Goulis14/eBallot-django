from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.admin import SimpleListFilter
from django.utils.html import format_html, format_html_join
from django.urls import reverse

from .models import Election, Candidate, Invitation, UserGroup
from .forms import ElectionForm

# ──────────────────────────────────────────────
#  Custom user model
# ──────────────────────────────────────────────
CustomUser = get_user_model()

try:
    admin.site.unregister(CustomUser)
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
        "title", "start_date", "end_date", "visibility",  "max_choices", "turnout_status"
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

    def invitation_links(self, obj):
        if not obj.pk:
            return "Αποθήκευσε πρώτα την εκλογή για να δεις τις προσκλήσεις."
        invs = obj.invitations.all()
        if not invs:
            return "Δεν υπάρχουν προσκλήσεις ακόμα."
        html = format_html_join(
            "\n",
            "<li><a href='{}' target='_blank'>{}</a></li>",
            ((inv.link(self.request), inv.link(self.request)) for inv in invs),
        )
        return format_html("<ul>{}</ul>", html)

    invitation_links.short_description = "Invitation links"

    def turnout_status(self, obj):
        voters = obj.voter_logs.count()
        voted = obj.voter_logs.filter(has_voted=True).count()
        return f"{voted}/{voters} ({(voted / voters) * 100:.1f}%)" if voters else "—"

    turnout_status.short_description = "Συμμετοχή"

    def generated_password_display(self, obj):
        if obj.visibility == "public":
            return "—"
        if obj.password:
            return obj.password
        return "Δεν έχει οριστεί"

    generated_password_display.short_description = "Ορισμένος Κωδικός"

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
