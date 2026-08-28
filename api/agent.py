from flask import Flask, request, jsonify, send_file, g
from flask_cors import CORS
import os
import sys
import re
import json
import asyncio
from time import time
from functools import wraps
from dotenv import load_dotenv
import io
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

# Ensure project root is in sys.path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.append(project_root)

# Load environment variables from .env file
load_dotenv()

try:
    import api.database as database
except ImportError:
    import database

# Initialize database / mock fallback
database.init_db()

app = Flask(__name__)
# Configure CORS to allow access from local/remote frontend origins
CORS(app)

# In-memory session and rate-limit storage (rate-limiting is still local IP based)
ip_request_history = {}

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return jsonify({"error": "Unauthorized. Please log in."}), 401
        
        token = auth_header.split(" ")[1]
        username = database.get_user_by_token(token)
        if not username:
            return jsonify({"error": "Session expired or invalid token."}), 401
            
        g.username = username
        g.token = token
        return f(*args, **kwargs)
    return decorated_function


RATE_LIMIT_WINDOW = 60  # seconds
RATE_LIMIT_MAX_REQUESTS = 15  # requests per minute

# Lazy-loaded runner reference
_runner = None

def get_runner():
    global _runner
    if _runner is None:
        # Lazy load to keep serverless cold start fast
        from google.adk.runners import InMemoryRunner
        from agents.orchestrator import root_agent
        _runner = InMemoryRunner(agent=root_agent)
    return _runner

def is_rate_limited(ip: str) -> bool:
    now = time()
    if ip not in ip_request_history:
        ip_request_history[ip] = []
    
    # Filter timestamps to keep only those in current window
    ip_request_history[ip] = [t for t in ip_request_history[ip] if now - t < RATE_LIMIT_WINDOW]
    
    if len(ip_request_history[ip]) >= RATE_LIMIT_MAX_REQUESTS:
        return True
    
    ip_request_history[ip].append(now)
    return False

@app.route("/api/agent", methods=["POST"])
@login_required
def handle_agent():
    # 1. Rate limiting check
    client_ip = request.headers.get("X-Forwarded-For", request.remote_addr)
    if is_rate_limited(client_ip):
        return jsonify({"error": "Rate limit exceeded. Please try again in a minute."}), 429

    # 2. Parse request data
    data = request.get_json() or {}
    message_text = data.get("message", "").strip()

    if not message_text:
        return jsonify({"error": "Missing required field: 'message'."}), 400

    # 3. Input Sanitization
    from agents.orchestrator import sanitize_input
    sanitized_message = sanitize_input(message_text)

    username = g.username
    session_data = database.get_user_session(username)
    if not session_data:
        session_data = {
            "messages": [],
            "chat_history": [
                {
                    "text": "Hello! I am your Ayurcare Agent. To guide you, I will collect some details about your symptoms and lifestyle.\n\nTo begin, what main symptoms are you experiencing today?",
                    "sender": "agent",
                    "isWarning": False
                }
            ],
            "is_mock": False,
            "mock_step": 0,
            "symptoms": "",
            "duration": "",
            "age_range": "",
            "lifestyle": "",
            "dosha_state": None
        }

    # Store message in histories
    session_data["messages"].append(sanitized_message)
    session_data["chat_history"].append({
        "text": sanitized_message,
        "sender": "user",
        "isWarning": False
    })
    database.save_user_session(username, session_data)

    # 4. Check for Mock Mode condition
    api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    use_mock = not api_key or session_data["is_mock"]

    if use_mock:
        from agents.orchestrator import run_mock_workflow
        # Run local rule-based mock pipeline
        reply = run_mock_workflow(session_data, sanitized_message)
        
        is_safety_warning = "SAFETY WARNING:" in reply or "emergency care" in reply or "see a doctor" in reply
        session_data["chat_history"].append({
            "text": reply,
            "sender": "agent",
            "isWarning": is_safety_warning
        })
        database.save_user_session(username, session_data)
        
        return jsonify({
            "reply": reply,
            "dosha_state": session_data["dosha_state"]
        }), 200

    # 5. Execute agent Workflow asynchronously (Live Mode)
    runner = get_runner()
    
    async def run_workflow():
        from google.genai import types
        
        # Ensure session exists in the ADK runner using username as key
        try:
            await runner.session_service.create_session(
                app_name=runner.app_name or "ayurcare",
                user_id=username,
                session_id=username
            )
        except Exception:
            pass

        content = types.Content(
            role="user",
            parts=[types.Part.from_text(text=sanitized_message)]
        )
        
        node_responses = {}
        async for event in runner.run_async(
            user_id=username,
            session_id=username,
            new_message=content
        ):
            node_name = getattr(event, "node_name", "unknown")
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        if node_name not in node_responses:
                            node_responses[node_name] = ""
                        node_responses[node_name] += part.text
                        
                        # Extract prakriti_agent's JSON output if emitted
                        if node_name == "prakriti_agent" or '"dominant_dosha"' in part.text:
                            try:
                                full_prakriti_text = node_responses.get("prakriti_agent", "")
                                json_match = re.search(r"\{.*\}", full_prakriti_text, re.DOTALL)
                                if json_match:
                                    prakriti_data = json.loads(json_match.group(0))
                                    session_data["dosha_state"] = prakriti_data
                                    database.save_user_session(username, session_data)
                            except Exception:
                                pass

        # Determine final response by picking output from the final executed node
        execution_order = [
            'safety_agent',
            'recommendation_agent',
            'knowledge_agent',
            'prakriti_agent',
            'intake_agent'
        ]
        
        response_text = ""
        for node in execution_order:
            if node in node_responses and node_responses[node].strip():
                response_text = node_responses[node].strip()
                break
                
        # If no custom nodes matched, fallback to any available output
        if not response_text and node_responses:
            response_text = list(node_responses.values())[-1].strip()

        return response_text

    try:
        reply = asyncio.run(run_workflow())
    except Exception as e:
        app.logger.warning(f"Live agent execution failed ({type(e).__name__}). Falling back to Mock Mode.")
        
        # Switch session to Mock Mode for subsequent turns
        session_data["is_mock"] = True
        
        # Sync the conversational state from history
        history = session_data["messages"]
        session_data["symptoms"] = history[0] if len(history) > 1 else ""
        session_data["lifestyle"] = history[1] if len(history) > 2 else ""
        session_data["age_range"] = history[2] if len(history) > 3 else ""
        session_data["duration"] = history[3] if len(history) > 4 else ""
        session_data["mock_step"] = len(history) - 1
        
        # Run mock workflow for the current turn
        from agents.orchestrator import run_mock_workflow
        reply = run_mock_workflow(session_data, sanitized_message)
        
        is_safety_warning = "SAFETY WARNING:" in reply or "emergency care" in reply or "see a doctor" in reply
        session_data["chat_history"].append({
            "text": reply,
            "sender": "agent",
            "isWarning": is_safety_warning
        })
        database.save_user_session(username, session_data)
        
        return jsonify({
            "reply": reply,
            "dosha_state": session_data["dosha_state"]
        }), 200

    # Extract final safety agent response (excluding intermediate JSON objects)
    clean_reply = reply
    clean_reply = re.sub(r"```json\s*\{.*?\}\s*```", "", clean_reply, flags=re.DOTALL).strip()
    clean_reply = re.sub(r"\{.*?\}", "", clean_reply, flags=re.DOTALL).strip()
    if not clean_reply:
        clean_reply = reply.strip()

    # Clean repeating/echoing responses and apply single disclaimer format
    clean_reply = cleanup_workflow_output(clean_reply)

    is_safety_warning = "SAFETY WARNING:" in clean_reply or "emergency care" in clean_reply or "see a doctor" in clean_reply
    session_data["chat_history"].append({
        "text": clean_reply,
        "sender": "agent",
        "isWarning": is_safety_warning
    })
    database.save_user_session(username, session_data)

    return jsonify({
        "reply": clean_reply,
        "dosha_state": session_data["dosha_state"]
    }), 200


def cleanup_workflow_output(text: str) -> str:
    if not text:
        return ""
    
    disclaimer_pattern = r"Disclaimer:\s*This\s*is\s*traditional\s*Ayurvedic\s*wellness\s*guidance.*"
    parts = re.split(disclaimer_pattern, text, flags=re.IGNORECASE)
    
    cleaned_parts = [p.strip() for p in parts if p.strip()]
    if cleaned_parts:
        final_text = cleaned_parts[-1]
        final_text = re.sub(r"^[\s\.\-\:\,\;]+", "", final_text).strip()
        return final_text + "\n\nDisclaimer: This is traditional Ayurvedic wellness guidance, not a medical diagnosis or treatment plan."
        
    return text


def get_consecutive_completed_days(history, start_date_str):
    from datetime import datetime, timedelta
    try:
        start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
    except ValueError:
        return 0
    
    def is_completed(date_str):
        day_data = history.get(date_str)
        if not day_data:
            return False
        tasks = day_data.get("tasks", [])
        if not tasks:
            return False
        return all(t.get("completed", False) for t in tasks)
    
    current_date = start_date
    streak = 0
    
    if is_completed(start_date_str):
        while is_completed(current_date.strftime("%Y-%m-%d")):
            streak += 1
            current_date -= timedelta(days=1)
        return streak
    else:
        yesterday = start_date - timedelta(days=1)
        yesterday_str = yesterday.strftime("%Y-%m-%d")
        if is_completed(yesterday_str):
            current_date = yesterday
            while is_completed(current_date.strftime("%Y-%m-%d")):
                streak += 1
                current_date -= timedelta(days=1)
            return streak
        return 0


@app.route("/api/tracker", methods=["GET"])
@login_required
def get_tracker():
    from datetime import datetime
    date_str = request.args.get("date")
    if not date_str or not re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
        date_str = datetime.utcnow().strftime("%Y-%m-%d")
        
    username = g.username
    session_data = database.get_user_session(username)
    dosha_state = session_data.get("dosha_state") if session_data else None
    if not dosha_state or not dosha_state.get("dominant_dosha"):
        return jsonify({
            "no_profile": True,
            "error": "No dosha profile generated yet. Complete your intake to unlock your daily Dinacharya tracker."
        }), 200
        
    dominant_dosha = dosha_state.get("dominant_dosha")
    
    tracker = session_data.get("dinacharya_tracker")
    if not tracker or tracker.get("dominant_dosha") != dominant_dosha:
        tracker = {
            "dominant_dosha": dominant_dosha,
            "longest_streak": tracker.get("longest_streak", 0) if tracker else 0,
            "history": {}
        }
        session_data["dinacharya_tracker"] = tracker

    history = tracker.get("history", {})
    
    if date_str not in history:
        balancing_routines = []
        try:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            db_path = os.path.join(current_dir, "..", "ayurveda_db.json")
            with open(db_path, "r", encoding="utf-8") as f:
                db_data = json.load(f)
            matching_doshas = [d.strip() for d in ["Vata", "Pitta", "Kapha"] if d.lower() in dominant_dosha.lower()]
            if not matching_doshas:
                matching_doshas = ["Vata"]
            
            routines_set = []
            for md in matching_doshas:
                for r in db_data["doshas"].get(md, {}).get("balancing_routines", []):
                    if r not in routines_set:
                        routines_set.append(r)
            balancing_routines = routines_set
        except Exception:
            fallback_routines = {
                "Vata": [
                    "Wake up early and maintain a consistent daily schedule to ground the mobile energy.",
                    "Massage the body with warm sesame oil (Abhyanga) before bathing to reduce dryness.",
                    "Eat warm, cooked, moist, and grounding meals with healthy fats like ghee.",
                    "Practice alternate nostril breathing (Nadi Shodhana Pranayama) to calm the nervous system."
                ],
                "Pitta": [
                    "Incorporate cooling foods into the diet (sweet fruits, leafy greens, coconut water).",
                    "Perform a gentle massage using cooling oils (like coconut or sunflower oil) to soothe heat.",
                    "Avoid intense exercise during the hottest parts of the day; prefer calming walks in nature.",
                    "Practice sheetali pranayama (cooling breath technique) to release heat."
                ],
                "Kapha": [
                    "Wake up before sunrise (by 6:00 AM) to prevent sluggish energy.",
                    "Engage in vigorous daily exercise to stimulate circulation and heat.",
                    "Eat warm, light, dry, and spicy foods; minimize dairy and sweet foods.",
                    "Perform dry skin brushing (Garshana) to stimulate lymphatic flow."
                ]
            }
            for d in ["Vata", "Pitta", "Kapha"]:
                if d.lower() in dominant_dosha.lower():
                    balancing_routines.extend(fallback_routines[d])
            if not balancing_routines:
                balancing_routines = fallback_routines["Vata"]
                
        balancing_routines = list(dict.fromkeys(balancing_routines))
        
        tasks = []
        for i, text in enumerate(balancing_routines):
            tasks.append({
                "id": f"task_{i}",
                "text": text,
                "completed": False
            })
            
        history[date_str] = {
            "tasks": tasks
        }
        tracker["history"] = history
        session_data["dinacharya_tracker"] = tracker
        database.save_user_session(username, session_data)
        
    current_streak = get_consecutive_completed_days(history, date_str)
    tracker["longest_streak"] = max(tracker.get("longest_streak", 0), current_streak)
    
    session_data["dinacharya_tracker"] = tracker
    database.save_user_session(username, session_data)
    
    return jsonify({
        "tracker": {
            "dominant_dosha": dominant_dosha,
            "streak_count": current_streak,
            "longest_streak": tracker["longest_streak"],
            "tasks": history[date_str]["tasks"],
            "date": date_str
        }
    }), 200


@app.route("/api/tracker/toggle", methods=["POST"])
@login_required
def toggle_tracker_task():
    data = request.get_json() or {}
    date_str = data.get("date")
    task_index = data.get("task_index")
    
    if not date_str or not re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
        return jsonify({"error": "Invalid or missing 'date' parameter."}), 400
        
    if task_index is None or not isinstance(task_index, int):
        return jsonify({"error": "Invalid or missing 'task_index' parameter."}), 400
        
    username = g.username
    session_data = database.get_user_session(username)
    if not session_data:
        return jsonify({"error": "No active session found."}), 404
        
    tracker = session_data.get("dinacharya_tracker")
    if not tracker:
        return jsonify({"error": "Tracker has not been initialized."}), 400
        
    history = tracker.get("history", {})
    if date_str not in history:
        return jsonify({"error": "No routine records found for the specified date."}), 404
        
    tasks = history[date_str].get("tasks", [])
    if task_index < 0 or task_index >= len(tasks):
        return jsonify({"error": "Task index out of bounds."}), 400
        
    tasks[task_index]["completed"] = not tasks[task_index]["completed"]
    
    current_streak = get_consecutive_completed_days(history, date_str)
    tracker["longest_streak"] = max(tracker.get("longest_streak", 0), current_streak)
    
    tracker["history"] = history
    session_data["dinacharya_tracker"] = tracker
    database.save_user_session(username, session_data)
    
    return jsonify({
        "tracker": {
            "dominant_dosha": tracker.get("dominant_dosha"),
            "streak_count": current_streak,
            "longest_streak": tracker["longest_streak"],
            "tasks": tasks,
            "date": date_str
        }
    }), 200


@app.route("/api/recipes", methods=["GET"])
@login_required
def get_recipes():
    username = g.username
    session_data = database.get_user_session(username)
    dosha_state = session_data.get("dosha_state") if session_data else None
    if not dosha_state or not dosha_state.get("dominant_dosha"):
        return jsonify({
            "no_profile": True,
            "error": "No dosha profile generated yet. Complete your intake to unlock your personalized Ayurvedic diet suggestions."
        }), 200
        
    dominant_dosha = dosha_state.get("dominant_dosha")
    
    recipes = []
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        db_path = os.path.join(current_dir, "..", "ayurveda_db.json")
        with open(db_path, "r", encoding="utf-8") as f:
            db_data = json.load(f)
        recipes = db_data.get("recipes", [])
    except Exception as e:
        return jsonify({"error": f"Failed to load recipes: {str(e)}"}), 500
        
    date_str = request.args.get("date")
    if not date_str or not re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
        from datetime import datetime
        date_str = datetime.utcnow().strftime("%Y-%m-%d")
        
    tracker = session_data.get("dinacharya_tracker") or {}
    history = tracker.get("history", {})
    logged_meals = []
    if date_str in history:
        logged_meals = history[date_str].get("meals", [])
        
    return jsonify({
        "dominant_dosha": dominant_dosha,
        "recipes": recipes,
        "logged_meals": logged_meals,
        "date": date_str
    }), 200


@app.route("/api/recipes/log", methods=["POST"])
@login_required
def log_recipe_meal():
    data = request.get_json() or {}
    date_str = data.get("date")
    recipe_id = data.get("recipe_id")
    
    if not date_str or not re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
        return jsonify({"error": "Invalid or missing 'date' parameter."}), 400
        
    if not recipe_id:
        return jsonify({"error": "Missing 'recipe_id' parameter."}), 400
        
    username = g.username
    session_data = database.get_user_session(username)
    if not session_data:
        return jsonify({"error": "No active session found."}), 404
        
    recipe_name = "Unknown Recipe"
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        db_path = os.path.join(current_dir, "..", "ayurveda_db.json")
        with open(db_path, "r", encoding="utf-8") as f:
            db_data = json.load(f)
        for r in db_data.get("recipes", []):
            if r["id"] == recipe_id:
                recipe_name = r["name"]
                break
    except Exception:
        pass
        
    tracker = session_data.get("dinacharya_tracker")
    if not tracker:
        dosha_state = session_data.get("dosha_state") or {}
        dominant_dosha = dosha_state.get("dominant_dosha", "Vata")
        tracker = {
            "dominant_dosha": dominant_dosha,
            "longest_streak": 0,
            "history": {}
        }
        
    history = tracker.get("history", {})
    if date_str not in history:
        # Initialize day entry with empty tasks if not present yet
        history[date_str] = {
            "tasks": [],
            "meals": []
        }
        
    if "meals" not in history[date_str]:
        history[date_str]["meals"] = []
        
    from datetime import datetime
    log_entry = {
        "recipe_id": recipe_id,
        "name": recipe_name,
        "logged_at": datetime.utcnow().strftime("%H:%M")
    }
    history[date_str]["meals"].append(log_entry)
    
    tracker["history"] = history
    session_data["dinacharya_tracker"] = tracker
    database.save_user_session(username, session_data)
    
    return jsonify({
        "logged_meals": history[date_str]["meals"],
        "date": date_str
    }), 200


@app.route("/api/consultations", methods=["GET"])
@login_required
def get_consultations():
    username = g.username
    session_data = database.get_user_session(username)
    if not session_data:
        return jsonify({"consultations": []}), 200
        
    tracker = session_data.get("dinacharya_tracker") or {}
    consultations = tracker.get("archived_consultations", [])
    
    return jsonify({"consultations": consultations}), 200


@app.route("/api/consultations/<consultation_id>", methods=["GET"])
@login_required
def get_consultation_details(consultation_id):
    username = g.username
    session_data = database.get_user_session(username)
    if not session_data:
        return jsonify({"error": "No active session found."}), 404
        
    tracker = session_data.get("dinacharya_tracker") or {}
    consultations = tracker.get("archived_consultations", [])
    
    for c in consultations:
        if c["id"] == consultation_id:
            return jsonify({"consultation": c}), 200
            
    return jsonify({"error": "Consultation not found."}), 404


@app.route("/api/consultations/archive", methods=["POST"])
@login_required
def archive_current_consultation():
    username = g.username
    session_data = database.get_user_session(username)
    if not session_data:
        return jsonify({"error": "No active session found."}), 404
        
    chat_history = session_data.get("chat_history", [])
    dosha_state = session_data.get("dosha_state")
    
    if len(chat_history) <= 1 or not dosha_state:
        return jsonify({"error": "No completed consultation to archive. Complete the intake first."}), 400
        
    tracker = session_data.get("dinacharya_tracker")
    if not tracker:
        tracker = {
            "dominant_dosha": dosha_state.get("dominant_dosha", "Vata"),
            "longest_streak": 0,
            "history": {}
        }
        
    if "archived_consultations" not in tracker:
        tracker["archived_consultations"] = []
        
    symptoms = session_data.get("symptoms", "General Wellness")
    dominant_dosha = dosha_state.get("dominant_dosha", "Unknown")
    
    summary = symptoms[:30] + "..." if len(symptoms) > 30 else symptoms
    summary = f"{summary} ({dominant_dosha})"
    
    import uuid
    from datetime import datetime
    
    consultation_id = "c_" + str(uuid.uuid4()).replace("-", "")
    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    
    archive_entry = {
        "id": consultation_id,
        "date": date_str,
        "summary": summary,
        "dosha_state": dosha_state,
        "chat_history": chat_history
    }
    
    tracker["archived_consultations"].insert(0, archive_entry)
    
    session_data["chat_history"] = [
        {
            "text": "Hello! I am your Ayurcare Agent. To guide you, I will collect some details about your symptoms and lifestyle.\n\nTo begin, what main symptoms are you experiencing today?",
            "sender": "agent",
            "isWarning": False
        }
    ]
    session_data["messages"] = []
    session_data["dosha_state"] = None
    session_data["mock_step"] = 0
    session_data["symptoms"] = ""
    session_data["duration"] = ""
    session_data["age_range"] = ""
    session_data["lifestyle"] = ""
    session_data["is_mock"] = False
    
    session_data["dinacharya_tracker"] = tracker
    database.save_user_session(username, session_data)
    
    return jsonify({
        "message": "Consultation archived successfully.",
        "consultations": tracker["archived_consultations"],
        "active_chat_history": session_data["chat_history"]
    }), 200


def load_ayurveda_knowledge():

    current_dir = os.path.dirname(os.path.abspath(__file__))
    kb_path = os.path.join(current_dir, "..", "data", "ayurveda_knowledge.json")
    with open(kb_path, "r", encoding="utf-8") as f:
        return json.load(f)

def generate_pdf(username, session_data):
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    
    # Title
    p.setFont("Helvetica-Bold", 24)
    p.drawString(50, 750, "PranaAI Weekly Wellness Report")
    
    # Line separator
    p.setStrokeColorRGB(0.2, 0.56, 0.38) # nature green
    p.setLineWidth(2)
    p.line(50, 735, 550, 735)
    
    # Metadata
    p.setFont("Helvetica", 10)
    p.drawString(50, 715, f"User: {username}")

    
    # Section 1: Dosha Profile
    p.setFont("Helvetica-Bold", 16)
    p.drawString(50, 680, "1. Dosha Profile")
    
    dosha_state = session_data.get("dosha_state", {})
    dominant_dosha = dosha_state.get("dominant_dosha", "N/A")
    constitution = dosha_state.get("constitution_breakdown", {})
    reasoning = dosha_state.get("reasoning", "")
    
    p.setFont("Helvetica-Bold", 12)
    p.drawString(60, 655, f"Dominant Dosha: {dominant_dosha}")
    
    p.setFont("Helvetica", 11)
    y = 635
    p.drawString(60, y, "Constitution Breakdown:")
    y -= 18
    for d, val in constitution.items():
        p.drawString(80, y, f"- {d}: {val}")
        y -= 16
        
    y -= 10
    p.setFont("Helvetica-Bold", 12)
    p.drawString(50, y, "2. Clinical Reasoning & Context")
    y -= 20
    p.setFont("Helvetica-Oblique", 11)
    
    # Wrap reasoning
    reasoning_lines = []
    words = reasoning.split(" ")
    current_line = ""
    for w in words:
        if len(current_line + " " + w) < 90:
            current_line += (" " if current_line else "") + w
        else:
            reasoning_lines.append(current_line)
            current_line = w
    if current_line:
        reasoning_lines.append(current_line)
        
    for line in reasoning_lines:
        p.drawString(60, y, line)
        y -= 16
        
    # Load knowledge base guidelines
    y -= 15
    p.setFont("Helvetica-Bold", 12)
    p.drawString(50, y, "3. Recommended Diet & Lifestyle Guidelines")
    y -= 20
    
    try:
        kb = load_ayurveda_knowledge()
        matching_doshas = [d for d in ["Vata", "Pitta", "Kapha"] if d.lower() in dominant_dosha.lower()]
        if not matching_doshas:
            matching_doshas = ["Vata"] # fallback
            
        p.setFont("Helvetica", 11)
        for d in matching_doshas:
            guidance = kb["doshas"][d]["guidance"]
            charac = kb["doshas"][d]["characteristics"]
            
            p.setFont("Helvetica-Bold", 11)
            p.drawString(60, y, f"[{d} Balancing Guidelines]")
            y -= 18
            
            p.setFont("Helvetica", 11)
            # Wrap guidance
            words = guidance.split(" ")
            current_line = ""
            for w in words:
                if len(current_line + " " + w) < 90:
                    current_line += (" " if current_line else "") + w
                else:
                    p.drawString(70, y, current_line)
                    y -= 16
                    current_line = w
            if current_line:
                p.drawString(70, y, current_line)
                y -= 16
                
            y -= 10
            # Wrap characteristics
            p.setFont("Helvetica-Oblique", 10)
            words = charac.split(" ")
            current_line = ""
            for w in words:
                if len(current_line + " " + w) < 95:
                    current_line += (" " if current_line else "") + w
                else:
                    p.drawString(70, y, current_line)
                    y -= 14
                    current_line = w
            if current_line:
                p.drawString(70, y, current_line)
                y -= 14
            y -= 15
    except Exception as e:
        p.drawString(60, y, "Unable to load detailed guidelines from database.")
        y -= 16
        
    # Footer
    p.setFont("Helvetica-Bold", 10)
    p.setFillColorRGB(0.7, 0.3, 0.3)
    p.drawString(50, 60, "Disclaimer: This is traditional Ayurvedic wellness guidance, not a medical diagnosis or treatment plan.")
    
    p.showPage()
    p.save()
    
    buffer.seek(0)
    return buffer

@app.route("/api/download_report", methods=["GET"])
def download_report():
    # Support token in Authorization header or query parameter
    token = None
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
    else:
        token = request.args.get("token")
        
    if not token:
        return jsonify({"error": "Unauthorized. Missing token."}), 401
        
    username = database.get_user_by_token(token)
    if not username:
        return jsonify({"error": "Session expired or invalid token."}), 401
        
    session_data = database.get_user_session(username)
    if not session_data:
        return jsonify({"error": "No session found."}), 404
        
    consultation_id = request.args.get("consultation_id")
    if consultation_id:
        tracker = session_data.get("dinacharya_tracker") or {}
        consultations = tracker.get("archived_consultations", [])
        found_c = None
        for c in consultations:
            if c["id"] == consultation_id:
                found_c = c
                break
        if not found_c:
            return jsonify({"error": "Archived consultation not found."}), 404
        session_data = {
            "dosha_state": found_c["dosha_state"]
        }
        
    if not session_data.get("dosha_state"):
        return jsonify({"error": "No wellness report generated yet for this session."}), 404
        
    try:
        pdf_buffer = generate_pdf(username, session_data)
        return send_file(
            pdf_buffer,
            as_attachment=True,
            download_name="PranaAI_Wellness_Report.pdf",
            mimetype="application/pdf"
        )
    except Exception as e:
        app.logger.error(f"Error generating PDF: {str(e)}")
        return jsonify({"error": "Failed to generate report PDF."}), 500

@app.route("/api/register", methods=["POST"])
def register():
    data = request.get_json() or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")
    
    if not username or not password:
        return jsonify({"error": "Username and password are required."}), 400
        
    success, msg = database.register_user(username, password)
    if not success:
        return jsonify({"error": msg}), 400
        
    return jsonify({"message": msg}), 201

@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")
    
    if not username or not password:
        return jsonify({"error": "Username and password are required."}), 400
        
    success, token_or_msg = database.authenticate_user(username, password)
    if not success:
        return jsonify({"error": token_or_msg}), 401
        
    # Upon login, fetch or initialize session_data
    session_data = database.get_user_session(username)
    has_history = session_data is not None and len(session_data.get("chat_history", [])) > 1
    
    return jsonify({
        "token": token_or_msg,
        "username": username,
        "has_history": has_history
    }), 200

@app.route("/api/logout", methods=["POST"])
@login_required
def logout():
    success = database.revoke_token(g.token)
    return jsonify({"message": "Logged out successfully."}), 200

@app.route("/api/user/status", methods=["GET"])
@login_required
def user_status():
    session_data = database.get_user_session(g.username)
    dosha_state = session_data.get("dosha_state") if session_data else None
    return jsonify({
        "username": g.username,
        "dosha_state": dosha_state
    }), 200

@app.route("/api/chat/history", methods=["GET"])
@login_required
def chat_history():
    session_data = database.get_user_session(g.username)
    if not session_data:
        # Default fresh state
        session_data = {
            "messages": [],
            "chat_history": [
                {
                    "text": "Hello! I am your Ayurcare Agent. To guide you, I will collect some details about your symptoms and lifestyle.\n\nTo begin, what main symptoms are you experiencing today?",
                    "sender": "agent",
                    "isWarning": False
                }
            ],
            "is_mock": False,
            "mock_step": 0,
            "symptoms": "",
            "duration": "",
            "age_range": "",
            "lifestyle": "",
            "dosha_state": None
        }
        database.save_user_session(g.username, session_data)
        
    return jsonify({
        "chat_history": session_data.get("chat_history", []),
        "dosha_state": session_data.get("dosha_state")
    }), 200

@app.route("/api/chat/clear", methods=["POST"])
@login_required
def chat_clear():
    # Reset to default state
    session_data = {
        "messages": [],
        "chat_history": [
            {
                "text": "Hello! I am your Ayurcare Agent. To guide you, I will collect some details about your symptoms and lifestyle.\n\nTo begin, what main symptoms are you experiencing today?",
                "sender": "agent",
                "isWarning": False
            }
        ],
        "is_mock": False,
        "mock_step": 0,
        "symptoms": "",
        "duration": "",
        "age_range": "",
        "lifestyle": "",
        "dosha_state": None
    }
    database.save_user_session(g.username, session_data)
    return jsonify({"message": "Chat history cleared successfully."}), 200

if __name__ == "__main__":
    app.run(port=5000, debug=False)


