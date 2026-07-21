from types import SimpleNamespace

import pytest


class FakeLLMClient:
    """Minimal deterministic replacement for the real LLM client."""

    def __init__(self, response_text: str):
        self.response_text = response_text
        self.calls: list[dict] = []

        self.chat = SimpleNamespace(
            completions=SimpleNamespace(
                create=self._create,
            )
        )

    def _create(self, **kwargs):
        self.calls.append(kwargs)

        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=self.response_text,
                    )
                )
            ]
        )


@pytest.fixture
def fake_client_factory():
    def create(response_text: str) -> FakeLLMClient:
        return FakeLLMClient(response_text)

    return create