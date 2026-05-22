"""
RAG 端到端问答 — 来自项目1

检索 → 拼接上下文 → 生成答案
当前使用模板式摘要，后续可替换为 DeepSeek/Qwen API。
项目2 没有此功能。
"""
from __future__ import annotations

from .retrieval import HybridRetriever


def rag_answer(retriever: HybridRetriever, question: str, top_k: int = 3) -> str:
    """
    端到端 RAG：检索 → 拼接上下文 → 生成答案

    当前使用基于模板的摘要式回答（不依赖外部 API）。
    后续可替换为智谱/千问/DeepSeek API 获得更好效果。
    """
    results = retriever.search_hybrid(question, top_k=top_k)

    if not results:
        return "未找到相关内容。"

    # 拼接检索到的上下文
    context_parts = []
    for i, r in enumerate(results):
        chunk = r["chunk"]
        page_nums = chunk.metadata.get("page_nums", "N/A")
        context_parts.append(
            f"[来源{i+1}] (第{page_nums}页, "
            f"相关度={r['rrf_score']:.3f})\n{chunk.text}"
        )
    context = "\n\n".join(context_parts)

    # 构建回答（基于模板，后续可接入 LLM API）
    answer = f"""
📋 问题：{question}

📖 基于检索到的 {len(results)} 段相关内容：

{context}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💡 提示：当前为检索模式（展示原文片段）。
   接入 DeepSeek/Qwen API 后可生成自然语言摘要答案。
"""
    return answer


def build_llm_prompt(question: str, context: str) -> str:
    """
    构建 LLM 提示词（预留接口）。
    当接入大模型 API 后使用。
    """
    return f"""你是一个动力装备领域的专业知识助手。请根据以下检索到的参考资料回答用户的问题。

## 参考资料
{context}

## 用户问题
{question}

## 要求
1. 只基于参考资料回答，不要编造
2. 如果参考资料不足以回答，请明确说明
3. 引用来源时标注 [来源X]
4. 使用专业但易懂的语言
"""
