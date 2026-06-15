def has_close_pair(numbers, threshold):
    for i, left in enumerate(numbers):
        for right in numbers[i + 1:]:
            if abs(left - right) < threshold:
                return True
    return False


def split_balanced_parens(text):
    groups = []
    depth = 0
    start = None

    for index, char in enumerate(text):
        if char == "(":
            if depth == 0:
                start = index
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0 and start is not None:
                groups.append(text[start:index + 1])
                start = None

    return groups


def rolling_minimum(numbers):
    result = []
    current = None
    for value in numbers:
        current = value if current is None else min(current, value)
        result.append(current)
    return result


def below_zero(changes):
    balance = 0
    for change in changes:
        balance += change
        if balance < 0:
            return True
    return False
