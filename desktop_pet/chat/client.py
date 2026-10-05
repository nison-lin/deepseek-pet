"""DeepSeek 对话客户端（与界面无关）。

DeepSeek 官方 API 兼容 OpenAI 协议，因此直接使用 openai SDK。
"""
from typing import Iterator

from openai import OpenAI


class DeepSeekClient:
    def __init__(self, api_key: str, base_url: str = "https://api.deepseek.com",
                 model: str = "deepseek-chat", timeout: float = 60.0):
        self.model = model
        self._client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)

    def stream_chat(self, messages: list[dict]) -> Iterator[str]:
        """流式返回回复的文本片段。"""
        stream = self._client.chat.completions.create(model=self.model, messages=messages, stream=True)
        try:
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        finally:
            stream.close()


class ChatSession:
    """维护对话历史。只有成功的问答才会写入历史。"""

    def __init__(self, system_prompt: str = "", max_history: int = 20):
        self.system_prompt = system_prompt
        self.max_history = max_history
        self.history: list[dict] = []

    def build_messages(self, user_text: str) -> list[dict]:
        messages = [{"role": "system", "content": self.system_prompt}] if self.system_prompt else []
        return messages + self.history + [{"role": "user", "content": user_text}]

    def commit(self, user_text: str, reply: str):
        self.history += [{"role": "user", "content": user_text}, {"role": "assistant", "content": reply}]
        if self.max_history > 0:
            self.history = self.history[-self.max_history:]

    def clear(self):
        self.history.clear()
