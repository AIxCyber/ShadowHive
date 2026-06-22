from backend.generators.company_generator import generate_company


async def create_full_company(
    industry: str = "Technology",
    size: str = "medium",
    seed: str | None = None,
) -> dict:
    return await generate_company(industry=industry, size=size, seed=seed)
