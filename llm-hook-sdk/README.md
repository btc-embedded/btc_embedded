# llm-hook-sdk

`llm-hook-sdk` contains the shared protocol types (`Message`, `Tool`, `ChatResponse`, etc.) and the `LLMHookBase` stdin/stdout loop that the Java plugin talks to. Provider-specific code lives outside the package, for example in `examples\aws_bedrock_hook.py`.

## Package layout

```text
llm-hook-sdk/
├── pyproject.toml
├── README.md
├── examples/
│   └── aws_bedrock_hook.py
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

## Install locally

Create and activate a virtual environment, then install the package from source:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
```

If you want to run the Bedrock example too, install the optional dependency group:

```powershell
python -m pip install -e ".[bedrock]"
```

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

## Bedrock example

An AWS Bedrock implementation is included at:

```text
examples/aws_bedrock_hook.py
```