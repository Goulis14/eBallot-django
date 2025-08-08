# core/tests/test_vote_flow.py
import os, re
import pytest
from datetime import timedelta
from django.utils import timezone
from django.contrib.auth import get_user_model
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ---------- μικρά helpers ----------
def wait_body(driver, timeout=10):
    WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.TAG_NAME, "body")))

def first_or_none(driver, by, sel):
    els = driver.find_elements(by, sel)
    return els[0] if els else None

@pytest.fixture
def browser():
    options = Options()
    if os.getenv("HEADLESS", "1") != "0":
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    driver = webdriver.Chrome(options=options)  # Selenium Manager (δεν χρειάζεται webdriver_manager)
    driver.set_window_size(1400, 1000)
    yield driver
    driver.quit()

# ---------- το E2E test ----------
@pytest.mark.django_db
def test_vote_flow(live_server, browser):
    # 1) Φτιάχνω χρήστη σύμφωνα με το custom user model
    UserModel = get_user_model()
    username_field = UserModel.USERNAME_FIELD  # 'username' ή 'email'
    login_value = "testuser" if username_field == "username" else "test@example.com"
    user = UserModel.objects.create_user(**{username_field: login_value}, password="testpass")

    # 2) Κάνω login
    browser.get(live_server.url + "/login/")
    wait_body(browser)

    # Στόχευση συγκεκριμένου form login (αν δεν πιάσει, παίρνει το πρώτο form)
    form = first_or_none(browser, By.CSS_SELECTOR, "form[action*='/login/'], form[action$='login/'], form[action='/login/']") \
           or browser.find_element(By.TAG_NAME, "form")

    username_input = form.find_element(By.NAME, username_field)
    password_input = form.find_element(By.NAME, "password")

    username_input.clear(); username_input.send_keys(login_value)
    password_input.clear(); password_input.send_keys("testpass")
    password_input.send_keys(Keys.RETURN)

    wait_body(browser)
    if "Σύνδεση" in browser.page_source:
        submit_btn = first_or_none(form, By.CSS_SELECTOR, "button[type='submit'], input[type='submit']")
        if submit_btn:
            browser.execute_script("arguments[0].scrollIntoView({block:'center'});", submit_btn)
            try:
                submit_btn.click()
            except Exception:
                browser.execute_script("arguments[0].click();", submit_btn)
        wait_body(browser)
    assert "Σύνδεση" not in browser.page_source, "Φαίνεται ότι δεν έγινε login."

    # 3) Δημιουργώ ΜΟΝΟ με ORM μία δημόσια, ενεργή εκλογή + έναν υποψήφιο
    #    (με βάση τα μοντέλα που μου έστειλες)
    from core.models import Election, Candidate
    e = Election.objects.create(
        title="Δοκιμαστική Εκλογή E2E",
        description="Auto-created by Selenium test",
        start_date=timezone.now() - timedelta(days=1),
        end_date=timezone.now() + timedelta(days=1),
        is_active=True,                # να είναι ενεργή
        created_by=user,               # required FK
        visibility="public",           # δημόσια (όχι invite/password)
        max_choices=1,
    )
    Candidate.objects.create(election=e, name="Alice")

    # 4) Πηγαίνω κατευθείαν στη σελίδα ψηφοφορίας της εκλογής
    browser.get(live_server.url + f"/elections/{e.id}/vote/")
    wait_body(browser)

    # 5) Επιλέγω έναν υποψήφιο & κάνω submit
    # Περίμενε το form
    vote_form = WebDriverWait(browser, 10).until(
        EC.presence_of_element_located((By.TAG_NAME, "form"))
    )

    # Προσπάθησε με διάφορους selectors (radio ή checkbox, candidates ή candidate)
    candidate_input = first_or_none(browser, By.CSS_SELECTOR, "input[type='radio'][name='candidates']")
    if not candidate_input:
        candidate_input = first_or_none(browser, By.CSS_SELECTOR, "input[type='checkbox'][name='candidates']")
    if not candidate_input:
        candidate_input = first_or_none(browser, By.CSS_SELECTOR, "input[type='radio'][name='candidate']")
    if not candidate_input:
        candidate_input = first_or_none(browser, By.CSS_SELECTOR, "input[type='checkbox'][name='candidate']")
    if not candidate_input:
        # Τελευταίο fallback: πάρε το πρώτο enabled radio/checkbox στο form
        inputs = vote_form.find_elements(By.CSS_SELECTOR, "input[type='radio'], input[type='checkbox']")
        inputs = [el for el in inputs if el.is_enabled() and el.is_displayed()]
        candidate_input = inputs[0] if inputs else None

    assert candidate_input is not None, "Δεν βρήκα κανένα radio/checkbox υποψηφίου στο vote form."

    browser.execute_script("arguments[0].scrollIntoView({block:'center'});", candidate_input)
    candidate_input.click()

    # Submit (id=vote-submit αν έβαλες, αλλιώς generic)
    submit_vote = first_or_none(browser, By.ID, "vote-submit") \
                  or first_or_none(browser, By.CSS_SELECTOR, "button[type='submit'], input[type='submit']")
    assert submit_vote is not None, "Δεν βρήκα κουμπί υποβολής ψήφου."

    browser.execute_script("arguments[0].scrollIntoView({block:'center'});", submit_vote)
    try:
        submit_vote.click()
    except Exception:
        browser.execute_script("arguments[0].click();", submit_vote)

    wait_body(browser)

    # 6) Επιβεβαίωση επιτυχίας (αποδείξεις/αποτελέσματα/redirect)
    page = browser.page_source
    success_indicators = [
        "Οι αποδείξεις της ψήφου σου",
        "Αποτελέσματα:",
    ]
    in_results_url = re.search(r"/elections/\d+/results/?$", browser.current_url) is not None
    assert any(ind in page for ind in success_indicators) or in_results_url, (
        "Δεν βρέθηκε σαφής ένδειξη επιτυχούς ψήφου "
        "(ούτε 'Οι αποδείξεις της ψήφου σου', ούτε 'Αποτελέσματα:', ούτε redirect σε /results/)."
    )
