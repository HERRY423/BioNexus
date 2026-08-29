"""Unit tests for BioNexus Private & Air-Gapped LLM Provider (BNS-LLM-001)."""

import pytest

from bionexus.airgap_guard import AirgapNetworkGuard, AirgapPolicyMode
from bionexus.private_llm_provider import (
    PrivateLLMBackendType,
    PrivateLLMProvider,
    PrivateModelConfig,
)


def test_private_llm_inference():
    guard = AirgapNetworkGuard(mode=AirgapPolicyMode.AIRGAP_STRICT)
    config = PrivateModelConfig(
        backend_type=PrivateLLMBackendType.LOCAL_VLLM,
        endpoint_url="http://127.0.0.1:8000/v1/chat/completions",
        model_name="llama3-70b-instruct",
    )
    provider = PrivateLLMProvider(config=config, airgap_guard=guard)

    messages = [
        {"role": "system", "content": "You are a BioNexus verified agent."},
        {"role": "user", "content": "Evaluate TP53 biomarker significance."},
    ]
    resp = provider.generate_chat_completion(messages, mock_response=True)

    assert resp.model_name == "llama3-70b-instruct"
    assert resp.backend_type == PrivateLLMBackendType.LOCAL_VLLM.value
    assert "TP53" in resp.content
    assert resp.prompt_tokens > 0
    assert resp.receipt["execution_status"] == "SUCCESS"
    assert resp.receipt["tool_name"] == "llm.private_chat_completion"
    assert resp.model_fingerprint.startswith("sha256:")


def test_private_llm_blocked_if_external():
    guard = AirgapNetworkGuard(mode=AirgapPolicyMode.AIRGAP_STRICT)
    config = PrivateModelConfig(
        backend_type=PrivateLLMBackendType.LOCAL_VLLM,
        endpoint_url="https://api.external-cloud.com/v1/chat/completions",
        model_name="untrusted-model",
    )
    provider = PrivateLLMProvider(config=config, airgap_guard=guard)

    messages = [{"role": "user", "content": "Hello"}]
    with pytest.raises(PermissionError, match="Airgap guard denied"):
        provider.generate_chat_completion(messages, mock_response=True)
