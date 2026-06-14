from typing import List, Dict, Optional
import re
from dataclasses import dataclass

from ..database import get_db, Conversation, Message


MAX_HISTORY_TOKENS = 2000
MAX_HISTORY_ROUNDS = 3


def _estimate_tokens(text: str) -> int:
    return len(text) // 2


def get_conversation_history(
    conversation_id: str,
    max_rounds: int = MAX_HISTORY_ROUNDS,
    max_tokens: int = MAX_HISTORY_TOKENS
) -> List[Dict]:
    db = next(get_db())
    messages = (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())
        .limit(max_rounds * 2)
        .all()
    )
    messages = list(reversed(messages))

    result = []
    total_tokens = 0

    for msg in messages:
        msg_tokens = _estimate_tokens(msg.content)
        if total_tokens + msg_tokens > max_tokens and len(result) >= 4:
            break
        result.append({
            "role": msg.role,
            "content": msg.content
        })
        total_tokens += msg_tokens

    return result


PRONOUN_PATTERNS = [
    r"^(他|她|它|这|那|这个|那个|这些|那些|该|此)",
    r"^(他的|她的|它的|这个的|那个的)",
    r"^作者是|^作者是谁|^其作者|^它的作者",
    r"^它的|^他的|^她的",
]


def is_pronoun_query(question: str) -> bool:
    stripped = question.strip()
    for pattern in PRONOUN_PATTERNS:
        if re.match(pattern, stripped):
            return True
    if len(stripped) < 10 and stripped.endswith("？") or stripped.endswith("?"):
        if "什么" in stripped or "谁" in stripped or "哪" in stripped:
            return True
    return False


def complete_question(question: str, history: List[Dict]) -> str:
    if not history:
        return question
    if not is_pronoun_query(question):
        return question

    user_messages = [h for h in history if h["role"] == "user"]
    if not user_messages:
        return question

    last_user = user_messages[-1]["content"]

    entities = _extract_key_entities(last_user)
    if entities:
        main_entity = entities[0]
        rewritten = question
        for pronoun in ["它", "他", "她", "这", "那", "这个", "那个", "该", "此"]:
            if rewritten.startswith(pronoun):
                rewritten = main_entity + rewritten[len(pronoun):]
                break
        if "它的" in rewritten:
            rewritten = rewritten.replace("它的", f"{main_entity}的")
        if "其" in rewritten:
            rewritten = rewritten.replace("其", f"{main_entity}的")
        return rewritten

    return question


def _extract_key_entities(text: str) -> List[str]:
    import re
    cleaned = re.sub(r'[？?！!。，,、；;：:]', ' ', text)
    words = [w for w in cleaned.split() if len(w) > 1]

    quoted = re.findall(r'"([^"]+)"|\'([^\']+)\'|《([^》]+)》', text)
    entities = []
    for groups in quoted:
        for g in groups:
            if g:
                entities.append(g)

    if "是" in text:
        parts = text.split("是")
        if len(parts) > 1:
            subject = parts[0].strip()
            if subject and len(subject) < 30:
                entities.append(subject)

    if words:
        for w in words:
            if w not in entities and len(w) > 2:
                entities.append(w)
                break

    return entities
