import re

SECRET_PATTERNS = [
    (r"sk-[a-zA-Z0-9]{20,}", "[REDACTED_OPENAI_KEY]"),
    (r"ghp_[a-zA-Z0-9]{20,}", "[REDACTED_GITHUB_TOKEN]"),
    (r"xox[baprs]-[a-zA-Z0-9]{10,}", "[REDACTED_SLACK_TOKEN]"),
    (r"-----BEGIN [A-Z ]+ PRIVATE KEY-----.*", "[REDACTED_PRIVATE_KEY]"),
    (r"AKIA[0-9A-Z]{16}", "[REDACTED_AWS_ACCESS_KEY]"),
]

INJECTION_PATTERNS = [
    r"(?i)ignore (previous|all) instructions",
    r"(?i)system prompt",
]

def mask_secrets(text: str) -> str:
    """
    Mask common secret patterns in the text.
    """
    if not text:
        return text

    for pattern, replacement in SECRET_PATTERNS:
        text = re.sub(pattern, replacement, text)
    return text

def strip_prompt_injection(text: str) -> str:
    """
    Remove lines that look like prompt injection attempts.
    """
    if not text:
        return text

    lines = text.splitlines()
    safe_lines = []
    for line in lines:
        if any(re.search(p, line) for p in INJECTION_PATTERNS):
            continue
        safe_lines.append(line)
    return "\n".join(safe_lines)
