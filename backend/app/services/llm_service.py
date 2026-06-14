from typing import List, Optional, Dict
import threading
import json
import re

from ..config import settings
from ..schemas import SourceInfo


SYSTEM_PROMPT = """你是一个专业的文档问答助手。请严格基于提供的文档内容回答用户的问题。
规则：
1. 只能使用文档中明确提到的信息，不要编造、猜测或引入外部知识
2. 如果文档中没有相关信息，请明确回答"根据提供的文档内容，无法回答该问题"
3. 回答时需要引用来源，使用[1][2]等格式标注引用的来源段落编号
4. 引用应紧跟在相关事实或观点之后
5. 回答应简洁、准确、结构清晰

文档内容将以[来源X]开头进行标注，X是段落编号。"""


def build_context_prompt(sources: List[SourceInfo]) -> str:
    parts = []
    for i, src in enumerate(sources, 1):
        location = ""
        if src.page_number:
            location = f"（第{src.page_number}页）"
        elif src.paragraph_number:
            location = f"（第{src.paragraph_number}段）"
        parts.append(f"[来源{i}]《{src.document_name}》{location}：\n{src.content}")
    return "\n\n".join(parts)


def build_chat_prompt(
    question: str,
    sources: List[SourceInfo],
    history: Optional[List[Dict]] = None
) -> List[Dict]:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT}
    ]

    if history:
        for msg in history:
            messages.append({
                "role": msg["role"],
                "content": msg["content"]
            })

    context = build_context_prompt(sources)
    user_content = f"参考文档内容：\n\n{context}\n\n用户问题：{question}\n\n请基于文档内容回答问题，并在回答中引用相应的来源编号[1]、[2]等。"
    messages.append({"role": "user", "content": user_content})

    return messages


class LocalLLMService:
    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        self._model = None
        self._tokenizer = None
        self._device = "cpu"

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def _load_model(self):
        if self._model is None:
            try:
                import torch
                from transformers import AutoModelForCausalLM, AutoTokenizer
                self._device = "cuda" if torch.cuda.is_available() else "cpu"
                model_name = settings.LOCAL_LLM_MODEL
                self._tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
                self._model = AutoModelForCausalLM.from_pretrained(
                    model_name,
                    trust_remote_code=True,
                    torch_dtype=torch.float16 if self._device == "cuda" else torch.float32,
                    device_map="auto" if self._device == "cuda" else None
                )
                if self._device == "cpu":
                    self._model = self._model.to(self._device)
            except Exception as e:
                print(f"Failed to load local LLM: {e}")
                raise

    def generate(self, messages: List[Dict], max_tokens: int = 1024, temperature: float = 0.7) -> str:
        self._load_model()
        import torch

        text = self._tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True
        )
        inputs = self._tokenizer(text, return_tensors="pt", truncation=True, max_length=4096)
        inputs = {k: v.to(self._device) for k, v in inputs.items()}

        with torch.no_grad():
            outputs = self._model.generate(
                **inputs,
                max_new_tokens=max_tokens,
                temperature=temperature,
                do_sample=temperature > 0,
                pad_token_id=self._tokenizer.eos_token_id
            )

        generated_ids = outputs[0][inputs["input_ids"].shape[1]:]
        response = self._tokenizer.decode(generated_ids, skip_special_tokens=True)
        return response.strip()


class RemoteLLMService:
    def __init__(self):
        self.api_key = settings.REMOTE_API_KEY
        self.endpoint = settings.REMOTE_API_ENDPOINT
        self.model = settings.REMOTE_MODEL_NAME

    def generate(self, messages: List[Dict], max_tokens: int = 1024, temperature: float = 0.7) -> str:
        import httpx

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature
        }

        with httpx.Client(timeout=120) as client:
            resp = client.post(
                f"{self.endpoint.rstrip('/')}/chat/completions",
                headers=headers,
                json=payload
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()


def get_llm_service():
    if settings.LLM_MODE == "local":
        return LocalLLMService.get_instance()
    else:
        return RemoteLLMService()


def extract_cited_source_indices(answer_text: str) -> List[int]:
    pattern = r'\[(\d+)\]'
    matches = re.findall(pattern, answer_text)
    indices = []
    for m in matches:
        try:
            idx = int(m) - 1
            if idx >= 0 and idx not in indices:
                indices.append(idx)
        except ValueError:
            continue
    return indices


def rewrite_answer_with_links(answer_text: str) -> str:
    return answer_text
