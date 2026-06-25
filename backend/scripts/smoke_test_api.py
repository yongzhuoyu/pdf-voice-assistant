"""
One-shot check that the Anthropic API key works end-to-end.

Run:  python scripts/smoke_test_api.py
Makes the smallest possible billed call and prints the reply + token usage.
If billing/credits aren't set up, the SDK raises a clear error here rather
than deep inside the pipeline later.
"""

import sys
from pathlib import Path

# Make `app` importable when run as a script from backend/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import anthropic
from app import config


def main() -> None:
    key = config.require_anthropic_key()
    client = anthropic.Anthropic(api_key=key)

    resp = client.messages.create(
        model=config.ANSWER_MODEL,
        max_tokens=32,
        messages=[{"role": "user", "content": "Reply with exactly: pipeline ready"}],
    )

    text = next((b.text for b in resp.content if b.type == "text"), "")
    print(f"Model:  {resp.model}")
    print(f"Reply:  {text!r}")
    print(f"Tokens: in={resp.usage.input_tokens} out={resp.usage.output_tokens}")
    print("\nPASS: ANTHROPIC_API_KEY works — billing is active.")


if __name__ == "__main__":
    main()
