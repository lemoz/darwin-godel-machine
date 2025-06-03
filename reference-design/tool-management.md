# DGM MVP: Tool Management and Execution Design

This document outlines the proposed design for tool management and execution within the Darwin Gödel Machine (DGM) Minimum Viable Product (MVP). The design is informed by patterns observed in the Roo-Code repository.

## Core Principles:

*   **Modularity:** Each tool should be a self-contained unit with a clear interface.
*   **Centralized Dispatch:** A single point in the agent's logic should be responsible for parsing tool calls from the FM and dispatching them to the correct tool implementation.
*   **Contextual Execution:** Tools should receive necessary context from the agent (e.g., current working directory, user approval mechanisms, methods to return results/errors).
*   **Standardized Tool Definition:** Tools should have a defined schema for their parameters and a clear description for the FM.
*   **Controlled Execution:** Implement safeguards like user approvals for sensitive actions, tool repetition detection, and limiting one tool execution per FM response turn.

## Key Components:

1.  **Tool Definition (Python):**
    *   Each tool will be implemented as a Python function (e.g., `read_file_tool(agent_context, params)`).
    *   **Tool Schema & Description:** Each tool should have an associated schema (e.g., a JSON schema object or a Pydantic model) defining its expected parameters and their types. A natural language description for the FM is also crucial. This information will be used to construct the tool descriptions provided to the FM in the system prompt.
    *   **`agent_context` Parameter:** This object (analogous to Roo-Code's `cline: Task`) will be passed to each tool, providing:
        *   Access to the current working directory (`cwd`).
        *   A method to request user approval for actions (`async def request_approval(prompt_message: str) -> bool`).
        *   A method to return structured results to the agent core (`def push_tool_result(result_xml: str)`).
        *   A method to report errors (`def report_error(error_message: str)`).
        *   Access to other relevant agent state or services if necessary (e.g., file ignore lists, context trackers).
    *   **`params` Parameter:** A dictionary containing the parameters for the tool call, as parsed from the FM's output.

2.  **FM Output Parsing:**
    *   The agent's core loop will receive a text response from the FM.
    *   A dedicated parsing function (e.g., `parse_fm_response_for_tools(response_text: str)`) will scan this text for tool call invocations (e.g., XML-like blocks: `<tool_name><param1>value1</param1>...</tool_name>`).
    *   This parser will extract the `tool_name` and the `params` dictionary.
    *   Roo-Code uses `parseAssistantMessage` which seems to produce an array of structured blocks (text, tool_use). We can adopt a similar approach.

3.  **Tool Dispatcher:**
    *   A central function or method within the agent's core logic (e.g., `execute_tool_call(tool_name: str, params: dict, agent_context: AgentContext)`).
    *   This dispatcher will use a dictionary or a series of `if/elif` statements to map the `tool_name` to the actual Python tool function.
    *   It will then call the appropriate tool function, passing the `agent_context` and `params`.
    *   **Example (Conceptual Python):**
        ```python
        # In Agent class or a dedicated ToolExecutor class
        async def execute_tool_call(self, tool_name: str, params: dict):
            tool_function = self.tool_registry.get(tool_name)
            if tool_function:
                try:
                    # agent_context would be 'self' or an object holding relevant state
                    await tool_function(self, params) 
                except Exception as e:
                    self.report_error(f"Error executing tool {tool_name}: {str(e)}")
                    self.push_tool_result(f"<error>Error executing tool {tool_name}: {str(e)}</error>")
            else:
                self.report_error(f"Unknown tool: {tool_name}")
                self.push_tool_result(f"<error>Unknown tool: {tool_name}</error>")
        ```

4.  **Tool Registry (Conceptual):**
    *   A dictionary mapping tool names (strings) to their respective Python functions.
    *   This registry would be populated at agent initialization.
        ```python
        # Example
        self.tool_registry = {
            "read_file": read_file_tool,
            "execute_command": execute_command_tool,
            # ... other tools
        }
        ```

5.  **Agent Core Loop Integration:**
    *   After the FM response is parsed, if a tool call is identified:
        1.  The agent calls the `execute_tool_call` dispatcher.
        2.  The tool executes (potentially involving user approval).
        3.  The tool uses `push_tool_result` (via `agent_context`) to provide its output.
        4.  This output is then formatted and included in the next message to the FM.
    *   The agent should enforce that only one tool is fully executed per FM turn.

6.  **User Approval Mechanism:**
    *   Tools performing sensitive actions (file writes, command execution) must request user approval via `agent_context.request_approval()`.
    *   This method will handle the necessary UI interaction (e.g., showing a dialog in a web interface or a prompt in a CLI).

7.  **Error Handling & Reporting:**
    *   Tools should use `agent_context.report_error()` for internal errors.
    *   The dispatcher should also handle errors like unknown tools.
    *   Error messages should be formatted and sent back to the FM via `push_tool_result`.

8.  **Tool Repetition Detection:**
    *   Implement a mechanism similar to Roo-Code's `ToolRepetitionDetector` to prevent an agent from getting stuck in loops calling the same tool with the same parameters.

## Workflow Example:

1.  FM responds with text containing `<read_file><path>example.txt</path></read_file>`.
2.  `parse_fm_response_for_tools` extracts `tool_name="read_file"` and `params={"path": "example.txt"}`.
3.  Agent core calls `agent.execute_tool_call("read_file", {"path": "example.txt"})`.
4.  The dispatcher looks up `read_file_tool` in its registry.
5.  `read_file_tool(agent_context, {"path": "example.txt"})` is executed.
    *   It might call `agent_context.request_approval(...)`.
    *   If approved, it reads the file.
    *   It calls `agent_context.push_tool_result("<file><path>example.txt</path><content>...</content></file>")`.
6.  The agent core takes this result, formats it as part of the next user message to the FM.

This design provides a structured and extensible way to manage tools, drawing on the robust patterns observed in Roo-Code.