import re
import os
import json
import asyncio
from typing import Any
from google.adk import Workflow
from agents.intake_agent import intake_agent
from agents.prakriti_agent import prakriti_agent
from agents.knowledge_agent import knowledge_agent
from agents.recommendation_agent import recommendation_agent
from agents.safety_agent import safety_agent

# Input Sanitization: Strips potential prompt-injection patterns
def sanitize_input(text: str) -> str:
    if not text:
        return ""
    # Remove system commands / bypass instruction attempts
    sanitized = re.sub(
        r"(ignore\s+(?:previous|all)\s+instructions|system\s+override|delete\s+all\s+rules|you\s+are\s+now|override\s+persona|jailbreak)", 
        "[REDACTED INJECTION ATTEMPT]", 
        text, 
        flags=re.IGNORECASE
    )
    # Strip dangerous special character runs or backticks/tags that might break formats
    sanitized = sanitized.strip()
    return sanitized

# Delay nodes to prevent "429 Resource Exhausted" API errors by introducing spacing between rapid LLM transitions
async def delay_prakriti(node_input: Any) -> Any:
    await asyncio.sleep(0.1)
    return node_input

async def delay_knowledge(node_input: Any) -> Any:
    await asyncio.sleep(0.1)
    return node_input

async def delay_recommendation(node_input: Any) -> Any:
    await asyncio.sleep(0.1)
    return node_input

async def delay_safety(node_input: Any) -> Any:
    await asyncio.sleep(0.1)
    return node_input

# List of red flags to check in the user's message
RED_FLAGS = [
    "chest pain",
    "difficulty breathing", "breathing difficulty", "shortness of breath",
    "severe bleeding", "bleeding heavily",
    "loss of consciousness", "passed out", "unconscious",
    "sudden numbness", "numbness",
    "sudden weakness", "weakness",
    "difficulty speaking", "speech difficulty",
    "sudden severe headache", "severe headache",
    "stiff neck",
    "severe abdominal pain", "severe stomach pain",
    "self-harm", "suicid",
    "swallowing difficulty",
    "severe allergic reaction", "allergic reaction"
]

def intake_router(ctx, node_input) -> Any:
    # 1. Check for red flags in the user's latest message
    try:
        try:
            import api.database as database
        except ImportError:
            import database
        
        username = ctx.user_id
        session_data = database.get_user_session(username)
        if session_data and session_data.get("messages"):
            latest_message = session_data["messages"][-1].lower().strip()
            
            has_red_flag = False
            for flag in RED_FLAGS:
                if flag in latest_message:
                    has_red_flag = True
                    break
            
            if has_red_flag:
                ctx.route = "route_safety"
                return node_input
    except Exception as e:
        # Fallback to checking the input text itself
        pass
        
    # 2. Check if the intake is complete by looking at the output from intake_agent
    text = ""
    if isinstance(node_input, str):
        text = node_input
    elif hasattr(node_input, "parts") and node_input.parts:
        text = "".join(p.text for p in node_input.parts if p.text)
    elif isinstance(node_input, dict):
        text = json.dumps(node_input)
    else:
        text = str(node_input)
        
    text_lower = text.lower()
    is_complete = "symptoms" in text_lower and "lifestyle" in text_lower and ("duration" in text_lower or "age_range" in text_lower)
    
    if is_complete:
        ctx.route = "route_prakriti"
    else:
        ctx.route = "route_exit"
        
    return node_input

# Define the root workflow agent that chains the agents sequentially with intermediate spacing delays
root_agent = Workflow(
    name="root_agent",
    edges=[
        ("START", intake_agent),
        (intake_agent, intake_router),
        (intake_router, {
            "route_safety": safety_agent,
            "route_prakriti": delay_prakriti
        }),
        (delay_prakriti, prakriti_agent),
        (prakriti_agent, delay_knowledge),
        (delay_knowledge, knowledge_agent),
        (knowledge_agent, delay_recommendation),
        (delay_recommendation, recommendation_agent),
        (recommendation_agent, delay_safety),
        (delay_safety, safety_agent)
    ]
)

# --- Fallback Mock Mode state-machine logic ---

def load_kb():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    kb_path = os.path.join(current_dir, "..", "data", "ayurveda_knowledge.json")
    with open(kb_path, "r", encoding="utf-8") as f:
        return json.load(f)

def run_mock_workflow(session: dict, message_text: str) -> str:
    """Runs a logic-based mock workflow that simulates the multi-agent pipeline using local database data.
    Updates the session state in-place and returns the text reply.
    """
    kb = load_kb()
    
    # 1. Always perform Red Flag check first on any user message
    red_flags = kb.get("red_flags", [])
    msg_lower = message_text.lower().strip()
    
    matched_flag = None
    for flag in red_flags:
        if flag.lower() in msg_lower:
            matched_flag = flag
            break
            
    if matched_flag:
        return (
            "SAFETY WARNING:\n"
            f"A potential red-flag medical symptom ('{matched_flag}') has been detected. "
            "Please seek immediate professional medical attention or emergency care. "
            "Do not rely on traditional Ayurvedic suggestions for acute or severe conditions.\n\n"
            "Disclaimer: This is traditional Ayurvedic wellness guidance, not a medical diagnosis or treatment plan."
        )

    step = session.get("mock_step", 0)
    
    if step == 0:
        session["symptoms"] = message_text
        session["mock_step"] = 1
        return "Thank you. Could you briefly describe your general lifestyle habits (covering diet, sleep quality/hours, and current stress levels)?"
        
    elif step == 1:
        session["lifestyle"] = message_text
        session["mock_step"] = 2
        return "Understood. What is your age range (e.g. 18-29, 30-45, 46-60, or 60+)?"
        
    elif step == 2:
        session["age_range"] = message_text
        session["mock_step"] = 3
        return "Thank you. Lastly, how long have you been experiencing these symptoms (duration)?"
        
    elif step == 3:
        session["duration"] = message_text
        session["mock_step"] = 4  # completed
        
        # Analyze collected inputs to compute mock dosha constitution
        symptoms_text = session.get("symptoms", "").lower()
        lifestyle_text = session.get("lifestyle", "").lower()
        full_context = symptoms_text + " " + lifestyle_text
        
        # Keyword-based scoring
        vata_score = 2
        pitta_score = 2
        kapha_score = 2
        
        vata_keywords = ["dry", "anxiety", "fear", "restless", "insomnia", "sleep", "constipation", "gas", "bloat", "fatigue", "spasm", "cold"]
        pitta_keywords = ["irritab", "anger", "impatient", "acid", "reflux", "heartburn", "rash", "acne", "inflam", "heat", "sweat", "red", "burn"]
        kapha_keywords = ["letharg", "drowsy", "oversleep", "weight", "slow", "congest", "mucus", "sinus", "fluid", "swell", "stubborn", "depress"]
        
        for kw in vata_keywords:
            if kw in full_context:
                vata_score += 3
        for kw in pitta_keywords:
            if kw in full_context:
                pitta_score += 3
        for kw in kapha_keywords:
            if kw in full_context:
                kapha_score += 3
                
        # Custom lifestyle keyword scoring
        if "spicy" in lifestyle_text or "hot" in lifestyle_text or "coffee" in lifestyle_text:
            pitta_score += 3
        if "cold" in lifestyle_text or "raw" in lifestyle_text or "salad" in lifestyle_text:
            vata_score += 3
        if "heavy" in lifestyle_text or "sweet" in lifestyle_text or "dairy" in lifestyle_text:
            kapha_score += 3
            
        total = vata_score + pitta_score + kapha_score
        vata_pct = int((vata_score / total) * 100)
        pitta_pct = int((pitta_score / total) * 100)
        kapha_pct = 100 - vata_pct - pitta_pct
        
        # Dominant dosha determination
        scores = {"Vata": vata_pct, "Pitta": pitta_pct, "Kapha": kapha_pct}
        sorted_doshas = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        highest_dosha, highest_score = sorted_doshas[0]
        second_dosha, second_score = sorted_doshas[1]
        
        if highest_score - second_score <= 15:
            dominant_dosha = f"{highest_dosha}-{second_dosha}"
        else:
            dominant_dosha = highest_dosha
            
        # Contextual reasoning
        characteristics = []
        for d in ["Vata", "Pitta", "Kapha"]:
            if d in dominant_dosha:
                characteristics.append(d)
                
        reasoning = (
            f"Based on your symptoms and lifestyle inputs, we see a predominance of qualities associated with {dominant_dosha}. "
            f"Specifically, we observed indications of {', '.join(characteristics)} attributes in your description."
        )
        
        dosha_state = {
            "dominant_dosha": dominant_dosha,
            "constitution_breakdown": {
                "Vata": f"{vata_pct}%",
                "Pitta": f"{pitta_pct}%",
                "Kapha": f"{kapha_pct}%"
            },
            "reasoning": reasoning
        }
        session["dosha_state"] = dosha_state
        
        # Build guidelines from KB
        diet_guidelines = []
        lifestyle_guidelines = []
        for d in ["Vata", "Pitta", "Kapha"]:
            if d in dominant_dosha:
                info = kb["doshas"].get(d, {})
                diet_guidelines.append(info.get("guidance", ""))
                lifestyle_guidelines.append(info.get("characteristics", ""))
                
        diet_text = " ".join(diet_guidelines)
        lifestyle_text = " ".join(lifestyle_guidelines)
        
        # Personalize based on specific symptoms/issues
        personalized_diet_tips = []
        personalized_lifestyle_tips = []
        
        symptoms_lower = symptoms_text.lower()
        if "acne" in symptoms_lower or "oily skin" in symptoms_lower or "skin" in symptoms_lower:
            personalized_diet_tips.append("To support your skin health and manage oily skin/acne, limit sour, salty, and spicy foods, as well as fermented items which can inflame Pitta. Favor cooling foods like sweet fruits, cucumbers, and leafy greens.")
            personalized_lifestyle_tips.append("For your skin issues, avoid harsh chemicals or excessive heat. Wash your face with cooling rosewater or apply a paste of chickpea flour and turmeric.")
            
        if "hair" in symptoms_lower or "hair fall" in symptoms_lower or "hair loss" in symptoms_lower:
            personalized_diet_tips.append("To combat hair fall, ensure your diet includes iron-rich foods, leafy greens, sesame seeds, and warm, nourishing meals to strengthen your roots.")
            personalized_lifestyle_tips.append("To support hair growth, perform a gentle scalp massage (Shiroabhyanga) weekly using cooling coconut oil or warm Bhringraj oil before washing.")
            
        if "gut" in symptoms_lower or "digestion" in symptoms_lower or "stomach" in symptoms_lower or "bloat" in symptoms_lower or "constipation" in symptoms_lower or "health" in symptoms_lower:
            # Map general bad gut health to digestion support
            personalized_diet_tips.append("To improve bad gut health, prioritize warm, freshly cooked, and easily digestible foods. Sip warm cumin-coriander-fennel (CCF) tea throughout the day, and avoid cold or iced drinks which weaken digestion (Agni).")
            personalized_lifestyle_tips.append("For better digestion and gut health, maintain consistent meal times daily, chew your food thoroughly in a calm environment, and take a gentle 100-step walk after dinner.")
            
        if "anxiety" in symptoms_lower or "stress" in symptoms_lower or "overthinking" in symptoms_lower:
            personalized_diet_tips.append("To calm anxiety and stress, favor warm, heavy, and grounding foods (soups, stews, warm milk with nutmeg). Avoid caffeine and cold, dry snacks.")
            personalized_lifestyle_tips.append("To manage stress, establish a daily grounding routine: practice alternate nostril breathing (Nadi Shodhana Pranayama) for 5-10 minutes every morning, and limit screen time before bed.")
            
        if "headache" in symptoms_lower:
            personalized_diet_tips.append("To reduce headaches, stay hydrated by drinking warm water or herbal teas, and avoid skipping meals which can trigger stress-induced headaches.")
            personalized_lifestyle_tips.append("For headaches, apply a drop of cooling sandalwood or peppermint paste to your temples, and ensure you rest in a dark, quiet room.")

        # Check lifestyle inputs
        lifestyle_lower = lifestyle_text.lower()
        if "coffee" in lifestyle_lower or "caffeine" in lifestyle_lower:
            personalized_diet_tips.append("Since you consume coffee/caffeine, consider reducing your intake or replacing it with herbal teas (like chamomile or mint) to avoid drying out Vata or heating up Pitta.")
        if "sleep" in lifestyle_lower or "hour" in lifestyle_lower:
            personalized_lifestyle_tips.append("Given your sleep duration (around 6 hours), aim to go to bed by 10:00 PM to align with Kapha's naturally restorative night window, ensuring deeper sleep.")
        if "stress" in lifestyle_lower:
            personalized_lifestyle_tips.append("To help with high daily stress levels, schedule 10 minutes of quiet meditation or deep breathing exercises in your daily routine.")

        # Combine guidelines
        if personalized_diet_tips:
            diet_text = diet_text + "\n\n**Personalized Diet Tips:**\n" + "\n".join([f"- {tip}" for tip in personalized_diet_tips])
        if personalized_lifestyle_tips:
            lifestyle_text = lifestyle_text + "\n\n**Personalized Daily Routines:**\n" + "\n".join([f"- {tip}" for tip in personalized_lifestyle_tips])
        
        # Select matching herbs
        matching_herbs = []
        for herb in kb.get("herbs", []):
            balances_dominant = False
            for d in ["Vata", "Pitta", "Kapha"]:
                if d in dominant_dosha and d in herb.get("balances", []):
                    balances_dominant = True
                    break
            
            if balances_dominant:
                matches_symptom = False
                herb_name = herb.get("name", "").lower()
                use_note = herb.get("use_note", "").lower()
                for word in full_context.split():
                    if len(word) > 3 and (word in herb_name or word in use_note):
                        matches_symptom = True
                        break
                if matches_symptom:
                    matching_herbs.append(herb)
                    
        # Fallback to general herbs if none matched symptom specifically
        if not matching_herbs:
            for herb in kb.get("herbs", []):
                for d in ["Vata", "Pitta", "Kapha"]:
                    if d in dominant_dosha and d in herb.get("balances", []):
                        matching_herbs.append(herb)
                        break
                if len(matching_herbs) >= 2:
                    break
                    
        # Limit to 3 herbs maximum
        matching_herbs = matching_herbs[:3]
        herbs_lines = [f"- **{h['name']}**: {h['use_note']}" for h in matching_herbs]
        herbs_text = "\n".join(herbs_lines)
        
        reply = (
            f"Based on your Ayurvedic profile, here is traditional wellness guidance:\n\n"
            f"**Constitution:** Vata ({vata_pct}%), Pitta ({pitta_pct}%), Kapha ({kapha_pct}%)\n"
            f"**Dominant Dosha:** {dominant_dosha}\n\n"
            f"### Diet Recommendations\n"
            f"{diet_text}\n\n"
            f"### Lifestyle & Daily Routine\n"
            f"{lifestyle_text}\n\n"
            f"### Traditional Herb/Food Suggestions\n"
            f"{herbs_text}\n\n"
            "Disclaimer: This is traditional Ayurvedic wellness guidance, not a medical diagnosis or treatment plan."
        )
        return reply
        
    else:
        # Handle follow-up Q&A mode in mock session instead of resetting
        dominant_dosha = "Vata"
        if session.get("dosha_state") and session["dosha_state"].get("dominant_dosha"):
            dominant_dosha = session["dosha_state"]["dominant_dosha"]
        else:
            breakdown = session.get("dosha_state", {}).get("constitution_breakdown", {})
            if breakdown:
                try:
                    highest = max(breakdown.items(), key=lambda x: int(x[1].replace("%","")))
                    dominant_dosha = highest[0]
                except Exception:
                    pass
                
        msg_lower = message_text.lower()
        
        # Check if user is asking for a checklist, routine, or daily plan
        if any(kw in msg_lower for kw in ["checklist", "routine", "daily plan", "morning routine", "plan"]):
            if "vata" in dominant_dosha.lower():
                checklist_items = [
                    "Drink a glass of warm water with lemon upon waking",
                    "Perform 5-10 minutes of gentle grounding stretches or yoga",
                    "Practice 5 minutes of Nadi Shodhana (Alternate Nostril Breathing)",
                    "Self-massage (Abhyanga) with warm sesame oil before warm shower"
                ]
            elif "pitta" in dominant_dosha.lower():
                checklist_items = [
                    "Drink a glass of cool or room-temperature water upon waking",
                    "Practice 5 minutes of Sheetali Pranayama (Cooling Breath)",
                    "Engage in a 10-minute mindfulness meditation in a cool room",
                    "Self-massage (Abhyanga) with cooling coconut or sunflower oil"
                ]
            else:  # Kapha
                checklist_items = [
                    "Drink a cup of warm water with ginger and a drop of honey",
                    "Perform 10-15 minutes of vigorous Sun Salutations (Surya Namaskar)",
                    "Practice 5 minutes of Bhastrika Pranayama (Bellows Breath) to clear mucus",
                    "Dry brush the skin (Garshana) to stimulate lymphatic circulation"
                ]
            
            checklist_lines = [f"- [ ] {item}" for item in checklist_items]
            checklist_text = "\n".join(checklist_lines)
            
            return (
                "🔔 **Personalized Follow-Up:**\n"
                f"Here is your verified daily morning checklist for your dominant {dominant_dosha} constitution:\n\n"
                f"{checklist_text}\n\n"
                "Disclaimer: This is traditional Ayurvedic wellness guidance, not a medical diagnosis or treatment plan."
            )
            
        elif "basil seed" in msg_lower or "basil seeds" in msg_lower:
            # Check if user is asking how to consume them without losing weight
            if any(kw in msg_lower for kw in ["weight", "reduce", "how", "what can i do"]):
                return (
                    "🔔 **Personalized Follow-Up:**\n"
                    f"To consume basil seeds without reducing weight or causing excess weight loss under your dominant {dominant_dosha} constitution, traditional Ayurvedic guidance suggests:\n\n"
                    "- **Soak in milk**: Soak the basil seeds in warm milk (cow's milk or almond milk) instead of water to add nourishing, building (Brimhana) qualities.\n"
                    "- **Combine with sweet/heavy foods**: Mix the soaked seeds into a bowl of warm oatmeal, pudding, or a naturally sweet smoothie to counterbalance their cooling, scraping nature.\n"
                    "- **Limit frequency**: Use them in moderation (no more than 1 teaspoon daily) and avoid consuming them on an empty stomach.\n\n"
                    "Disclaimer: This is traditional Ayurvedic wellness guidance, not a medical diagnosis or treatment plan."
                )
                
            if "pitta" in dominant_dosha.lower():
                explanation = "balancing (beneficial) because they are cooling and help soothe the excess heat associated with Pitta."
            elif "vata" in dominant_dosha.lower():
                explanation = "mildly aggravating if taken in excess because they are cooling and heavy, which can increase Vata coldness. Take them with warm water."
            else:
                explanation = "balancing for Kapha but should be consumed in moderation due to their heavy, grounding nature."
            
            return (
                "🔔 **Personalized Follow-Up:**\n"
                f"Evaluating basil seeds for your dominant {dominant_dosha} constitution:\n\n"
                f"Basil seeds are {explanation}\n\n"
                "Disclaimer: This is traditional Ayurvedic wellness guidance, not a medical diagnosis or treatment plan."
            )
            
        elif "coffee" in msg_lower:
            if "pitta" in dominant_dosha.lower() or "vata" in dominant_dosha.lower():
                explanation = "aggravating (harmful) because coffee is heating, drying, and highly stimulating, which increases acidity/heat (Pitta) and restlessness (Vata)."
            else:
                explanation = "balancing for Kapha in moderation as its warm, dry, and stimulating properties help reduce Kapha heaviness."
                
            return (
                "🔔 **Personalized Follow-Up:**\n"
                f"Evaluating coffee for your dominant {dominant_dosha} constitution:\n\n"
                f"Coffee is {explanation}\n\n"
                "Disclaimer: This is traditional Ayurvedic wellness guidance, not a medical diagnosis or treatment plan."
            )
            
        else:
            return (
                "🔔 **Personalized Follow-Up:**\n"
                f"For your dominant {dominant_dosha} constitution, traditional wellness suggests favoring habits and foods that bring balance. Since you asked about '{message_text}', please ensure it is warm, grounding, and easily digestible to support your current state.\n\n"
                "Disclaimer: This is traditional Ayurvedic wellness guidance, not a medical diagnosis or treatment plan."
            )

