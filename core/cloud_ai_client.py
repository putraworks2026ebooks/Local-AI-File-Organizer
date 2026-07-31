"""
Cloud AI client for file classification and geocoding.
Uses OpenAI-compatible API format — works with OpenAI, Groq, OpenRouter,
Together AI, LM Studio, and any provider that supports /chat/completions.
"""

import json
import requests
from typing import Optional


class CloudAIClient:
    """Client for OpenAI-compatible cloud AI APIs."""

    def __init__(self, api_key: str = "", base_url: str = "https://api.openai.com/v1",
                 model: str = "gpt-4o-mini", timeout: int = 60,
                 temperature: float = 0.1, max_tokens: int = 500):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.temperature = temperature
        self.max_tokens = max_tokens

    def update_settings(self, api_key: str = None, base_url: str = None,
                        model: str = None, timeout: int = None,
                        temperature: float = None, max_tokens: int = None) -> None:
        """Update client settings."""
        if api_key is not None:
            self.api_key = api_key
        if base_url is not None:
            self.base_url = base_url.rstrip("/")
        if model is not None:
            self.model = model
        if timeout is not None:
            self.timeout = timeout
        if temperature is not None:
            self.temperature = temperature
        if max_tokens is not None:
            self.max_tokens = max_tokens

    def is_available(self) -> bool:
        """Check if the cloud API is reachable and API key is set."""
        if not self.api_key:
            return False
        try:
            resp = requests.get(
                f"{self.base_url}/models",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=10,
            )
            return resp.status_code == 200
        except requests.RequestException:
            return False

    def list_models(self) -> list[str]:
        """List available models from the cloud API."""
        if not self.api_key:
            return []
        try:
            resp = requests.get(
                f"{self.base_url}/models",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                models = data.get("data", [])
                return [m.get("id", "") for m in models if m.get("id")]
        except requests.RequestException:
            pass
        return []

    def chat(self, messages: list[dict], stream: bool = False,
             use_json_format: bool = True, num_predict: int = None) -> Optional[str]:
        """Send a chat request to the cloud API (OpenAI-compatible).

        Args:
            messages: list of {role, content} dicts.
            stream: ignored (always non-streaming).
            use_json_format: if True, request JSON output format.
            num_predict: override max_tokens for this request.
        """
        import logging
        logger = logging.getLogger(__name__)

        if not self.api_key:
            logger.warning("Cloud AI: no API key configured")
            return None

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": num_predict if num_predict else self.max_tokens,
        }
        if use_json_format:
            payload["response_format"] = {"type": "json_object"}

        try:
            resp = requests.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=self.timeout,
            )
            if resp.status_code == 200:
                data = resp.json()
                choices = data.get("choices", [])
                if choices:
                    content = choices[0].get("message", {}).get("content", "")
                    if not content:
                        logger.warning(
                            f"Cloud AI returned empty content. "
                            f"Response: {str(data)[:300]}"
                        )
                    return content
                else:
                    logger.warning(f"Cloud AI: no choices in response: {str(data)[:300]}")
            else:
                logger.warning(
                    f"Cloud AI HTTP {resp.status_code}: {resp.text[:300]}"
                )
        except requests.RequestException as e:
            logger.warning(f"Cloud AI request failed: {e}")

        return None

    def classify_file(self, file_info: dict, categories: list[str],
                      content_summary: str = None) -> Optional[str]:
        """Classify a file into one of the given categories."""
        categories_str = ", ".join(categories)
        file_name = file_info.get("file_name", "unknown")
        extension = file_info.get("extension", "")
        metadata = file_info.get("metadata", {})

        prompt_parts = [
            f"File name: {file_name}",
            f"Extension: {extension}",
        ]
        if metadata:
            prompt_parts.append(f"Metadata: {json.dumps(metadata, indent=2)}")
        if content_summary:
            prompt_parts.append(f"Content summary: {content_summary[:500]}")

        prompt_parts.append(f"\nAvailable categories: {categories_str}")
        prompt_parts.append(
            "\nYou are a professional file organizer. Based on the filename, extension, "
            "metadata, and available content, return only the best category from the "
            "configured category list. If uncertain, return Miscellaneous."
        )
        prompt_parts.append('\nReturn JSON only: {"category": "<category_name>"}')

        prompt = "\n".join(prompt_parts)
        system_msg = (
            "You are a professional file organizer. Analyze file information and classify "
            "it into the most appropriate category. Return only valid JSON with a 'category' key. "
            "Be precise and consistent with classifications."
        )

        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": prompt},
        ]

        response = self.chat(messages)

        if response:
            try:
                result = json.loads(response.strip())
                category = result.get("category", "").strip()
                if category in categories:
                    return category
                for cat in categories:
                    if cat.lower() == category.lower():
                        return cat
                return "Miscellaneous"
            except json.JSONDecodeError:
                response_clean = response.strip().strip('"').strip("'")
                for cat in categories:
                    if cat.lower() in response_clean.lower():
                        return cat
                return "Miscellaneous"
        return None

    def batch_classify(self, files: list[dict], categories: list[str],
                       content_summaries: dict = None,
                       progress_callback: callable = None) -> dict[str, str]:
        """Classify multiple files. Returns {file_path: category}."""
        results = {}
        total = len(files)
        content_summaries = content_summaries or {}

        for i, file_info in enumerate(files):
            file_path = file_info.get("file_path", file_info.get("file_name", str(i)))
            summary = content_summaries.get(file_path)
            category = self.classify_file(file_info, categories, summary)
            if category:
                results[file_path] = category
            if progress_callback:
                progress_callback(i + 1, total)
        return results

    def pull_model(self, model_name: str) -> bool:
        """Not supported for cloud APIs — models are already available."""
        return True
