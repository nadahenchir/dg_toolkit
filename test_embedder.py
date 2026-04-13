from app.services.layer2.embedder import embed_organization, compute_org_similarity
import numpy as np

orgs = {
    "STB (Banking SME)":          embed_organization("Banking",      "Commercial banking, trade finance, SME lending, digital banking and financial advisory services"),
    "Attijari (Banking Large)":   embed_organization("Banking",      "Retail and corporate banking, mortgage loans, deposit accounts, digital banking and wealth management"),
    "BIAT (Banking Enterprise)":  embed_organization("Banking",      "Corporate and retail banking, investment services, trade finance, digital banking and asset management"),
    "STAR Insurance (SME)":       embed_organization("Insurance",    "Insurance products including life insurance, property coverage, risk assessment and claims management"),
    "COMAR (Insurance Ent)":      embed_organization("Insurance",    "Multi-line insurance, reinsurance, corporate risk, marine cargo, fire and accident coverage"),
    "Ooredoo (Telecom Large)":    embed_organization("Telecom",      "Mobile telecommunications, internet services, digital solutions, network infrastructure and enterprise connectivity"),
    "Tunisie Telecom (Ent)":      embed_organization("Telecom",      "Fixed line and mobile telecommunications, broadband internet, enterprise solutions and digital infrastructure"),
    "STEG (Energy Ent)":          embed_organization("Energy",       "Energy production, electricity distribution, gas supply, infrastructure management and utility services"),
    "Carrefour (Retail Large)":   embed_organization("Retail",       "Retail commerce, consumer goods distribution, supply chain management, e-commerce and customer loyalty programs"),
    "Clinique (Healthcare SME)":  embed_organization("Healthcare",   "Private healthcare, medical consultations, clinical services, patient management and diagnostic imaging"),
    "McKinsey (Consulting)":      embed_organization("Other",        "Management consulting, strategy advisory, digital transformation, organizational change and business process optimization"),
    "Publicis (Marketing)":       embed_organization("Other",        "Advertising agency, brand strategy, digital marketing, media planning, creative campaigns and social media management"),
    "Gide (Legal)":               embed_organization("Other",        "Corporate law firm, M&A advisory, contract law, litigation, compliance and international legal services"),
    "Sodexo (Food Services)":     embed_organization("Other",        "Facilities management, food services, corporate catering, cafeteria operations and workplace experience"),
}

# Test: STB vs everyone
current    = orgs["STB (Banking SME)"]
others     = {k: v for k, v in orgs.items() if k != "STB (Banking SME)"}
past_keys  = list(others.keys())
past_vecs  = np.array([others[k] for k in past_keys])

sims = compute_org_similarity(current, past_vecs)

print("STB (Banking SME) vs:\n")
for k, s in sorted(zip(past_keys, sims), key=lambda x: -x[1]):
    print(f"  {k:<35} {round(s, 3)}")