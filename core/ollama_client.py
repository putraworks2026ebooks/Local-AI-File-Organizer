"""
Ollama API client for local AI file classification.
Communicates with a locally running Ollama server.
"""

import json
import requests
from typing import Optional


class OllamaClient:
    """Client for communicating with a local Ollama server."""

    def __init__(self, server_url: str = "http://localhost:11434",
                 model: str = "llama3.1", timeout: int = 60,
                 temperature: float = 0.1, max_tokens: int = 100):
        self.server_url = server_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.temperature = temperature
        self.max_tokens = max_tokens

    def update_settings(self, server_url: str = None, model: str = None,
                        timeout: int = None, temperature: float = None,
                        max_tokens: int = None) -> None:
        """Update client settings."""
        if server_url is not None:
            self.server_url = server_url.rstrip("/")
        if model is not None:
            self.model = model
        if timeout is not None:
            self.timeout = timeout
        if temperature is not None:
            self.temperature = temperature
        if max_tokens is not None:
            self.max_tokens = max_tokens

    def is_available(self) -> bool:
        """Check if the Ollama server is reachable."""
        try:
            resp = requests.get(f"{self.server_url}/api/tags", timeout=5)
            return resp.status_code == 200
        except requests.RequestException:
            return False

    def list_models(self) -> list[str]:
        """List available models on the Ollama server."""
        try:
            resp = requests.get(f"{self.server_url}/api/tags", timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                return [m["name"] for m in data.get("models", [])]
        except requests.RequestException:
            pass
        return []

    def generate(self, prompt: str, system: str = None,
                  stream: bool = False) -> Optional[str]:
        """Send a generate request to Ollama."""
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": stream,
            "options": {
                "temperature": self.temperature,
                "num_predict": self.max_tokens,
            },
        }
        if system:
            payload["system"] = system

        try:
            resp = requests.post(
                f"{self.server_url}/api/generate",
                json=payload,
                timeout=self.timeout,
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("response", "")
        except requests.RequestException as e:
            raise ConnectionError(f"Ollama request failed: {e}")

        return None

    def chat(self, messages: list[dict], stream: bool = False,
             use_json_format: bool = True, num_predict: int = None) -> Optional[str]:
        """Send a chat request to Ollama.

        Args:
            messages: list of {role, content} dicts.
            stream: if True, stream response (not used here).
            use_json_format: if True, force JSON output mode. Set False
                for tasks where the model might not know the answer and
                would return empty in forced JSON mode.
            num_predict: override max_tokens for this request.
        """
        import logging
        logger = logging.getLogger(__name__)

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": stream,
            "options": {
                "temperature": self.temperature,
                "num_predict": num_predict if num_predict else self.max_tokens,
            },
        }
        if use_json_format:
            payload["format"] = "json"

        try:
            resp = requests.post(
                f"{self.server_url}/api/chat",
                json=payload,
                timeout=self.timeout,
            )
            if resp.status_code == 200:
                data = resp.json()
                message = data.get("message", {})
                content = message.get("content", "")
                if not content:
                    logger.warning(
                        f"Ollama returned empty content. "
                        f"Status: {resp.status_code}, "
                        f"Response: {str(data)[:300]}"
                    )
                return content
            else:
                logger.warning(
                    f"Ollama HTTP {resp.status_code}: {resp.text[:300]}"
                )
        except requests.RequestException as e:
            raise ConnectionError(f"Ollama chat request failed: {e}")

        return None

    def classify_file(self, file_info: dict, categories: list[str],
                      content_summary: str = None) -> Optional[str]:
        """
        Classify a file into one of the given categories using Ollama.

        Args:
            file_info: dict with file_name, extension, metadata, etc.
            categories: list of category names to choose from.
            content_summary: optional text content summary for classification.

        Returns:
            Category name or None on failure.
        """
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
            truncated = content_summary[:500]
            prompt_parts.append(f"Content summary: {truncated}")

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
                # Try to parse JSON response
                result = json.loads(response.strip())
                category = result.get("category", "").strip()
                if category in categories:
                    return category
                # Try case-insensitive match
                for cat in categories:
                    if cat.lower() == category.lower():
                        return cat
                return "Miscellaneous"
            except json.JSONDecodeError:
                # Try to extract category from plain text
                response_clean = response.strip().strip('"').strip("'")
                for cat in categories:
                    if cat.lower() in response_clean.lower():
                        return cat
                return "Miscellaneous"

        return None

    def batch_classify(self, files: list[dict], categories: list[str],
                       content_summaries: dict = None,
                       progress_callback: callable = None) -> dict[str, str]:
        """
        Classify multiple files. Returns {file_path: category}.
        """
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
        """Pull a model on the Ollama server."""
        try:
            resp = requests.post(
                f"{self.server_url}/api/pull",
                json={"name": model_name, "stream": False},
                timeout=300,
            )
            return resp.status_code == 200
        except requests.RequestException:
            return False
