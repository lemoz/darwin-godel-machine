from algorithms import binary_search, is_palindrome, fibonacci, prime_factors, merge_sorted_lists

# Test binary_search
print("Testing binary_search:")
print(f"binary_search([1, 3, 5, 7, 9, 11], 7) = {binary_search([1, 3, 5, 7, 9, 11], 7)} (expected: 3)")
print(f"binary_search([2, 4, 6, 8, 10], 5) = {binary_search([2, 4, 6, 8, 10], 5)} (expected: -1)")
print(f"binary_search([1], 1) = {binary_search([1], 1)} (expected: 0)")
print(f"binary_search([], 5) = {binary_search([], 5)} (expected: -1)")
print(f"binary_search([1, 2, 3, 4, 5], 3) = {binary_search([1, 2, 3, 4, 5], 3)} (expected: 2)")

print("\nTesting is_palindrome:")
print(f"is_palindrome('racecar') = {is_palindrome('racecar')} (expected: True)")
print(f"is_palindrome('A man a plan a canal Panama') = {is_palindrome('A man a plan a canal Panama')} (expected: True)")
print(f"is_palindrome('hello') = {is_palindrome('hello')} (expected: False)")
print(f"is_palindrome('') = {is_palindrome('')} (expected: True)")
print(f"is_palindrome('a') = {is_palindrome('a')} (expected: True)")

print("\nTesting fibonacci:")
print(f"fibonacci(0) = {fibonacci(0)} (expected: 0)")
print(f"fibonacci(1) = {fibonacci(1)} (expected: 1)")
print(f"fibonacci(5) = {fibonacci(5)} (expected: 5)")
print(f"fibonacci(10) = {fibonacci(10)} (expected: 55)")
print(f"fibonacci(15) = {fibonacci(15)} (expected: 610)")

print("\nTesting prime_factors:")
print(f"prime_factors(12) = {prime_factors(12)} (expected: [2, 2, 3])")
print(f"prime_factors(17) = {prime_factors(17)} (expected: [17])")
print(f"prime_factors(100) = {prime_factors(100)} (expected: [2, 2, 5, 5])")
print(f"prime_factors(1) = {prime_factors(1)} (expected: [])")
print(f"prime_factors(60) = {prime_factors(60)} (expected: [2, 2, 3, 5])")

print("\nTesting merge_sorted_lists:")
print(f"merge_sorted_lists([1, 3, 5], [2, 4, 6]) = {merge_sorted_lists([1, 3, 5], [2, 4, 6])} (expected: [1, 2, 3, 4, 5, 6])")
print(f"merge_sorted_lists([1, 2, 3], [4, 5, 6]) = {merge_sorted_lists([1, 2, 3], [4, 5, 6])} (expected: [1, 2, 3, 4, 5, 6])")
print(f"merge_sorted_lists([], [1, 2, 3]) = {merge_sorted_lists([], [1, 2, 3])} (expected: [1, 2, 3])")
print(f"merge_sorted_lists([5, 6, 7], []) = {merge_sorted_lists([5, 6, 7], [])} (expected: [5, 6, 7])")
print(f"merge_sorted_lists([1, 1, 2], [1, 2, 3]) = {merge_sorted_lists([1, 1, 2], [1, 2, 3])} (expected: [1, 1, 1, 2, 2, 3])")