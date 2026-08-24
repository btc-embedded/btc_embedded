# llm-hook-sdk

`llm-hook-sdk` contains the shared protocol types (`Message`, `Tool`, `ChatResponse`, etc.) and the `LLMHookBase` stdin/stdout loop that the Java plugin talks to. Provider-specific code lives outside the package, for example in `examples\aws_sonnet_4-6_hook.py`.

## Package layout

```text
llm-hook-sdk/
├── pyproject.toml
├── README.md
├── examples/
│   ├── aws_sonnet_4-6_hook.py
│   └── aws_sonnet_5_hook.py
└── src/
    └── llm_hook_sdk/
        ├── __init__.py
        ├── base.py
        ├── types.py
        ├── __init__.pyi
        ├── base.pyi
        ├── types.pyi
        └── py.typed
```

## Installation

**From PyPI:**

```bash
pip install llm-hook-sdk
```

**From a local copy:**

```bash
pip install ./llm-hook-sdk
```

The SDK has no external dependencies of its own. If your hook needs a provider-specific package (e.g. `boto3` for AWS Bedrock, `openai` for OpenAI), install it alongside the SDK.

## Public API

The package currently re-exports:

- `LLMHookBase`
- `MessageRole`
- `StopReason`
- `Tool`
- `ToolCall`
- `ToolResult`
- `Message`
- `ChatResponse`
- `ContentBlock`

Example import:

```python
from llm_hook_sdk import LLMHookBase, ChatResponse, StopReason
```

## Writing a hook

Provider implementations subclass `LLMHookBase` and return `ChatResponse` objects:

```python
from llm_hook_sdk import ChatResponse, LLMHookBase, StopReason


class MyHook(LLMHookBase):
    def __init__(self):
        pass

    def chat(self, messages, tools=None):
        return ChatResponse(
            content=[{"type": "text", "text": "Hello from my provider"}],
            stop_reason=StopReason.COMPLETE,
            prompt_tokens=0,
            completion_tokens=0,
        )


if __name__ == "__main__":
    MyHook().run()
```

## Bedrock examples

AWS Bedrock implementations are included at:

```text
examples/aws_sonnet_4-6_hook.py
examples/aws_sonnet_5_hook.py
```

Note: these examples require `boto3` to be installed.
