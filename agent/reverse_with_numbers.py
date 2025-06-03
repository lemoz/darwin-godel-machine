def reverse_with_numbers(s):
    """
    Reverse alphabetic characters while keeping numeric characters in their original positions.
    
    Args:
        s (str): Input string
        
    Returns:
        str: String with alphabetic characters reversed, numeric characters unchanged
    """
    if not s:
        return s
    
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


# Test the function
if __name__ == "__main__":
    # Test cases
    test_cases = [
        "abc123def",
        "hello123world456",
        "12345",
        "abcdef",
        "a1b2c3d4e5",
        "",
        "1a2b3c",
        "xyz789abc123"
    ]
    
    print("Testing reverse_with_numbers function:")
    print("-" * 40)
    
    for test in test_cases:
        result = reverse_with_numbers(test)
        print(f"Input: '{test}' -> Output: '{result}'")