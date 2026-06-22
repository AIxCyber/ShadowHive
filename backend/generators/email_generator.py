import asyncio
from datetime import UTC, datetime, timedelta

from backend.ai import get_provider_for_module
from backend.utils.config import Config
from backend.utils.json_parser import extract_json

EMAIL_PROMPT = """You are an email system generating realistic internal corporate emails.

Company: {company_name}
Industry: {industry}
Sender: {sender_name} ({sender_title}, {sender_dept})
Recipient: {recipient_name} ({recipient_title}, {recipient_dept})
Subject hint: {subject_hint}
Thread: {thread_status}

Return a JSON object with:
- subject: email subject line (professional, realistic)
- body: email body text (2-4 paragraphs, realistic corporate tone)
- is_internal: true

ONLY return valid JSON, no other text."""


EMAIL_TOPICS = [
    "Q4 budget review meeting",
    "Project timeline update",
    "New hire onboarding",
    "Quarterly performance review",
    "Team building event",
    "Security policy reminder",
    "Product launch planning",
    "Client feedback summary",
    "Office renovation update",
    "Vendor selection process",
    "Compliance training deadline",
    "Sprint retrospective",
    "Department restructuring",
    "Holiday schedule",
    "New tool rollout",
    "Architecture review request",
    "Marketing campaign results",
    "Customer success story",
]


async def generate_email(
    company_name: str,
    industry: str,
    sender: dict,
    recipient: dict,
    subject_hint: str | None = None,
    is_reply: bool = False,
) -> dict:
    provider = get_provider_for_module("email_generation", Config.all())
    topic = subject_hint or EMAIL_TOPICS[hash(str(sender) + str(recipient)) % len(EMAIL_TOPICS)]
    prompt = EMAIL_PROMPT.format(
        company_name=company_name,
        industry=industry,
        sender_name=f"{sender['first_name']} {sender['last_name']}",
        sender_title=sender.get("title", "Employee"),
        sender_dept=sender.get("department", "General"),
        recipient_name=f"{recipient['first_name']} {recipient['last_name']}",
        recipient_title=recipient.get("title", "Employee"),
        recipient_dept=recipient.get("department", "General"),
        subject_hint=topic,
        thread_status="This is a reply in an existing thread" if is_reply else "This starts a new thread",
    )
    response = await provider.generate(
        prompt=prompt,
        system="You generate realistic internal corporate email communications. Use appropriate tone, signatures, and corporate language.",
        temperature=0.8,
    )
    try:
        data = extract_json(response.content)
    except Exception:
        return {"error": "Failed to parse email generation", "raw": response.content}
    data["sent_at"] = (datetime.now(UTC) - timedelta(minutes=hash(str(prompt)) % 1440)).isoformat()
    return data


async def generate_email_thread(
    company_name: str,
    industry: str,
    participants: list[dict],
    depth: int = 3,
) -> list[dict]:
    tasks = []
    for i in range(depth):
        sender = participants[i % len(participants)]
        recipient = participants[(i + 1) % len(participants)]
        tasks.append(
            generate_email(
                company_name=company_name,
                industry=industry,
                sender=sender,
                recipient=recipient,
                is_reply=i > 0,
            )
        )
    results = await asyncio.gather(*tasks)
    return [e for e in results if "error" not in e]
