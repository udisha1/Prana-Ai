import asyncio
import os
import sys
from dotenv import load_dotenv

# Ensure project root is in sys.path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.append(project_root)

# Load env variables
load_dotenv()

async def run_conversation(symptoms, duration, age_range, lifestyle_text):
    from google.adk.runners import InMemoryRunner
    from google.genai import types
    from agents.orchestrator import root_agent, run_mock_workflow
    
    session_id = "test_normal_session"
    user_id = "test_user"
    
    # Check if API key exists
    api_key = os.environ.get("GOOGLE_API_KEY")
    use_mock = not api_key
    
    # Initialize local mock session state
    mock_session = {
        "mock_step": 0,
        "symptoms": "",
        "duration": "",
        "age_range": "",
        "lifestyle": "",
        "dosha_state": None,
        "messages": []
    }
    
    runner = InMemoryRunner(agent=root_agent)
    # Create session for live runner
    if not use_mock:
        try:
            await runner.session_service.create_session(
                app_name=runner.app_name or "ayurcare",
                user_id=user_id,
                session_id=session_id
            )
        except Exception:
            pass
            
    print(f"\n--- Testing Symptoms: '{symptoms}' ---")
    
    responses = [
        symptoms,
        lifestyle_text,
        age_range,
        duration
    ]
    
    for i, user_reply in enumerate(responses):
        print(f"User Turn {i+1}: {user_reply}")
        mock_session["messages"].append(user_reply)
        
        if use_mock:
            # Run mock mode
            reply = run_mock_workflow(mock_session, user_reply)
        else:
            # Run live mode
            content = types.Content(
                role="user",
                parts=[types.Part.from_text(text=user_reply)]
            )
            try:
                response_text = ""
                async for event in runner.run_async(
                    user_id=user_id,
                    session_id=session_id,
                    new_message=content
                ):
                    if event.content and event.content.parts:
                        for part in event.content.parts:
                            if part.text:
                                response_text += part.text
                reply = response_text.strip()
            except Exception as e:
                # Catch 429 quota exhaustion or other errors, switch to mock mode mid-session!
                print(f"[Warning] Live execution failed ({type(e).__name__}). Falling back to Mock Mode mid-session.")
                use_mock = True
                
                # Reconstruct mock session up to current turn
                mock_session["symptoms"] = responses[0] if i >= 1 else ""
                mock_session["lifestyle"] = responses[1] if i >= 2 else ""
                mock_session["age_range"] = responses[2] if i >= 3 else ""
                mock_session["duration"] = responses[3] if i >= 4 else ""
                mock_session["mock_step"] = i
                
                # Execute current turn in mock mode
                reply = run_mock_workflow(mock_session, user_reply)
        
        # Print output
        if i == len(responses) - 1:
            print(f"\nWorkflow Final Response:\n{reply}")
            if use_mock and mock_session["dosha_state"]:
                print(f"Mock Dosha State: {mock_session['dosha_state']}")
        else:
            # Clean intermediate JSON responses for turns before final recommendations
            import re
            clean_question = re.sub(r"```json\s*\{.*?\}\s*```", "", reply, flags=re.DOTALL).strip()
            clean_question = re.sub(r"\{.*?\}", "", clean_question, flags=re.DOTALL).strip()
            if not clean_question:
                clean_question = reply
            print(f"Agent: {clean_question}")
            print("-" * 30)

async def test_red_flag():
    from google.adk.runners import InMemoryRunner
    from google.genai import types
    from agents.orchestrator import root_agent, run_mock_workflow
    
    session_id = "test_chest_pain"
    user_id = "test_user"
    
    api_key = os.environ.get("GOOGLE_API_KEY")
    use_mock = not api_key
    
    mock_session = {
        "mock_step": 0,
        "symptoms": "",
        "duration": "",
        "age_range": "",
        "lifestyle": "",
        "dosha_state": None,
        "messages": []
    }
    
    runner = InMemoryRunner(agent=root_agent)
    if not use_mock:
        try:
            await runner.session_service.create_session(
                app_name=runner.app_name or "ayurcare",
                user_id=user_id,
                session_id=session_id
            )
        except Exception:
            pass
            
    print("\n--- Testing Red Flag Symptom: 'chest pain' ---")
    
    responses = [
        "I have severe chest pain and difficulty breathing.",
        "My diet is standard, sleep is 7 hours, stress is moderate.",
        "I am 45 years old.",
        "It started 10 minutes ago."
    ]
    
    for i, user_reply in enumerate(responses):
        print(f"User Turn {i+1}: {user_reply}")
        mock_session["messages"].append(user_reply)
        
        if use_mock:
            reply = run_mock_workflow(mock_session, user_reply)
        else:
            content = types.Content(
                role="user",
                parts=[types.Part.from_text(text=user_reply)]
            )
            try:
                response_text = ""
                async for event in runner.run_async(
                    user_id=user_id,
                    session_id=session_id,
                    new_message=content
                ):
                    if event.content and event.content.parts:
                        for part in event.content.parts:
                            if part.text:
                                response_text += part.text
                reply = response_text.strip()
            except Exception as e:
                print(f"[Warning] Live execution failed ({type(e).__name__}). Falling back to Mock Mode mid-session.")
                use_mock = True
                
                # Reconstruct mock session
                mock_session["symptoms"] = responses[0] if i >= 1 else ""
                mock_session["lifestyle"] = responses[1] if i >= 2 else ""
                mock_session["age_range"] = responses[2] if i >= 3 else ""
                mock_session["duration"] = responses[3] if i >= 4 else ""
                mock_session["mock_step"] = i
                
                reply = run_mock_workflow(mock_session, user_reply)
                
        # If it's a red flag warning, safety agent immediately returns safety alert and blocks further steps.
        # Check if warning returned
        if "SAFETY WARNING" in reply:
            print(f"\nWorkflow Final Response (Safety Warning Triggered):\n{reply}")
            break
            
        if i == len(responses) - 1:
            print(f"\nWorkflow Final Response:\n{reply}")

async def main():
    print("=" * 60)
    print("RUNNING DATABASE AND AGENT INTEGRATION TESTS")
    print("=" * 60)
    
    # 1. Test stand-alone database tools
    from mcp_server.ayurveda_server import check_red_flag, get_dosha_info, get_herb_recommendations
    
    print("Testing check_red_flag('I am experiencing severe chest pain')...")
    red_flag_detected = check_red_flag("I am experiencing severe chest pain")
    print(f"Result: {red_flag_detected} (Expected: True)")
    assert red_flag_detected is True, "Failed to identify red flag!"
    
    print("Testing check_red_flag('Just a minor cough')...")
    normal_symptom = check_red_flag("Just a minor cough")
    print(f"Result: {normal_symptom} (Expected: False)")
    assert normal_symptom is False, "Incorrectly flagged a normal symptom!"
    
    print("\nTesting get_dosha_info('Vata')...")
    vata_info = get_dosha_info("Vata")
    print(f"Result (first 100 chars): {vata_info[:100]}...")
    assert "dry" in vata_info.lower(), "Failed to retrieve Vata qualities!"
    
    print("\nTesting get_herb_recommendations('Vata', 'headache')...")
    herb_recs = get_herb_recommendations("Vata", "headache")
    print(f"Result (first 150 chars): {herb_recs[:150]}...")
    assert "Ginger" in herb_recs or "Ashwagandha" in herb_recs or "Triphala" in herb_recs, "Failed to retrieve herb recommendations!"
    
    print("\n" + "=" * 60)
    print("DATABASE INTEGRATION TESTS PASSED SUCCESSFULLY!")
    print("=" * 60)
    
    # 2. Test Multi-Agent workflow execution (Live with Fallback)
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("\n[Notice] GOOGLE_API_KEY environment variable is not set. Running in Fallback Mock Mode.")
    else:
        print("\n[Notice] GOOGLE_API_KEY detected. Running in Live mode with Mock fallback.")
        
    # Test Case 1: Normal symptoms
    await run_conversation(
        symptoms="I have a persistent headache and dry skin.",
        duration="about 5 days now",
        age_range="I am in the 30-40 range",
        lifestyle_text="I eat mostly home-cooked food, sleep about 6 hours, and have high stress levels."
    )
    
    # Test Case 2: Red flag symptom
    await test_red_flag()

if __name__ == "__main__":
    asyncio.run(main())
