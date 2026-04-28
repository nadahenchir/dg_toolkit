import requests
import json

BASE_URL = "http://127.0.0.1:5000/api"
ASSESSMENT_ID = 58

def answer_questionnaire():
    # Get questionnaire structure
    response = requests.get(f"{BASE_URL}/assessments/{ASSESSMENT_ID}/questionnaire")
    questionnaire = response.json()
    
    options = ["Fully", "Mostly", "Partially", "Slightly", "Not"]
    
    for domain in questionnaire:
        print(f"\nAnswering domain: {domain['domain_name']}")
        for kpi in domain['kpis']:
            kpi_id = kpi['kpi_id']
            answers = []
            
            # Answer Q1 with "Mostly" 
            q1 = kpi['questions'][0]
            q1_answer = "Mostly"
            answers.append({
                "question_id": q1['id'],
                "selected_option": q1_answer
            })
            
            # If gate not triggered, answer remaining questions
            gate_option = "Fully" if kpi['is_inverted'] else "Not"
            gate_triggered = q1_answer == gate_option
            
            if not gate_triggered:
                for q in kpi['questions'][1:]:
                    if not q.get('is_hidden'):
                        answers.append({
                            "question_id": q['id'],
                            "selected_option": "Mostly"
                        })
            
            # Save answers
            resp = requests.post(
                f"{BASE_URL}/assessments/{ASSESSMENT_ID}/answers/kpi/{kpi_id}",
                json={"answers": answers}
            )
            if resp.status_code == 200:
                print(f"  KPI {kpi_id} ({kpi['kpi_name']}): answered")
            else:
                print(f"  KPI {kpi_id} ERROR: {resp.text}")
    
    # Submit assessment
    print("\nSubmitting assessment...")
    submit_resp = requests.post(f"{BASE_URL}/assessments/{ASSESSMENT_ID}/submit")
    print(f"Submit response: {submit_resp.status_code} - {submit_resp.json()}")

if __name__ == "__main__":
    answer_questionnaire()