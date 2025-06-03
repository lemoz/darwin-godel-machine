# DGM MVP: Foundation Model (FM) Interaction Layer Design

This document outlines the proposed design for the Foundation Model (FM) interaction layer in the Darwin Gödel Machine (DGM) Minimum Viable Product (MVP). This design is heavily inspired by the patterns observed in the Roo-Code repository and aims to provide a flexible and maintainable way to interact with various FM providers.

## Core Principles:

*   **Provider Agnostic:** The core DGM logic should not be tightly coupled to any specific FM provider.
*   **Configurability:** Users should be able to configure and switch between different FM providers (Gemini, Anthropic, OpenAI) and models.
*   **Extensibility:** Adding support for new providers or models should be straightforward.
*   **Standardized Interface:** A common interface for interacting with FMs, regardless of the underlying provider.
*   **Centralized Logic:** Provider-specific details (API calls, message formatting, authentication) should be encapsulated within dedicated handlers.

## Key Components:

1.  **`ApiHandler` Interface (Python):**
    *   A Python abstract base class (ABC) or a class defining a clear interface for all FM provider handlers.
    *   **Methods:**
        *   `__init__(self, api_key: str, model_name: str, **kwargs)`: Constructor to initialize with API key, model name, and other provider-specific options.
        *   `create_completion(self, messages: list[dict], stream: bool = True, **kwargs) -> Union[str, Iterator[str]]`:
            *   Takes a list of messages in a standardized internal format.
            *   Handles making the API call to the FM.
            *   Supports both streaming and non-streaming responses.
            *   Returns the FM's response as a string or an iterator of string chunks (for streaming).
            *   `**kwargs` can be used for provider-specific parameters (e.g., temperature, max_tokens).
        *   `count_tokens(self, text_or_messages: Union[str, list[dict]]) -> int`: (Optional but recommended) Calculates token count for given text or messages according to the provider's tokenization.
    *   **Example (Conceptual Python):**
        ```python
        from abc import ABC, abstractmethod
        from typing import List, Dict, Union, Iterator

        class ApiHandler(ABC):
            def __init__(self, api_key: str, model_name: str, **kwargs):
                self.api_key = api_key
                self.model_name = model_name
                # Store other kwargs as needed

            @abstractmethod
            def create_completion(self, messages: List[Dict], stream: bool = True, **kwargs) -> Union[str, Iterator[str]]:
                pass

            # Optional
            # @abstractmethod
            # def count_tokens(self, text_or_messages: Union[str, List[Dict]]) -> int:
            #     pass
        ```

2.  **Provider-Specific Handler Classes (e.g., `GeminiHandler`, `AnthropicHandler`, `OpenAIHandler`):**
    *   Concrete classes that inherit from `ApiHandler`.
    *   Each class implements the `create_completion` (and optionally `count_tokens`) method using the specific SDK and API conventions of its provider (e.g., `@google/generative-ai` for Gemini, `anthropic` SDK for Anthropic).
    *   Handles provider-specific authentication, request formatting, response parsing, and error handling.
    *   Manages message transformation from the internal DGM format to the provider's required format.

3.  **Internal Message Format:**
    *   A standardized dictionary structure for representing messages within the DGM system. This promotes consistency before messages are transformed for a specific provider.
    *   Inspired by Anthropic's format (or a simplified version):
        ```json
        {
          "role": "user" | "assistant",
          "content": "The message text or a list of content blocks (for multimodal later)"
        }
        ```
    *   Example: `[{"role": "user", "content": "Hello"}, {"role": "assistant", "content": "Hi there!"}]`

4.  **Message Transformation Utilities:**
    *   A set of functions responsible for converting messages between the internal DGM format and the formats required by each FM provider's SDK.
    *   Example: `def convert_dgm_to_gemini_messages(dgm_messages: list[dict]) -> list[dict]: ...`

5.  **Configuration Management:**
    *   A mechanism (e.g., a configuration file like `config.yaml` or `settings.json`, or environment variables) to store API keys, preferred models, and other settings for each provider.
    *   A `SettingsManager` or similar class to load and provide these configurations to the DGM.

6.  **`build_api_handler` Factory Function:**
    *   A function that takes provider settings (e.g., provider name, API key, model) as input.
    *   Returns an instantiated object of the appropriate `ApiHandler` subclass (e.g., `GeminiHandler` if "gemini" is specified).
    *   **Example (Conceptual Python):**
        ```python
        def build_api_handler(provider_name: str, api_key: str, model_name: str, **kwargs) -> ApiHandler:
            if provider_name == "gemini":
                return GeminiHandler(api_key, model_name, **kwargs)
            elif provider_name == "anthropic":
                return AnthropicHandler(api_key, model_name, **kwargs)
            # ... other providers
            else:
                raise ValueError(f"Unsupported provider: {provider_name}")
        ```

7.  **`Task` or `AgentInteraction` Class (Conceptual):**
    *   A higher-level class that encapsulates a single interaction or task involving an FM.
    *   It would hold an instance of an `ApiHandler` (obtained via `build_api_handler` based on current settings).
    *   Manages the process of preparing messages, calling `create_completion`, and handling the response.
    *   This is similar to the `Task` object observed in Roo-Code's `ClineProvider`.

## Workflow Example:

1.  DGM Core Logic needs to call an FM.
2.  It retrieves current FM provider settings (e.g., "gemini", API key, "gemini-1.5-pro").
3.  It calls `build_api_handler("gemini", "YOUR_API_KEY", "gemini-1.5-pro")` to get a `GeminiHandler` instance.
4.  It prepares messages in the internal DGM format.
5.  The `GeminiHandler`'s `create_completion` method is called:
    *   Internally, `GeminiHandler` transforms DGM messages to Gemini's format.
    *   It uses the `@google/generative-ai` SDK to make the API call.
    *   It handles the response (streaming or not) and returns it.
6.  DGM Core Logic receives and processes the FM's response.

## Benefits:

*   **Decoupling:** Core DGM logic is isolated from provider-specific implementation details.
*   **Flexibility:** Easy to switch FMs or add new ones without major refactoring of the core system.
*   **Maintainability:** Provider-specific code is contained within its own handler class.

This design provides a robust foundation for FM interactions within the DGM MVP.