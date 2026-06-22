import asyncio

from backend.ai import get_provider_for_module
from backend.utils.config import Config
from backend.utils.json_parser import extract_json

DOC_TYPES = {
    "financial_report": "Generate a financial report document with realistic quarterly figures",
    "proposal": "Generate a professional business proposal document",
    "internal_memo": "Generate an internal company memo",
    "meeting_notes": "Generate meeting notes from a corporate meeting",
    "technical_spec": "Generate a technical specification document",
    "roadmap": "Generate a product/strategy roadmap document",
    "policy": "Generate an internal company policy document",
    "contract": "Generate a redacted contract draft",
}


DOCUMENT_PROMPT = """You are a document generation system for deception operations.

Company: {company_name}
Industry: {industry}
Document Type: {doc_type}
Description: {description}
Author: {author_name} ({author_title}, {author_dept})

Return a JSON object with:
- title: realistic document title
- content: 3-6 paragraphs of realistic document content
- file_path: realistic file path (e.g., /shared/documents/finance/Q4_report_2024.pdf)

ONLY return valid JSON, no other text."""


async def generate_document(
    company_name: str,
    industry: str,
    doc_type: str,
    author: dict,
    description: str | None = None,
) -> dict:
    provider = get_provider_for_module("document_generation", Config.all())
    doc_info = DOC_TYPES.get(doc_type, {"description": f"Generate a {doc_type} document"})
    desc = description or doc_info
    prompt = DOCUMENT_PROMPT.format(
        company_name=company_name,
        industry=industry,
        doc_type=doc_type.replace("_", " ").title(),
        description=desc,
        author_name=f"{author['first_name']} {author['last_name']}",
        author_title=author.get("title", "Employee"),
        author_dept=author.get("department", "General"),
    )
    response = await provider.generate(
        prompt=prompt,
        system="You generate realistic business documents for corporate environments. Use appropriate formatting, headers, and professional language.",
        temperature=0.7,
        max_tokens=3072,
    )
    try:
        data = extract_json(response.content)
    except Exception:
        return {"error": "Failed to parse document generation", "raw": response.content}
    data["doc_type"] = doc_type
    return data


async def generate_document_set(
    company_name: str,
    industry: str,
    author: dict,
    types: list[str] | None = None,
) -> list[dict]:
    if types is None:
        types = list(DOC_TYPES.keys())
    tasks = [
        generate_document(
            company_name=company_name,
            industry=industry,
            doc_type=dt,
            author=author,
        )
        for dt in types
    ]
    results = await asyncio.gather(*tasks)
    return [d for d in results if "error" not in d]
