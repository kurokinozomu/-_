"""LLM プロバイダ。

優先順位 (AIVIDEO_LLM=auto):
  1. claude CLI (`claude -p`)  … Claude Code のログイン済みサブスクリプションを利用。API 従量課金なし。
  2. Anthropic API             … 有料。ANTHROPIC_API_KEY と AIVIDEO_ALLOW_PAID=1 の両方が必要。
  3. None (オフライン)          … planner 側でテンプレート台本にフォールバック。
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile

from .config import Settings, log


class LLMError(RuntimeError):
    pass


class ClaudeCLI:
    name = "claude-cli"

    def __init__(self, settings: Settings):
        self.settings = settings

    @staticmethod
    def available() -> bool:
        return shutil.which("claude") is not None

    def complete(self, system: str, prompt: str, timeout: int = 600) -> str:
        full = f"{system}\n\n---\n\n{prompt}"
        # プロジェクトの CLAUDE.md 等を読ませないよう、空の一時ディレクトリで実行
        with tempfile.TemporaryDirectory() as tmp:
            proc = subprocess.run(
                ["claude", "-p", "--output-format", "text"],
                input=full, capture_output=True, text=True, timeout=timeout, cwd=tmp,
            )
        if proc.returncode != 0 or not proc.stdout.strip():
            raise LLMError(f"claude CLI failed: {proc.stderr.strip()[:500]}")
        return proc.stdout


class AnthropicAPI:
    name = "anthropic-api"

    def __init__(self, settings: Settings):
        self.settings = settings
        import anthropic  # 任意依存

        self.client = anthropic.Anthropic()  # ANTHROPIC_API_KEY を環境変数から読む

    @staticmethod
    def available(settings: Settings) -> bool:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return False
        try:
            import anthropic  # noqa: F401
        except ImportError:
            log("anthropic パッケージ未インストール: pip install anthropic")
            return False
        return True

    def complete(self, system: str, prompt: str, timeout: int = 600) -> str:
        with self.client.beta.messages.stream(
            model=self.settings.claude_model,
            max_tokens=32000,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            output_config={"effort": "medium"},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        ) as stream:
            msg = stream.get_final_message()
        if msg.stop_reason == "refusal":
            raise LLMError("Claude declined the request")
        text = "".join(b.text for b in msg.content if b.type == "text")
        if not text.strip():
            raise LLMError("empty response")
        return text


def get_llm(settings: Settings):
    choice = settings.llm
    if choice in ("auto", "claude-cli") and ClaudeCLI.available():
        return ClaudeCLI(settings)
    if choice in ("auto", "anthropic") and AnthropicAPI.available(settings):
        if not settings.allow_paid:
            log("ANTHROPIC_API_KEY はありますが、有料APIの利用が許可されていません "
                "(AIVIDEO_ALLOW_PAID=1 または --allow-paid で許可)。")
        else:
            return AnthropicAPI(settings)
    if choice == "offline":
        return None
    if choice not in ("auto", "offline"):
        log(f"LLM '{choice}' は利用できません。オフラインテンプレートを使用します。")
    return None


def extract_json(text: str):
    """応答テキストから JSON を取り出す（```json フェンスや前置きを許容）。"""
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1)
    start = min([i for i in (text.find("{"), text.find("[")) if i >= 0], default=-1)
    if start < 0:
        raise LLMError("JSON not found in response")
    end = max(text.rfind("}"), text.rfind("]"))
    return json.loads(text[start:end + 1])


def complete_json(llm, system: str, prompt: str, retries: int = 2):
    last = None
    for attempt in range(retries + 1):
        try:
            p = prompt if attempt == 0 else (
                prompt + "\n\n注意: 前回の出力は JSON として解析できませんでした。"
                "説明文なしで、有効な JSON のみを出力してください。")
            return extract_json(llm.complete(system, p))
        except (LLMError, json.JSONDecodeError, subprocess.TimeoutExpired) as e:
            last = e
            log(f"LLM 応答の解析に失敗 ({attempt + 1}/{retries + 1}): {e}")
    raise LLMError(f"LLM failed: {last}")
