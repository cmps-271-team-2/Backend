import os
import re
import json
import pdfplumber

COURSES_FOLDER = "../courses"
OUTPUT_FILE = "../courses.json"

course_pattern = re.compile(r"\b([A-Z]{4})\s*(\d{3}[A-Z]{0,2})\b")
professor_pattern = re.compile(r"([A-Z][a-zA-Z'-]+),\s*([A-Z][a-zA-Z'-]+)")


def normalize_spaces(text):
    return re.sub(r"\s+", " ", text).strip()


def extract_title(line):
    line = normalize_spaces(line)

    # Expected Banner-like format:
    # "Biochemistry for MLSP - 23079 - BIOC 255 - 0"
    parts = [part.strip() for part in line.split(" - ")]

    if len(parts) >= 4:
        return normalize_spaces(parts[0])

    # Fallback if course code appears at beginning
    line = re.sub(r"^[A-Z]{4}\s*\d{3}[A-Z]{0,2}", "", line).strip()

    # Cut before professor if present
    prof_match = professor_pattern.search(line)
    if prof_match:
        line = line[:prof_match.start()].strip()

    # Remove trailing numeric junk
    line = re.sub(r"\s*-\s*\d+.*$", "", line).strip()
    line = re.sub(r"\b\d+(\.\d+)?\b$", "", line).strip()

    return normalize_spaces(line)


def extract_professors_from_text(text):
    text = normalize_spaces(text)
    professors = set()

    matches = professor_pattern.findall(text)
    for last, first in matches:
        professors.add(f"{first} {last}")

    return sorted(professors)


def extract_from_pdf(filepath):
    courses = []

    with pdfplumber.open(filepath) as pdf:
        for page in pdf.pages:
            text = page.extract_text()

            if not text:
                continue

            lines = text.split("\n")

            for i, line in enumerate(lines):
                line = line.strip()

                if not line:
                    continue

                match = course_pattern.search(line)
                if not match:
                    continue

                subject, number = match.groups()
                code = f"{subject} {number}"
                title = extract_title(line)

                # Try current line + next two lines for professor names
                nearby_parts = [line]

                if i + 1 < len(lines):
                    nearby_parts.append(lines[i + 1].strip())
                if i + 2 < len(lines):
                    nearby_parts.append(lines[i + 2].strip())

                nearby_text = " ".join(part for part in nearby_parts if part)
                professors = extract_professors_from_text(nearby_text)

                courses.append({
                    "course_id": f"{subject}_{number}",
                    "code": code,
                    "subject": subject,
                    "course_number": number,
                    "title": title,
                    "professors": professors,
                    "raw_line": line
                })

    return courses


def main():
    all_courses = {}

    if not os.path.exists(COURSES_FOLDER):
        print(f"Folder not found: {COURSES_FOLDER}")
        return

    for file in os.listdir(COURSES_FOLDER):
        if file.lower().endswith(".pdf"):
            path = os.path.join(COURSES_FOLDER, file)

            try:
                courses = extract_from_pdf(path)

                for c in courses:
                    cid = c["course_id"]

                    if cid not in all_courses:
                        all_courses[cid] = c
                    else:
                        old_profs = set(all_courses[cid].get("professors", []))
                        new_profs = set(c.get("professors", []))
                        all_courses[cid]["professors"] = sorted(old_profs | new_profs)

                        old_title = all_courses[cid].get("title", "")
                        new_title = c.get("title", "")

                        # Prefer shorter cleaner title
                        if old_title and new_title:
                            if len(new_title) < len(old_title):
                                all_courses[cid]["title"] = new_title
                        elif new_title:
                            all_courses[cid]["title"] = new_title

                print(f"{file} -> {len(courses)} matches found")

            except Exception as e:
                print(f"Error reading {file}: {e}")

    output = list(all_courses.values())
    output.sort(key=lambda x: x["code"])

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"Saved {len(output)} unique courses to {OUTPUT_FILE}")

    print("\nSample output:")
    for c in output[:10]:
        print(f'{c["code"]} | {c["title"]} | {c["professors"]}')


if __name__ == "__main__":
    main()