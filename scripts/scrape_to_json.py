import json
import time
import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


BASE = "https://www-banner.aub.edu.lb/pls/weba/"
TERM_PAGE = urljoin(BASE, "bwckgens.p_proc_term_date")      # term picker + posts to itself
RESULTS_PAGE = urljoin(BASE, "bwckschd.p_get_crse_unsec")   # results endpoint (form action often points here)

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Content-Type": "application/x-www-form-urlencoded",
    "Origin": "https://www-banner.aub.edu.lb",
    "Referer": TERM_PAGE,
}


def get_terms(session: requests.Session):
    r = session.get(TERM_PAGE, headers=HEADERS, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    # term select is usually name="p_term"
    sel = soup.find("select", {"name": "p_term"})
    if not sel:
        raise RuntimeError("Could not find term dropdown (p_term).")

    terms = []
    for opt in sel.find_all("option"):
        code = (opt.get("value") or "").strip()
        label = opt.get_text(strip=True)
        if code:
            terms.append((code, label))
    return terms


def post_term_and_get_search_form(session: requests.Session, term_code: str):
    """
    Submit term so Banner returns the search form (subject, course number, etc).
    We then parse the <form> and return:
    - action_url: where to POST for results
    - base_fields: all inputs/select default values (except subject)
    - subjects: list of (subj_value, subj_label)
    """
    payload = {
        "p_term": term_code,
        "term_in": "Submit",
    }

    r = session.post(TERM_PAGE, data=payload, headers=HEADERS, timeout=30)
    r.raise_for_status()

    html = r.text
    soup = BeautifulSoup(html, "html.parser")

    # find the main search form (the one that contains Subject)
    subj_select = soup.find("select", {"name": re.compile(r"sel_subj", re.I)})
    if not subj_select:
        # save for debugging
        with open("debug_after_term.html", "w", encoding="utf-8") as f:
            f.write(html)
        raise RuntimeError(
            "Could not find Subject dropdown after submitting term. "
            "Saved debug_after_term.html (open it and confirm the select name)."
        )

    form = subj_select.find_parent("form")
    if not form:
        raise RuntimeError("Found Subject dropdown but could not find its parent <form>.")

    action = form.get("action") or RESULTS_PAGE
    action_url = action if action.startswith("http") else urljoin(BASE, action)

    # Extract ALL inputs in the form (hidden/text/etc)
    # Banner relies on many repeated fields like sel_day, sel_schd, etc.
    base_fields = []

    # inputs
    for inp in form.find_all("input"):
        name = inp.get("name")
        if not name:
            continue
        value = inp.get("value", "")
        t = (inp.get("type") or "").lower()

        # unchecked checkboxes should not be included; include only hidden/text/submit defaults
        if t == "checkbox":
            # include only if checked
            if inp.has_attr("checked"):
                base_fields.append((name, value))
        else:
            base_fields.append((name, value))

    # selects: include their selected option(s)
    for sel in form.find_all("select"):
        name = sel.get("name")
        if not name:
            continue

        # We'll skip subject here because we will set it per loop
        if name.lower() == "sel_subj":
            continue

        selected = sel.find_all("option", selected=True)
        if not selected:
            # if nothing explicitly selected, use first option
            first = sel.find("option")
            if first:
                base_fields.append((name, (first.get("value") or "").strip()))
        else:
            for opt in selected:
                base_fields.append((name, (opt.get("value") or "").strip()))

    # subjects list
    subjects = []
    for opt in subj_select.find_all("option"):
        v = (opt.get("value") or "").strip()
        label = opt.get_text(strip=True)

        # Banner often has "All" as '%' or empty — skip those
        if not v or v == "%":
            continue
        subjects.append((v, label))

    return action_url, base_fields, subjects


def fetch_subject_results_html(session: requests.Session, action_url: str, base_fields, subj_value: str):
    # Build POST fields:
    # 1) include base_fields exactly
    # 2) add subject
    fields = list(base_fields)

    # Banner sometimes expects sel_subj to exist even if single value:
    fields.append(("sel_subj", subj_value))

    r = session.post(action_url, data=fields, headers=HEADERS, timeout=60)

    # Don’t hard-fail immediately; sometimes you get a temporary 500
    if r.status_code >= 500:
        raise RuntimeError(f"Server error {r.status_code} on subject {subj_value}")

    r.raise_for_status()
    return r.text


def parse_courses_from_results(html: str):
    """
    Parse course titles from results page.
    Banner results usually include course headers in:
      <th class="ddtitle">CMPS 211 - Data Structures - 12345 - Section 1</th>
    We'll extract code and title.
    """
    soup = BeautifulSoup(html, "html.parser")
    courses = []

    for th in soup.select("th.ddtitle"):
        text = th.get_text(" ", strip=True)
        # Example: "CMPS 211 - Data Structures - 12345 - Section 1"
        parts = [p.strip() for p in text.split(" - ")]

        # We want at least: ["CMPS 211", "Data Structures", ...]
        if len(parts) < 2:
            continue

        code = parts[0]
        title = parts[1]

        # Filter: code should look like ABCD 123
        if not re.match(r"^[A-Z]{2,5}\s*\d{3}", code):
            continue

        courses.append({"code": code, "title": title})

    return courses


def main():
    session = requests.Session()

    # 1) terms
    terms = get_terms(session)
    print("Available terms:")
    for i, (code, label) in enumerate(terms[:20]):
        print(f"{i}) {code} -> {label}")

    idx = int(input("Enter term index: ").strip())
    term_code, term_label = terms[idx]
    print(f"\nUsing term: {term_label} ({term_code})")

    # 2) get search form + subjects list
    action_url, base_fields, subjects = post_term_and_get_search_form(session, term_code)
    print(f"Form action URL: {action_url}")
    print(f"Subjects detected: {len(subjects)}")

    # 3) loop subjects
    all_courses = []
    failures = 0

    # Start small for testing (then switch to all subjects)
    # test_subject_values = [v for v, _ in subjects if v in ("CMPS", "EECE", "ECON")]
    # loop_subjects = test_subject_values

    loop_subjects = [v for v, _ in subjects]  # ALL subjects

    for subj in loop_subjects:
        try:
            html = fetch_subject_results_html(session, action_url, base_fields, subj)
            courses = parse_courses_from_results(html)

            print(f"{subj} -> {len(courses)} courses")
            all_courses.extend(courses)

            # be polite to the server
            time.sleep(0.6)

        except Exception as e:
            failures += 1
            print(f"⚠️ {subj} failed: {e}")
            time.sleep(1.2)

    # 4) deduplicate by code
    unique = {}
    for c in all_courses:
        unique.setdefault(c["code"], c)

    out = list(unique.values())

    with open("courses.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Saved courses.json with {len(out)} unique courses")
    print(f"Failures: {failures}")


if __name__ == "__main__":
    main()