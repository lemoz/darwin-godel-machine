import re
from collections import Counter


def normalize_whitespace(text):
    return " ".join(text.split())


def first_unique(items):
    counts = Counter(items)
    for item in items:
        if counts[item] == 1:
            return item
    return None


def rotate_left(items, n):
    if not items:
        return []
    offset = n % len(items)
    return items[offset:] + items[:offset]


def is_valid_slug(text):
    if not text or text.startswith("-") or text.endswith("-"):
        return False
    if "--" in text:
        return False
    return all(char.islower() or char.isdigit() or char == "-" for char in text)


def parse_ints(text):
    return [int(match) for match in re.findall(r"[+-]?\d+", text)]


def flatten_once(items):
    result = []
    for item in items:
        if isinstance(item, (list, tuple)):
            result.extend(item)
        else:
            result.append(item)
    return result


def merge_intervals(intervals):
    merged = []
    for start, end in sorted(intervals):
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
        else:
            previous_start, previous_end = merged[-1]
            merged[-1] = (previous_start, max(previous_end, end))
    return merged


def top_k_frequent(items, k):
    first_index = {}
    counts = Counter(items)
    for index, item in enumerate(items):
        first_index.setdefault(item, index)
    ranked = sorted(counts, key=lambda item: (-counts[item], first_index[item]))
    return ranked[:k]


def roman_to_int(text):
    values = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    total = 0
    index = 0
    while index < len(text):
        value = values[text[index]]
        next_value = values[text[index + 1]] if index + 1 < len(text) else 0
        if value < next_value:
            total += next_value - value
            index += 2
        else:
            total += value
            index += 1
    return total


def safe_get(data, path, default=None):
    current = data
    for key in path:
        if isinstance(current, dict):
            if key not in current:
                return default
            current = current[key]
        elif isinstance(current, (list, tuple)) and isinstance(key, int):
            if key < 0 or key >= len(current):
                return default
            current = current[key]
        else:
            return default
    return current
