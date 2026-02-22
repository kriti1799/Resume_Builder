import os
from pathlib import Path


class LLMClient:
    def __init__(self, provider="openai", api_key=None, model=None):
        self.provider = (provider or "openai").lower()
        self.api_key = api_key
        self.model = model

    @staticmethod
    def _load_env_file():
        env_path = Path.cwd() / ".env"
        if not env_path.exists():
            return
        try:
            for line in env_path.read_text(encoding="utf-8").splitlines():
                raw = line.strip()
                if not raw or raw.startswith("#") or "=" not in raw:
                    continue
                key, val = raw.split("=", 1)
                os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))
        except Exception:
            pass

    def _resolve_openai_key(self):
        self._load_env_file()
        return self.api_key or os.environ.get("OPENAI_API_KEY")

    def _resolve_gemini_key(self):
        self._load_env_file()
        return (
            self.api_key
            or os.environ.get("GEMINI_API_KEY")
            or os.environ.get("GOOGLE_API_KEY")
        )

    def _generate_with_gemini(self, prompt: str):
        try:
            from google import genai
        except ImportError as e:
            raise RuntimeError(
                "Gemini provider requested but `google-genai` is not installed."
            ) from e

        api_key = self._resolve_gemini_key()
        if not api_key:
            raise RuntimeError("Missing GEMINI_API_KEY/GOOGLE_API_KEY for upskill agent.")

        model = self.model or "gemini-2.0-flash"
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model,
            contents=[{"parts": [{"text": prompt}]}],
        )
        return response.text if response and getattr(response, "text", None) else ""

    def _generate_with_openai(self, prompt: str, system=None, temperature=0.2):
        api_key = self._resolve_openai_key()
        if not api_key:
            raise RuntimeError("Missing OPENAI_API_KEY for upskill agent.")

        model = self.model or "gpt-4o-mini"

        # Try official OpenAI SDK first.
        try:
            from openai import OpenAI

            client = OpenAI(api_key=api_key)
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})
            response = client.chat.completions.create(
                model=model,
                temperature=temperature,
                messages=messages,
            )
            return (response.choices[0].message.content or "").strip()
        except ImportError:
            pass

        # Fallback to langchain-openai if available.
        try:
            from langchain_openai import ChatOpenAI

            llm = ChatOpenAI(model=model, temperature=temperature, api_key=api_key)
            full_prompt = f"{system}\n\n{prompt}" if system else prompt
            response = llm.invoke(full_prompt)
            return getattr(response, "content", "") or ""
        except ImportError as e:
            raise RuntimeError(
                "Neither `openai` nor `langchain-openai` is installed."
            ) from e

    def generate(self, prompt, system=None, temperature=0.2):
        if self.provider == "gemini":
            return self._generate_with_gemini(prompt)
        return self._generate_with_openai(prompt, system=system, temperature=temperature)
