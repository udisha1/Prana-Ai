import sys
import os
# Ensure project root is in sys.path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.append(project_root)

import asyncio
from google.adk.runners import InMemoryRunner
from agents.orchestrator import root_agent
from google.genai import types

async def test():
    runner = InMemoryRunner(agent=root_agent)
    session_id = 'test_inspect_session'
    try:
        await runner.session_service.create_session(
            app_name=runner.app_name or "ayurcare",
            user_id=session_id,
            session_id=session_id
        )
    except Exception:
        pass
        
    content = types.Content(role='user', parts=[types.Part.from_text(text='I have oily skin')])
    async for event in runner.run_async(user_id=session_id, session_id=session_id, new_message=content):
        print("Event Type:", type(event))
        print("Event Attributes:", dir(event))
        print("Event Dict keys:", event.__dict__.keys() if hasattr(event, "__dict__") else "no __dict__")
        for key in ['node_name', 'node', 'agent_name', 'name', 'step', 'type']:
            if hasattr(event, key):
                print(f"{key}:", getattr(event, key))
        break

if __name__ == "__main__":
    asyncio.run(test())
