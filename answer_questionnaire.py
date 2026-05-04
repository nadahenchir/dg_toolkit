import requests

BASE_URL       = "http://127.0.0.1:5000/api"
ASSESSMENT_ID  = 61
LOGIN_EMAIL    = "your@email.com"
LOGIN_PASSWORD = "yourpassword"


def answer_questionnaire():
    session = requests.Session()

    # Authenticate — reuse the cookie for all subsequent calls
    login_resp = session.post(f"{BASE_URL}/auth/login", json={
        "email":    "emnakallel@kpmg.com",
        "password": "test123",
    })
    if login_resp.status_code != 200:
        print(f"Login failed: {login_resp.json()}")
        return
    print("Logged in successfully.")

    # Fetch questionnaire structure
    response = session.get(f"{BASE_URL}/assessments/{ASSESSMENT_ID}/questionnaire")
    if response.status_code != 200:
        print(f"Failed to fetch questionnaire: {response.status_code} - {response.text}")
        return
    questionnaire = response.json()

    for domain in questionnaire:
        print(f"\nAnswering domain: {domain['domain_name']}")
        for kpi in domain['kpis']:
            kpi_id      = kpi['kpi_id']
            is_inverted = kpi.get('is_inverted', False)

            # L1 target: worst possible answer per KPI type.
            # Normal KPI  → "Not"   triggers the gate on Q1 → L1.
            # Inverted KPI → "Fully" triggers the gate on Q1 → L1.
            l1_answer   = "Fully" if is_inverted else "Not"
            gate_option = "Fully" if is_inverted else "Not"

            q1      = kpi['questions'][0]
            answers = [{"question_id": q1['id'], "selected_option": l1_answer}]

            gate_triggered = (l1_answer == gate_option)
            if not gate_triggered:
                for q in kpi['questions'][1:]:
                    if not q.get('is_hidden'):
                        answers.append({
                            "question_id":     q['id'],
                            "selected_option": l1_answer,
                        })

            resp = session.post(
                f"{BASE_URL}/assessments/{ASSESSMENT_ID}/answers/kpi/{kpi_id}",
                json={"answers": answers},
            )
            if resp.status_code == 200:
                print(f"  KPI {kpi_id} ({kpi['kpi_name']}): answered → L1")
            else:
                print(f"  KPI {kpi_id} ERROR: {resp.text}")

    # Submit assessment
    print("\nSubmitting assessment...")
    submit_resp = session.post(f"{BASE_URL}/assessments/{ASSESSMENT_ID}/submit")
    print(f"Submit response: {submit_resp.status_code} - {submit_resp.json()}")


if __name__ == "__main__":
    answer_questionnaire()
