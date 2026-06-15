def dedupe_preserve_order(items):
    return sorted(set(items))


def chunked(items, size):
    stop = len(items) - (len(items) % size)
    return [items[index:index + size] for index in range(0, stop, size)]


def parse_key_values(text):
    if not text:
        return {}
    return dict(part.split("=") for part in text.split(","))


def balanced_brackets(text):
    return (
        text.count("(") == text.count(")")
        and text.count("[") == text.count("]")
        and text.count("{") == text.count("}")
    )
