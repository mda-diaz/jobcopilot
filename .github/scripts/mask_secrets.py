from pdfminer.high_level import extract_text


def emit_masks(text):
    for line in text.splitlines():
        line = line.strip()
        if len(line) >= 3:
            print(f"::add-mask::{line}")


def main():
    with open("config/profile.yaml", encoding="utf-8") as f:
        profile_text = f.read()
    emit_masks(profile_text)

    cv_text = extract_text("config/cv.pdf")
    with open("config/cv_template.md", "w", encoding="utf-8") as f:
        f.write(cv_text)
    emit_masks(cv_text)


if __name__ == "__main__":
    main()
