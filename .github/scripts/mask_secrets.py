def emit_masks(text):
    for line in text.splitlines():
        line = line.strip()
        if len(line) >= 3:
            print(f"::add-mask::{line}")


def main():
    for path in ("config/profile.yaml", "config/cv_template.md"):
        with open(path, encoding="utf-8") as f:
            emit_masks(f.read())


if __name__ == "__main__":
    main()
