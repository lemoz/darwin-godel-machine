def dedupe_preserve_order(items):
    seen = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def chunked(items, size):
    return [items[index:index + size] for index in range(0, len(items), size)]


def parse_key_values(text):
    result = {}
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        key, value = part.split("=", 1)
        result[key.strip()] = value.strip()
    return result


def balanced_brackets(text):
    pairs = {"(": ")", "[": "]", "{": "}"}
    closing = set(pairs.values())
    stack = []

    for char in text:
        if char in pairs:
            stack.append(pairs[char])
        elif char in closing:
            if not stack or stack.pop() != char:
                return False

    return not stack
