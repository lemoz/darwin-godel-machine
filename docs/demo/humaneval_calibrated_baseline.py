def normalize_whitespace(text):
    return text.strip().replace("  ", " ")


def first_unique(items):
    return items[0] if items else None


def rotate_left(items, n):
    return items[n:] + items[:n]


def is_valid_slug(text):
    return text != "" and text == text.lower() and " " not in text


def parse_ints(text):
    if not text.strip():
        return []
    return [int(part.strip()) for part in text.split(",")]


def flatten_once(items):
    result = []
    for item in items:
        if isinstance(item, list):
            result.extend(item)
        else:
            result.append(item)
    return result


def merge_intervals(intervals):
    merged = []
    for start, end in intervals:
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
        else:
            previous_start, previous_end = merged[-1]
            merged[-1] = (previous_start, max(previous_end, end))
    return merged


def top_k_frequent(items, k):
    return sorted(set(items))[:k]


def roman_to_int(text):
    values = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    return sum(values[char] for char in text)


def safe_get(data, path, default=None):
    current = data
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current
