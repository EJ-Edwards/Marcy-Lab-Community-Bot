import re

MAX_SUBJECT_LENGTH = 120
MAX_DESCRIPTION_LENGTH = 4000


def parse_email_report(message):
    """Parse a two-part Subject/Description report, allowing a multiline description."""
    lines = message.splitlines()
    subject_index = next(
        (index for index, line in enumerate(lines) if re.match(r"^\s*subject\s*:", line, re.IGNORECASE)),
        None,
    )
    description_index = next(
        (index for index, line in enumerate(lines) if re.match(r"^\s*description\s*:", line, re.IGNORECASE)),
        None,
    )
    if subject_index is None or description_index is None or subject_index >= description_index:
        return None
    if any(line.strip() for line in lines[:subject_index]):
        return None

    subject = re.sub(r"^\s*subject\s*:\s*", "", lines[subject_index], flags=re.IGNORECASE).strip()
    description_first_line = re.sub(
        r"^\s*description\s*:\s*",
        "",
        lines[description_index],
        flags=re.IGNORECASE,
    ).strip()
    description = "\n".join(
        [description_first_line, *lines[description_index + 1 :]]
    ).strip()
    if (
        not subject
        or len(subject) > MAX_SUBJECT_LENGTH
        or not description
        or len(description) > MAX_DESCRIPTION_LENGTH
    ):
        return None
    return subject, description
