import os
import re
import time
import pdfplumber
import firebase_admin
from collections import defaultdict
from firebase_admin import credentials, firestore

COURSES_FOLDER = "courses"

section_header_pattern = re.compile(
    r"^(.*?)\s*-\s*(\d{5})\s*-\s*([A-Z]{4})\s+(\d+[A-Z]{0,2})\s*-\s*([A-Z0-9]+)$"
)

# Matches names like:
# Mohamad Zalghout
# Mohamed A. Kobeissi
# Wadi' Jureidini
# Hans D. Muller
# Al Hajj
name_pattern = re.compile(
    r"\b([A-Z][a-zA-Z'`.-]+(?:\s+[A-Z][a-zA-Z'`.-]+){1,5})\b(?:\s*\(P\))?"
)


def get_db():
    if not firebase_admin._apps:
        cred = credentials.Certificate("serviceAccountKey.json")
        firebase_admin.initialize_app(cred)
    return firestore.client()


db = get_db()


def normalize_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def professor_doc_id(name: str) -> str:
    return (
        name.strip()
        .lower()
        .replace(" ", "_")
        .replace(".", "")
        .replace("/", "_")
        .replace("'", "")
        .replace("`", "")
    )


def is_probably_not_name(text: str) -> bool:
    text_lower = text.lower()

    banned_fragments = [
        " am", " pm", "jan ", "feb ", "mar ", "apr ", "may ", "jun ", "jul ",
        "aug ", "sep ", "oct ", "nov ", "dec ",
        "lecture", "lab", "project", "thesis", "recitation",
        "class", "online", "building", "hall", "campus",
        "mwf", "tr", "mw", "wf", "rf",
        "credits", "schedule", "type", "date range", "where",
        "associated term", "registration dates", "levels", "attributes",
        "course syllabus", "view catalog entry", "scheduled meeting times",
        "tba", "release:"
    ]

    if any(x in text_lower for x in banned_fragments):
        return True

    if re.search(r"\d", text):
        return True

    return False


def extract_names_from_text(text: str) -> list[str]:
    text = normalize_spaces(text)
    if not text:
        return []

    matches = name_pattern.findall(text)

    cleaned = []
    seen = set()

    for match in matches:
        name = normalize_spaces(match).strip(" ,;-")
        if not name:
            continue
        if is_probably_not_name(name):
            continue
        if len(name.split()) < 2:
            continue
        if name not in seen:
            seen.add(name)
            cleaned.append(name)

    return cleaned


def extract_lines_from_pdf(filepath: str) -> list[str]:
    lines = []

    with pdfplumber.open(filepath) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue

            page_lines = [normalize_spaces(x) for x in text.split("\n")]
            lines.extend([x for x in page_lines if x])

    return lines


def extract_sections_from_lines(lines: list[str]) -> list[dict]:
    sections = []
    i = 0

    while i < len(lines):
        line = lines[i]
        header_match = section_header_pattern.match(line)

        if not header_match:
            i += 1
            continue

        title, crn, subject, course_number, section = header_match.groups()
        code = f"{subject} {course_number}"
        course_id = f"{subject}_{course_number}"

        professors = []

        j = i + 1
        while j < len(lines):
            next_line = lines[j]
            normalized = normalize_spaces(next_line)

            if section_header_pattern.match(normalized):
                break

            # Main Banner case:
            # "Type Time Days Where Date Range Schedule Type Instructors"
            # next line(s) contain instructor names
            if "Instructors" in normalized:
                for k in range(1, 4):
                    if j + k < len(lines):
                        candidate = normalize_spaces(lines[j + k])

                        # stop if we hit a new section
                        if section_header_pattern.match(candidate):
                            break

                        names = extract_names_from_text(candidate)
                        if names:
                            professors.extend(names)
                            # usually the first name-bearing line is enough
                            break

                # Handle same-line case after "Instructors"
                after = normalized.split("Instructors", 1)[-1].strip()
                if after:
                    professors.extend(extract_names_from_text(after))

            # Special case: line itself contains "(P)" and a name,
            # like "Project Wassim El Hajj (P)"
            if "(P)" in normalized:
                professors.extend(extract_names_from_text(normalized))

            j += 1

        unique_professors = []
        seen = set()
        for p in professors:
            if p and p not in seen:
                seen.add(p)
                unique_professors.append(p)

        sections.append({
            "course_id": course_id,
            "code": code,
            "subject": subject,
            "course_number": course_number,
            "title": title,
            "crn": crn,
            "section": section,
            "professors": unique_professors,
        })

        i = j

    return sections


def extract_all_sections_from_pdfs() -> list[dict]:
    all_sections = []

    if not os.path.exists(COURSES_FOLDER):
        print(f"❌ Folder not found: {COURSES_FOLDER}")
        return all_sections

    for file in os.listdir(COURSES_FOLDER):
        if not file.lower().endswith(".pdf"):
            continue

        path = os.path.join(COURSES_FOLDER, file)

        try:
            lines = extract_lines_from_pdf(path)
            sections = extract_sections_from_lines(lines)
            all_sections.extend(sections)
            print(f"✅ {file} -> {len(sections)} sections found")
        except Exception as e:
            print(f"❌ Error reading {file}: {e}")

    return all_sections


def build_course_professors_map(sections: list[dict]) -> dict:
    course_map = {}

    for sec in sections:
        cid = sec["course_id"]

        if cid not in course_map:
            course_map[cid] = {
                "course_id": sec["course_id"],
                "code": sec["code"],
                "subject": sec["subject"],
                "course_number": sec["course_number"],
                "title": sec["title"],
                "professors": [],
                "sections": [],
            }

        course_map[cid]["sections"].append({
            "crn": sec["crn"],
            "section": sec["section"],
            "professors": sec["professors"],
        })

        existing = set(course_map[cid]["professors"])
        for prof in sec["professors"]:
            if prof not in existing:
                course_map[cid]["professors"].append(prof)
                existing.add(prof)

    return course_map


def build_professors_map(course_map: dict) -> dict:
    professors_map = defaultdict(lambda: {
        "name": "",
        "departments": [],
        "courses": []
    })

    for course in course_map.values():
        subject = course["subject"]

        for prof in course["professors"]:
            pid = professor_doc_id(prof)

            professors_map[pid]["name"] = prof

            if subject not in professors_map[pid]["departments"]:
                professors_map[pid]["departments"].append(subject)

            existing_ids = {c["course_id"] for c in professors_map[pid]["courses"]}
            if course["course_id"] not in existing_ids:
                professors_map[pid]["courses"].append({
                    "course_id": course["course_id"],
                    "code": course["code"],
                    "title": course["title"],
                    "department": subject
                })

    for pid in professors_map:
        professors_map[pid]["departments"].sort()
        professors_map[pid]["courses"].sort(key=lambda x: x["code"])

    return professors_map


def update_courses_collection(course_map: dict):
    batch = db.batch()
    count = 0
    total = 0

    for course in course_map.values():
        ref = db.collection("courses").document(course["course_id"])

        batch.set(ref, {
            "professors": course["professors"],
            "sections": course["sections"]
        }, merge=True)

        count += 1
        total += 1

        if count == 400:
            batch.commit()
            print(f"✅ Updated {total} course docs...")
            batch = db.batch()
            count = 0

    if count > 0:
        batch.commit()
        print(f"✅ Final course update commit. Total {total}")


def seed_professors_collection(professors_map: dict):
    batch = db.batch()
    count = 0
    total = 0

    for pid, prof_doc in professors_map.items():
        ref = db.collection("professors").document(pid)
        batch.set(ref, prof_doc, merge=True)

        count += 1
        total += 1

        if count == 400:
            batch.commit()
            print(f"✅ Seeded {total} professor docs...")
            batch = db.batch()
            count = 0

    if count > 0:
        batch.commit()
        print(f"✅ Final professor commit. Total {total}")


def main():
    print("✅ Starting extract_and_seed_professors_from_pdfs.py ...")

    db.collection("debug_seed").document("ping_extract_professors").set({
        "ping": True,
        "ts": time.time()
    })
    print("✅ Wrote debug_seed/ping_extract_professors")

    sections = extract_all_sections_from_pdfs()
    print(f"✅ Total sections extracted: {len(sections)}")

    course_map = build_course_professors_map(sections)
    professors_map = build_professors_map(course_map)

    print(f"✅ Unique courses with professor data: {len(course_map)}")
    print(f"✅ Unique professors found: {len(professors_map)}")

    print("\nSample courses:")
    for course in list(course_map.values())[:10]:
        print(f'{course["code"]} | {course["title"]} | {course["professors"]}')

    print("\nUpdating existing courses collection...")
    update_courses_collection(course_map)

    print("\nSeeding professors collection...")
    seed_professors_collection(professors_map)

    sample_prof_docs = db.collection("professors").limit(3).get()
    print(f"\n✅ professors sample docs: {len(sample_prof_docs)}")
    print("✅ Done!")


if __name__ == "__main__":
    main()