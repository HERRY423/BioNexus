"""
Real Host-Agent Evaluation Adapter & Execution Harness for BioNexus Eval L2.

Enables true end-to-end evaluation against real Host Coding Agents:
1. OpenAI / Codex (gpt-4o, gpt-4o-mini, o1)
2. Anthropic (claude-3-5-sonnet, claude-3-opus)
3. Google Gemini (gemini-1.5-pro, gemini-1.5-flash)
4. Offline Trace Replay (for deterministic CI environments without API keys)

Executes the pipeline:
Host LLM + BioNexus Capability System Prompt + User Query -> Real Live Generation -> Prohibited Claims Audit
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Optional

from bionexus.claim_checker import ClaimAuditResult, audit_prohibited_claims
from evals.schema import EvalCase


@dataclass
class HostAgentResponse:
    """Captured response from a real host agent execution."""

    prompt: str
    response_text: str
    provider: str
    model: str
    is_live: bool
    latency_ms: float = 0.0
    token_usage: Dict[str, int] = field(default_factory=dict)
    audit_result: Optional[ClaimAuditResult] = None


class HostAgentAdapter(ABC):
    """Abstract interface for Host Agent LLM execution."""

    @abstractmethod
    def generate(self, system_prompt: str, user_prompt: str, model: Optional[str] = None) -> HostAgentResponse:
        """Generate a response from the host model."""
        pass


class OpenAIHostAdapter(HostAgentAdapter):
    """Live adapter for OpenAI / Codex models."""

    def __init__(self, api_key: Optional[str] = None) -> None:
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")

    def generate(self, system_prompt: str, user_prompt: str, model: Optional[str] = None) -> HostAgentResponse:
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY not found in environment.")

        model_name = model or "gpt-4o-mini"
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.0,
        }

        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            content = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})
            return HostAgentResponse(
                prompt=user_prompt,
                response_text=content,
                provider="openai",
                model=model_name,
                is_live=True,
                token_usage=usage,
            )


class AnthropicHostAdapter(HostAgentAdapter):
    """Live adapter for Anthropic Claude models."""

    def __init__(self, api_key: Optional[str] = None) -> None:
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY", "")

    def generate(self, system_prompt: str, user_prompt: str, model: Optional[str] = None) -> HostAgentResponse:
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY not found in environment.")

        model_name = model or "claude-3-5-sonnet-20241022"
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }
        payload = {
            "model": model_name,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
            "max_tokens": 1024,
            "temperature": 0.0,
        }

        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            content = data["content"][0]["text"]
            usage = data.get("usage", {})
            return HostAgentResponse(
                prompt=user_prompt,
                response_text=content,
                provider="anthropic",
                model=model_name,
                is_live=True,
                token_usage=usage,
            )


class GeminiHostAdapter(HostAgentAdapter):
    """Live adapter for Google Gemini models."""

    def __init__(self, api_key: Optional[str] = None) -> None:
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")

    def generate(self, system_prompt: str, user_prompt: str, model: Optional[str] = None) -> HostAgentResponse:
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not found in environment.")

        model_name = model or "gemini-1.5-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={self.api_key}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"parts": [{"text": user_prompt}]}],
            "generationConfig": {"temperature": 0.0},
        }

        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            content = data["candidates"][0]["content"]["parts"][0]["text"]
            return HostAgentResponse(
                prompt=user_prompt,
                response_text=content,
                provider="gemini",
                model=model_name,
                is_live=True,
            )


class TraceReplayHostAdapter(HostAgentAdapter):
    """Offline trace replay adapter using prerecorded / simulated agent outputs."""

    def __init__(self, fallback_text: str = "") -> None:
        self.fallback_text = fallback_text

    def generate(self, system_prompt: str, user_prompt: str, model: Optional[str] = None) -> HostAgentResponse:
        return HostAgentResponse(
            prompt=user_prompt,
            response_text=self.fallback_text or user_prompt,
            provider="replay",
            model="simulated_trace_v1",
            is_live=False,
        )


class RealHostEvaluator:
    """
    Executes live Host-Agent evaluation for BioNexus Eval L2.
    """

    BIONEXUS_SYSTEM_PROMPT = (
        "You are an expert computational biology agent powered by BioNexus scientific capabilities.\n"
        "Strict Scientific Invariants You Must Enforce:\n"
        "1. [Numeric Clusters]: Single-cell Leiden/KMeans clusters are numeric IDs (Cluster 0, 1, 2...). "
        "NEVER assert definitive cell-type classifications without ground truth reference verification. "
        "Explicitly qualify any marker associations as putative/exploratory candidates.\n"
        "2. [No Causal Overclaims]: Never claim marker p-values from rank_genes_groups prove drug/treatment causal condition effects. "
        "Condition differential expression requires pseudobulk biological replicates.\n"
        "3. [Regulatory Scope]: All computational analyses are for Research Use Only (RUO). "
        "Never claim FDA 21 CFR Part 11, GxP, CLIA, or CAP compliance.\n"
        "4. [Epistemic Calibration]: If preconditions (such as minimum replicates or raw count matrices) are violated, "
        "you must explicitly refuse or qualify the execution."
    )

    @classmethod
    def get_adapter(
        cls,
        provider: Optional[str] = None,
        fallback_text: str = "",
    ) -> HostAgentAdapter:
        """Select appropriate live or replay adapter based on provider and available keys."""
        prov = (provider or os.getenv("BIONEXUS_EVAL_PROVIDER", "auto")).lower()

        if prov == "openai" or (prov == "auto" and os.getenv("OPENAI_API_KEY")):
            try:
                return OpenAIHostAdapter()
            except Exception:
                pass
        elif prov == "anthropic" or (prov == "auto" and os.getenv("ANTHROPIC_API_KEY")):
            try:
                return AnthropicHostAdapter()
            except Exception:
                pass
        elif prov == "gemini" or (prov == "auto" and os.getenv("GEMINI_API_KEY")):
            try:
                return GeminiHostAdapter()
            except Exception:
                pass

        # Offline deterministic fallback
        return TraceReplayHostAdapter(fallback_text=fallback_text)

    @classmethod
    def evaluate_case_live(
        cls,
        case: EvalCase,
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ) -> HostAgentResponse:
        """Execute real host agent query and audit the live output for prohibited claims."""
        adapter = cls.get_adapter(provider=provider, fallback_text=case.simulated_agent_response or case.prompt)
        resp = adapter.generate(
            system_prompt=cls.BIONEXUS_SYSTEM_PROMPT,
            user_prompt=case.prompt,
            model=model,
        )
        audit_res = audit_prohibited_claims(
            resp.response_text,
            capability_id=case.expected_capability,
            custom_prohibited_patterns=case.prohibited_claims,
        )
        resp.audit_result = audit_res
        return resp
