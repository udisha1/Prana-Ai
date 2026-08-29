# PranaAI — Your Personalized Ayurvedic Concierge Agent

> **An Intelligent Multi-Agent Ayurvedic System Leveraging Google Agent Development Kit (ADK) and Gemini 2.5 Flash for Safe, Personalised Wellness Guidance.**

---

## 1. Overview
**PranaAI** is a state-of-the-art traditional wellness assistant designed to bring the age-old wisdom of Ayurveda into the modern digital era. It utilizes the **Google Agent Development Kit (ADK)** and the **Gemini 2.5 Flash** model to analyze a user's symptoms, lifestyle, age, and duration of concerns to calculate their dominant **Dosha constitution** (Vata, Pitta, Kapha, or a combination). 

By referencing a curated Ayurvedic knowledge database and using context-aware memory, PranaAI provides highly tailored, safe, and actionable daily routines, dietary recommendations, and traditional herbal suggestions, accompanied by a dynamic PDF report generation engine.

---

## 2. Multi-Agent Architecture
PranaAI is powered by a sequential multi-agent pipeline built on top of the Google ADK. Each agent executes a highly specialized role:

```
[User Message]
      │
      ▼
┌──────────────┐
│ Intake Agent │ ──► Collects symptoms, lifestyle, age range, and duration
└──────────────┘
      │
      ▼
┌─────────────────┐
│ Prakriti Expert │ ──► Analyzes intake summary and determines Dosha breakdown
└─────────────────┘
      │
      ▼
┌─────────────────┐
│ Knowledge Agent │ ──► Connects to local MCP servers to fetch validated guidance
└─────────────────┘
      │
      ▼
┌──────────────────────┐
│ Recommendation Agent │ ──► Synthesizes data into dietary and routine tips
└──────────────────────┘
      │
      ▼
┌──────────────┐
│ Safety Guard │ ──► Runs a final validation check for medical red flags
└──────────────┘
      │
      ▼
[Final Clean Response]
```

- **Intake Agent:** Empathically collects user data (symptom, lifestyle details, age range, duration) one question at a time and packages it into a structured JSON payload once complete.
- **Prakriti Expert:** Interprets the intake summary and performs keyword-based or semantic mapping to calculate the percentage breakdown of Vata, Pitta, and Kapha.
- **Knowledge Agent:** Connects dynamically to local Model Context Protocol (MCP) servers (including the **Seasonal Awareness Server**) to retrieve traditional characteristics and seasonal guidance.
- **Recommendation Agent:** Formulates highly personalized advice (such as morning checklists and customized food evaluations) based on the user's history and current constitution.
- **Safety Guard:** Serves as a final check block to scan for clinical red flags (e.g. severe chest pain, shortness of breath) and instantly escalates to a medical disclaimer and suggestion to consult a doctor.

---

## 3. Key Features

- **Follow-up Q&A Memory:** Supports continuous follow-up conversations using context memory. Users can ask specific queries (e.g. *"how to use basil seeds without losing weight"*), and the agent provides direct, actionable answers rather than repeating general dosha evaluations.
- **Safety Guardrails (Red Flag Detection):** Scans user messages for critical symptoms and immediately suspends suggestions, returning a prominent warning block to see a doctor.
- **PDF Report Generation:** Once the intake is complete and the Dosha state is generated, a clean, nature-themed "Download Weekly Wellness Report" button appears. Users can click this to dynamically download a beautifully styled PDF report containing their personalized Ayurvedic profile, clinical reasoning, and database guidelines.

---

## 4. Tech Stack

- **Frontend:** React, Vite, CSS3 (with nature-themed design tokens and hover animations)
- **Backend:** Flask, Flask-CORS, Python 3.12, ReportLab (for PDF generation)
- **AI Engine:** Gemini 2.5 Flash, Google Agent Development Kit (ADK)
- **Model Context Protocol (MCP):** Stdio MCP Server for seasonal and health knowledge lookups
- **Deployment Platform:** Vercel (for frontend static hosting and backend python serverless functions)

---

## 5. Live Demo

🌐 **Live Demo Link:** `ayurcare-agent.vercel.app`

---
   *The frontend will start on `http://localhost:5173/`.*

### Step 5: Test the Integration
Open your browser and navigate to `http://localhost:5173/` to interact with your local instance of PranaAI.
