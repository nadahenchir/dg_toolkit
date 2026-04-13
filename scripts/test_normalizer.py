from dotenv import load_dotenv
load_dotenv()

from app.services.layer2.normalizer import generate_company_description, normalize_industry
# Test 1 — known industry
desc = generate_company_description(
    name="STAR Insurance",
    industry="Insurance",
    industry_other=None,
    size_band="SME",
    country="Tunisia"
)
print("Insurance:", desc)
print()

# Test 2 — Other with free text
desc = generate_company_description(
    name="Gide Loyrette",
    industry="Other",
    industry_other="law firm",
    size_band="Large",
    country="Tunisia"
)
print("Legal:", desc)
print()

# Test 3 — normalization still works
print("Normalized:", normalize_industry("banque d'affaires"))