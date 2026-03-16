import os
import re
import json
import pdfplumber

COURSES_FOLDER = "../courses"
OUTPUT_FILE = "../courses.json"

course_pattern = re.compile(r"\b([A-Z]{4})\s*(\d{3}[A-Z]{0,2})\b")


def extract_from_pdf(filepath):
    courses = []

    with pdfplumber.open(filepath) as pdf:
        for page in pdf.pages:
            text = page.extract_text()

            if not text:
                continue

            matches = course_pattern.findall(text)

            for subject, number in matches:
                code = f"{subject} {number}"

                courses.append({
                    "code": code,
                    "subject": subject,
                    "number": number
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
                    all_courses[c["code"]] = c

                print(f"{file} -> {len(courses)} matches found")

            except Exception as e:
                print(f"Error reading {file}: {e}")

    output = list(all_courses.values())
    output.sort(key=lambda x: x["code"])

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"Saved {len(output)} unique courses to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()