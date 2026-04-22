from flask import Blueprint, request, jsonify
from groq import Groq
import os
from dotenv import load_dotenv

load_dotenv()

generate_bp = Blueprint('generate', __name__)

client = Groq(api_key=os.getenv('GROQ_API_KEY'))
MODEL  = 'llama-3.3-70b-versatile'


@generate_bp.route('/generate/organization-description', methods=['POST'])
def generate_organization_description():
    data = request.get_json()

    name     = data.get('name', '').strip()
    industry = data.get('industry', '').strip()
    country  = data.get('country', '').strip()
    size     = data.get('size_band', '').strip()

    if not name or not industry:
        return jsonify({'error': 'name and industry are required'}), 400

    # Build context string
    context_parts = [f"Organization: {name}", f"Industry: {industry}"]
    if country:  context_parts.append(f"Country: {country}")
    if size:     context_parts.append(f"Size: {size} employees")
    context = ' | '.join(context_parts)

    prompt = f"""You are a business analyst writing a concise company profile for a data governance assessment report.

Given the following organization details:
{context}

Write 2-3 sentences describing:
- What the organization does (use your knowledge if you recognize the company, otherwise infer from the industry)
- Its scale and operational context

If you recognize this organization from your training data, use that knowledge to be specific.
If you don't recognize it, infer logically from the industry and size provided.
Be factual, professional, and concise. Write in third person.
Return only the description text, no preamble or labels."""

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{'role': 'user', 'content': prompt}],
            temperature=0.5,
            max_tokens=200,
        )
        description = response.choices[0].message.content.strip()
        return jsonify({'description': description}), 200

    except Exception as e:
        return jsonify({'error': f'Generation failed: {str(e)}'}), 500