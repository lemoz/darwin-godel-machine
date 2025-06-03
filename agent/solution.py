def reverse_with_numbers(s):
    """
    Takes a string and returns a new string where all alphabetic characters 
    are reversed, but numeric characters remain in their original positions.
    """
    # Convert string to list for easier manipulation
    chars = list(s)
    
    # Extract only alphabetic characters
    alpha_chars = [c for c in s if c.isalpha()]
    
    # Reverse the alphabetic characters
    alpha_chars.reverse()
    
    # Replace alphabetic characters in original positions with reversed ones
    alpha_index = 0
    for i in range(len(chars)):
        if chars[i].isalpha():
            chars[i] = alpha_chars[alpha_index]
            alpha_index += 1
    
    return ''.join(chars)


# Test the function with the provided examples
if __name__ == "__main__":
    test_cases = [
        ("abc123def", "fed123cba"),
        ("hello5world", "dlrow5olleh"),
        ("123", "123"),
        ("abc", "cba")
    ]
    
    print("Testing reverse_with_numbers function:")
    print("=" * 40)
    
    for i, (input_str, expected) in enumerate(test_cases, 1):
        result = reverse_with_numbers(input_str)
        status = "✓ PASS" if result == expected else "✗ FAIL"
        print(f"Test {i}: {input_str} → {result} (expected: {expected}) {status}")
    
    print("=" * 40)