import requests
import json
import os

def test_workflow_and_pdf():
    session_id = "test_sess_12345"
    base_url = "http://127.0.0.1:5000"
    
    # 4-step intake flow to trigger report generation in mock mode
    intake_messages = [
        "acid reflux and burning sensation",  # symptoms
        "consume coffee daily, high stress",  # lifestyle
        "30-45",                              # age range
        "2 weeks"                             # duration
    ]
    
    print("Starting session intake workflow...")
    for idx, msg in enumerate(intake_messages):
        print(f"\nSending message {idx + 1}: '{msg}'")
        resp = requests.post(f"{base_url}/api/agent", json={
            "message": msg,
            "session_id": session_id
        })
        if resp.status_code != 200:
            print(f"Error: status code {resp.status_code}")
            print(resp.text)
            return
            
        data = resp.json()
        print("Reply received.")
        if data.get("dosha_state"):
            print("Dosha state generated:", json.dumps(data["dosha_state"], indent=2))
            
    # Now attempt to download the report
    print("\nRequesting report PDF...")
    download_url = f"{base_url}/api/download_report?session_id={session_id}"
    pdf_resp = requests.get(download_url)
    
    if pdf_resp.status_code != 200:
        print(f"Failed to download report: {pdf_resp.status_code}")
        print(pdf_resp.text)
        return
        
    pdf_content = pdf_resp.content
    print(f"PDF download successful! Size: {len(pdf_content)} bytes")
    
    # Check PDF magic bytes
    if pdf_content.startswith(b"%PDF"):
        print("Success: File starts with valid PDF header '%PDF'")
    else:
        print("Error: File is not a valid PDF")
        return
        
    # Save the file
    out_path = os.path.join(os.path.dirname(__file__), "test_report.pdf")
    with open(out_path, "wb") as f:
        f.write(pdf_content)
    print(f"Saved test report to {out_path}")

if __name__ == "__main__":
    test_workflow_and_pdf()
