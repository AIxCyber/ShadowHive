import asyncio

from backend.ai import get_provider_for_module
from backend.utils.config import Config
from backend.utils.json_parser import extract_json

EMPLOYEE_PROMPT = """You are an HR system generating employee personas for deception operations.

Company: {company_name}
Industry: {industry}
Department: {department}
Title: {title}
Seed: {seed}

Return a JSON object with exactly:
- first_name: realistic first name matching local culture
- last_name: realistic last name
- bio: 2-3 sentence professional bio
- skills: array of 3-6 relevant skills
- personality: object with traits (openness, conscientiousness, extraversion, agreeableness, neuroticism) each 1-100
- phone_extension: 3-4 digit string

ONLY return valid JSON, no other text."""


async def generate_employee(
    company_name: str,
    industry: str,
    department: str,
    title: str,
    seed: str | None = None,
) -> dict:
    provider = get_provider_for_module("employee_generation", Config.all())
    prompt = EMPLOYEE_PROMPT.format(
        company_name=company_name,
        industry=industry,
        department=department,
        title=title,
        seed=seed or "default",
    )
    response = await provider.generate(
        prompt=prompt,
        system="You generate realistic employee personas for corporate environments.",
        temperature=0.8,
    )
    try:
        data = extract_json(response.content)
    except Exception:
        return {"error": "Failed to parse employee generation", "raw": response.content}
    data["department"] = department
    data["title"] = title
    return data


async def generate_employees_for_department(
    company_name: str,
    industry: str,
    department: dict,
    count: int = 5,
) -> list[dict]:
    titles = _titles_for_department(department["name"], count)
    tasks = [
        generate_employee(
            company_name=company_name,
            industry=industry,
            department=department["name"],
            title=title,
            seed=f"{department['name']}-{i}",
        )
        for i, title in enumerate(titles)
    ]
    results = await asyncio.gather(*tasks)
    return [e for e in results if "error" not in e]


def _titles_for_department(dept: str, count: int) -> list[str]:
    titles_map = {
        "Engineering": [
            "VP of Engineering",
            "Senior Software Engineer",
            "Software Engineer",
            "DevOps Engineer",
            "QA Engineer",
        ],
        "Marketing": ["CMO", "Marketing Director", "Content Strategist", "Social Media Manager", "Marketing Analyst"],
        "Sales": ["VP of Sales", "Sales Director", "Account Executive", "SDR Manager", "Sales Operations Analyst"],
        "HR": ["CHRO", "HR Director", "Recruiter", "HR Coordinator", "Benefits Specialist"],
        "Finance": ["CFO", "Finance Director", "Financial Analyst", "Accountant", "Payroll Specialist"],
        "Operations": [
            "COO",
            "Operations Manager",
            "Logistics Coordinator",
            "Facilities Manager",
            "Procurement Specialist",
        ],
        "Legal": ["General Counsel", "Corporate Lawyer", "Paralegal", "Compliance Officer", "Contracts Manager"],
        "Product": ["CPO", "Product Director", "Product Manager", "Product Designer", "Product Analyst"],
        "IT": ["CIO", "IT Director", "System Admin", "Network Engineer", "Security Analyst"],
    }
    titles = titles_map.get(dept, ["Director", "Manager", "Associate", "Coordinator", "Analyst"])
    return titles[:count]
