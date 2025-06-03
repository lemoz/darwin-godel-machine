"""
Test the Agent's code extraction functionality.
This verifies that the Agent correctly extracts Python code from markdown blocks.
"""

import re

def _extract_code_solution(response: str) -> str:
    """
    Extract Python code from the agent's response.
    
    The agent is instructed to provide code in markdown code blocks.
    
    Args:
        response: Agent's response containing the solution
        
    Returns:
        Extracted Python code
    """
    # Extract code from markdown code blocks
    # Pattern matches ```python or ``` followed by code and closing ```
    # More flexible pattern to handle various formatting
    code_block_pattern = r'```(?:python)?\s*\n(.*?)\n\s*```'
    matches = re.findall(code_block_pattern, response, re.DOTALL)
    
    if matches:
        # Return the last code block (likely the final solution)
        code = matches[-1].strip()
        print(f"[INFO] Extracted code from markdown block: {len(code)} characters")
        return code
    
    # If no code blocks found, log warning
    print("[WARNING] No markdown code blocks found in response")
    
    # As a fallback, try to find code that looks like a function definition
    lines = response.split('\n')
    code_lines = []
    in_function = False
    
    for line in lines:
        # Check if line starts a function
        if line.strip().startswith(('def ', 'class ', 'import ', 'from ', 'async def ')):
            in_function = True
            code_lines = [line]
        elif in_function:
            # Continue collecting lines if they're indented or empty
            if line.strip() == '' or line.startswith((' ', '\t')):
                code_lines.append(line)
            else:
                # Non-indented non-empty line, function likely ended
                if not line.strip().startswith(('def ', 'class ', 'import ', 'from ')):
                    break
    
    if code_lines:
        code = '\n'.join(code_lines).strip()
        print(f"[INFO] Extracted code using fallback method: {len(code)} characters")
        return code
    
    # If all else fails, return empty string and log error
    print("[ERROR] Could not extract any code from response")
    return ""

# Test the code extraction method
test_responses = [
    # Test 1: Standard markdown code block
    """
    I'll solve this step by step.
    
    Here's the solution:
    
    ```python
    def reverse_string(s):
        return s[::-1]
    ```
    """,
    
    # Test 2: Code block without 'python' language identifier
    """
    The function is implemented below:
    
    ```
    def add_numbers(a, b):
        return a + b
    ```
    """,
    
    # Test 3: Multiple code blocks (should use the last one)
    """
    First, let me show a helper function:
    
    ```python
    def helper():
        pass
    ```
    
    And here's the main solution:
    
    ```python
    def multiply(x, y):
        return x * y
    ```
    """,
    
    # Test 4: No code blocks (fallback extraction)
    """
    Here's the function:
    
    def subtract(a, b):
        return a - b
    
    This function subtracts b from a.
    """,
    
    # Test 5: Empty response (should return empty string)
    """
    I couldn't solve this task.
    """
]

print("Testing Agent Code Extraction")
print("=" * 50)

for i, response in enumerate(test_responses, 1):
    print(f"\nTest {i}:")
    print(f"Response preview: {response.strip()[:50]}...")
    
    # Extract code using the function
    extracted_code = _extract_code_solution(response)
    
    print(f"Extracted code:")
    print("-" * 30)
    print(extracted_code if extracted_code else "(empty)")
    print("-" * 30)

print("\n" + "=" * 50)
print("Test complete!")