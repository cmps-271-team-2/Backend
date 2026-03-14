import time
import re
import requests
from bs4 import BeautifulSoup
from app import db  # Firestore client from your app.py

BASE = "https://www-banner.aub.edu.lb/pls/weba"
TERM_PAGE = f"{BASE}/bwckschd.p_disp_dyn_sched"
RESULTS_PAGE = f"{BASE}/bwckschd.p_get_crse_unsec"
PROC_TERM_PAGE = f"{BASE}/bwckgens.p_proc_term_date"

HEADERS = {"User-Agent": "CMPS271-course-project/1.0"}


def format_id(code: str) -> str:
    return code.strip().replace(" ", "_").replace("/", "_")


def get_terms(session: requests.Session):
    r = session.get(TERM_PAGE, headers=HEADERS, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    sel = soup.find("select", {"name": "p_term"})
    if not sel:
        raise RuntimeError("Could not find term dropdown (p_term).")

    terms = []
    for opt in sel.find_all("option"):
        code = (opt.get("value") or "").strip()
        label = opt.get_text(strip=True)
        if code and code != "0":
            terms.append((code, label))

    return terms


def submit_term_and_get_subjects(session: requests.Session, term_code: str):
    """
    Correct Banner flow:
    POST term to bwckgens.p_proc_term_date, which returns the page containing subjects dropdown.
    """
    payload = {
    "p_term": term_code,
    "term_in": "Submit"
}

    r = session.post(PROC_TERM_PAGE, data=payload, headers=HEADERS, timeout=30)
    r.raise_for_status()

    print("DEBUG status:", r.status_code)
    print("DEBUG url:", r.url)
    print("DEBUG first 200 chars:", r.text[:200])

    with open("debug_proc_term.html", "w", encoding="utf-8") as f:
    f.write(r.text)

    print("✅ Wrote debug_proc_term.html (open it in your browser)")


    soup = BeautifulSoup(r.text, "html.parser")

    sel = soup.find("select", {"name": "sel_subj"})
    if not sel:
        # Debug: show what dropdown names exist on this page
        names = [s.get("name", "<no-name>") for s in soup.find_all("select")]
        raise RuntimeError(f"Could not find subjects dropdown (sel_subj). Selects found: {names}")

    subjects = []
    for opt in sel.find_all("option"):
        code = (opt.get("value") or "").strip()
        label = opt.get_text(strip=True)
        # Banner includes '%' meaning "All" sometimes; skip it
        if re.fullmatch(r"[A-Z]{2,5}", code):
            subjects.append((code, label))

    return subjects

def fetch_subject_courses(session: requests.Session, term_code: str, subj_code: str):
    """
    Fetch course entries for ONE subject (e.g., CMPS).
    """
    payload = {
        "term_in": term_code,
        "sel_subj": subj_code,

        # dummy fields Banner expects
        "sel_day": "dummy",
        "sel_schd": "dummy",
        "sel_insm": "dummy",
        "sel_camp": "dummy",
        "sel_levl": "dummy",
        "sel_sess": "dummy",
        "sel_instr": "dummy",
        "sel_ptrm": "dummy",
        "sel_attr": "dummy",

        # optional filters empty
        "sel_crse": "",
        "sel_title": "",
        "sel_from_cred": "",
        "sel_to_cred": "",
        "sel_begin_hh": "",
        "sel_begin_mi": "",
        "sel_begin_ap": "",
        "sel_end_hh": "",
        "sel_end_mi": "",
        "sel_end_ap": "",
    }

    r = session.post(RESULTS_PAGE, data=payload, headers=HEADERS, timeout=60)

    # If Banner returns 500 sometimes, we retry once after a short delay
    if r.status_code >= 500:
        time.sleep(1.0)
        r = session.post(RESULTS_PAGE, data=payload, headers=HEADERS, timeout=60)

    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")
    titles = [t.get_text(" ", strip=True) for t in soup.find_all("th", class_="ddtitle")]

    courses = []
    for line in titles:
        # Example: "CMPS 271 - Software Engineering - 12345 - LEC - 1"
        parts = [p.strip() for p in line.split(" - ") if p.strip()]
        if len(parts) < 2:
            continue

        code = parts[0]
        title = parts[1]

        m = re.match(r"^([A-Z]{2,5})\s+(\d{3}[A-Z]?)$", code)
        if not m:
            continue

        dept, number = m.group(1), m.group(2)
        courses.append({"code": code, "title": title, "dept": dept, "number": number})

    return courses


def seed_courses_to_firestore(course_list):
    # Deduplicate by course code
    unique = {}
    for c in course_list:
        unique.setdefault(c["code"], c)

    all_courses = list(unique.values())
    print(f"✅ Unique courses found: {len(all_courses)}")

    batch = db.batch()
    count = 0
    total = 0

    for c in all_courses:
        doc_id = format_id(c["code"])
        ref = db.collection("courses").document(doc_id)

        batch.set(ref, {
            "code": c["code"],
            "title": c["title"],
            "department": c["dept"],
            "number": c["number"],
            "ratingAvg": 0,
            "ratingCount": 0
        }, merge=True)

        count += 1
        total += 1

        if count == 400:
            batch.commit()
            print(f"✅ Committed {total}...")
            batch = db.batch()
            count = 0

    if count:
        batch.commit()
        print(f"✅ Final commit. Total {total}")


def main():
    session = requests.Session()

    terms = get_terms(session)
    print("Available terms (pick one):")
    for i, (code, label) in enumerate(terms[:15]):
        print(f"{i}) {code} -> {label}")

    choice = input("\nEnter term index to use (e.g., 7 for Spring): ").strip()
    if not choice.isdigit():
        print("❌ Invalid input. Please enter a number.")
        return

    idx = int(choice)
    if idx < 0 or idx >= len(terms):
        print("❌ Invalid index.")
        return

    term_code, term_label = terms[idx]
    print(f"\n✅ Using term: {term_label} ({term_code})\n")

    # ✅ Get subjects the correct way (submit term first)
    subjects = submit_term_and_get_subjects(session, term_code)
    print(f"✅ Subjects found: {len(subjects)}")

    all_courses = []
    for subj_code, subj_name in subjects:
        subj_courses = fetch_subject_courses(session, term_code, subj_code)
        all_courses.extend(subj_courses)
        print(f"[OK] {subj_code} ({subj_name}) -> +{len(subj_courses)} entries")
        time.sleep(0.25)  # be polite

    print(f"\n✅ Total scraped entries (including duplicates): {len(all_courses)}")
    seed_courses_to_firestore(all_courses)
    print("✅ Done: courses collection populated!")


if __name__ == "__main__":
    main()