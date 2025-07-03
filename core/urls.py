from django.urls import path
from . import views

urlpatterns = [
    path("", views.index, name="home"),

    # static pages
    path("about/", views.about, name="about"),
    path("services/", views.services, name="services"),
    path("contact/", views.ContactView.as_view(), name="contact"),
    path("team/", views.team, name="team"),

    # auth
    path("signup/", views.signup_view, name="signup"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("profile/", views.profile, name="profile"),
    path("profile/edit/", views.edit_profile, name="edit_profile"),
    path("api/receipts/<int:election_id>.json", views.receipts_json, name="receipts_json"),
    # invitations
    path("invite/<uuid:code>/", views.invitation_redeem, name="invitation_redeem"),
    path("verify/<int:election_id>/", views.verify_receipt, name="verify_receipt"),
    # ▸▸ the password step  ◂◂
    path(
        "elections/<int:pk>/password/",
        views.election_password,
        name="election_password",
    ),

    # elections
    path("elections/", views.ElectionListView.as_view(), name="election_list"),
    path("elections/<int:pk>/vote/", views.VoteView.as_view(), name="vote"),
    path(
        "elections/<int:election_id>/results/",
        views.results,
        name="results",
    ),
]
