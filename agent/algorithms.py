def binary_search(arr, target):
    """
    Performs binary search on a sorted array.
    Returns the index of target if found, -1 otherwise.
    """
    left, right = 0, len(arr) - 1
    
    while left <= right:
        mid = (left + right) // 2
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            left = mid + 1
        else:
            right = mid - 1
    
    return -1


def is_palindrome(s):
    """
    Checks if a string is a palindrome (ignoring case and non-alphanumeric characters).
    """
    # Convert to lowercase and keep only alphanumeric characters
    cleaned = ''.join(char.lower() for char in s if char.isalnum())
    
    # Check if cleaned string equals its reverse
    return cleaned == cleaned[::-1]


def fibonacci(n):
    """
    Returns the nth Fibonacci number.
    """
    if n <= 1:
        return n
    
    a, b = 0, 1
    for _ in range(2, n + 1):
        a, b = b, a + b
    
    return b


def prime_factors(n):
    """
    Returns a list of prime factors of n.
    """
    if n <= 1:
        return []
    
    factors = []
    divisor = 2
    
    while divisor * divisor <= n:
        while n % divisor == 0:
            factors.append(divisor)
            n //= divisor
        divisor += 1
    
    if n > 1:
        factors.append(n)
    
    return factors


def merge_sorted_lists(list1, list2):
    """
    Merges two sorted lists into one sorted list.
    """
    result = []
    i, j = 0, 0
    
    # Merge elements while both lists have remaining elements
    while i < len(list1) and j < len(list2):
        if list1[i] <= list2[j]:
            result.append(list1[i])
            i += 1
        else:
            result.append(list2[j])
            j += 1
    
    # Add remaining elements from list1
    while i < len(list1):
        result.append(list1[i])
        i += 1
    
    # Add remaining elements from list2
    while j < len(list2):
        result.append(list2[j])
        j += 1
    
    return result