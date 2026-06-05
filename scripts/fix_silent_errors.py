import os
import re

TARGET_PATTERN = r'import\s+logging\s*;\s*logging\.debug\(\s*"Silent error suppressed:\s*%s"\s*,\s*(.*?)\s*\)'
REPLACEMENT = r'logger.warning("Error suppressed: %s", \1)'

LOGGER_INIT = """import logging

logger = logging.getLogger(__name__)"""


def process_file(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # Skip if no matches
    if not re.search(TARGET_PATTERN, content):
        return False

    # Replace the suppressed errors
    new_content = re.sub(TARGET_PATTERN, REPLACEMENT, content)

    # Ensure logger is initialized
    if "logger = logging.getLogger(__name__)" not in new_content:
        # Try to insert after imports or at top of file
        # Find first non-empty, non-comment line that isn't an import
        lines = new_content.split("\n")
        insert_idx = 0
        in_docstring = False
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith('"""') or stripped.startswith("'''"):
                if stripped.count('"""') == 1 or stripped.count("'''") == 1:
                    in_docstring = not in_docstring
                continue
            if in_docstring:
                continue
            if (
                stripped
                and not stripped.startswith("import")
                and not stripped.startswith("from")
                and not stripped.startswith("#")
            ):
                insert_idx = i
                break

        # Insert the logger initialization
        lines.insert(insert_idx, "logger = logging.getLogger(__name__)")
        lines.insert(insert_idx, "import logging")
        new_content = "\n".join(lines)

        # Deduplicate import logging if we just added it and it was already there
        # but honestly multiple imports in python are safe, let's clean up a bit.
        # Actually it's simpler to just ensure it works.

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(new_content)

    return True


def main():
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
    count = 0
    for dirpath, _, filenames in os.walk(root_dir):
        for fname in filenames:
            if fname.endswith(".py"):
                fpath = os.path.join(dirpath, fname)
                if process_file(fpath):
                    print(f"Fixed: {fpath}")
                    count += 1
    print(f"Total files fixed: {count}")


if __name__ == "__main__":
    main()
