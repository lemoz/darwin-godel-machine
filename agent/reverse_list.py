def reverse_list(lst):
    """
    Reverses a list in-place without using built-in reverse methods.
    
    Args:
        lst: The list to reverse
    
    Returns:
        None (modifies the list in-place)
    """
    # Use two pointers approach - one from start, one from end
    left = 0
    right = len(lst) - 1
    
    # Swap elements from both ends moving towards center
    while left < right:
        # Swap elements at left and right positions
        lst[left], lst[right] = lst[right], lst[left]
        
        # Move pointers towards center
        left += 1
        right -= 1
    
    # Function returns None as it modifies in-place


# Test the function with the official test cases
if __name__ == "__main__":
    print("Testing reverse_list function:")
    
    # Test case 1: [1, 2, 3, 4, 5] → [5, 4, 3, 2, 1]
    test1 = [1, 2, 3, 4, 5]
    print(f"Before: {test1}")
    reverse_list(test1)
    print(f"After: {test1}")
    print(f"Expected: [5, 4, 3, 2, 1]")
    print(f"Match: {test1 == [5, 4, 3, 2, 1]}")
    print()
    
    # Test case 2: ['a', 'b', 'c'] → ['c', 'b', 'a']
    test2 = ['a', 'b', 'c']
    print(f"Before: {test2}")
    reverse_list(test2)
    print(f"After: {test2}")
    print(f"Expected: ['c', 'b', 'a']")
    print(f"Match: {test2 == ['c', 'b', 'a']}")
    print()
    
    # Test case 3: [] → []
    test3 = []
    print(f"Before: {test3}")
    reverse_list(test3)
    print(f"After: {test3}")
    print(f"Expected: []")
    print(f"Match: {test3 == []}")
    print()
    
    # Test case 4: [1] → [1]
    test4 = [1]
    print(f"Before: {test4}")
    reverse_list(test4)
    print(f"After: {test4}")
    print(f"Expected: [1]")
    print(f"Match: {test4 == [1]}")