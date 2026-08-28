import React, { useState, useEffect, useRef } from 'react';
import Login from './Login';
import './App.css';

const getDietGuideline = (dosha) => {
  const d = String(dosha || '').toLowerCase();
  if (d.includes('vata') && d.includes('pitta')) {
    return "Favor warm, cooked, grounding foods that are moderately moist and cooling. Favor sweet, mild spices, and healthy oils like ghee. Limit extremely spicy, dry, or cold foods.";
  }
  if (d.includes('pitta') && d.includes('kapha')) {
    return "Favor light, cooling, and moderately dry foods. Favor bitter, astringent, and mildly pungent tastes. Avoid excessively oily, hot, spicy, or heavy sweet foods.";
  }
  if (d.includes('vata') && d.includes('kapha')) {
    return "Favor warm, cooked, and stimulating foods with warming spices (ginger, cinnamon, black pepper). Limit cold, raw, frozen, and heavy sweet foods.";
  }
  if (d.includes('vata')) {
    return "Favor warm, cooked, nourishing, and slightly oily foods. Focus on sweet, sour, and salty tastes. Avoid cold, raw, dry, or light foods.";
  }
  if (d.includes('pitta')) {
    return "Favor cooling, hydrating, and mildly spiced foods. Favor sweet, bitter, and astringent tastes. Avoid hot, spicy, oily, salty, or highly acidic foods.";
  }
  if (d.includes('kapha')) {
    return "Favor light, warm, dry, and spicy foods. Focus on pungent, bitter, and astringent tastes. Avoid heavy, sweet, cold, oily, or salty foods.";
  }
  return "Favor freshly cooked, warm meals. Eat mindfully in a calm environment to support your digestive fire (Agni).";
};

const getDominantEffect = (recipe, dominantDosha) => {
  if (!dominantDosha) return "Neutral";
  let effects = [];
  if (dominantDosha.toLowerCase().includes("vata")) {
    effects.push(`Vata: ${recipe.dosha_effect.Vata}`);
  }
  if (dominantDosha.toLowerCase().includes("pitta")) {
    effects.push(`Pitta: ${recipe.dosha_effect.Pitta}`);
  }
  if (dominantDosha.toLowerCase().includes("kapha")) {
    effects.push(`Kapha: ${recipe.dosha_effect.Kapha}`);
  }
  return effects.join(" | ");
};

function App() {
  const [token, setToken] = useState(() => localStorage.getItem('prana_token') || '');
  const [username, setUsername] = useState(() => localStorage.getItem('prana_username') || '');
  
  const [messages, setMessages] = useState([
    {
      text: "Hello! I am your Ayurcare Agent. To guide you, I will collect some details about your symptoms and lifestyle.\n\nTo begin, what main symptoms are you experiencing today?",
      sender: 'agent',
      isWarning: false
    }
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [initialLoading, setInitialLoading] = useState(false);
  
  // Dosha state: Vata, Pitta, Kapha breakdown
  const [doshaState, setDoshaState] = useState(null);

  // Tracker state variables
  const [activeTab, setActiveTab] = useState('chat'); // 'chat' or 'tracker'
  const [trackerDate, setTrackerDate] = useState(() => {
    const today = new Date();
    const year = today.getFullYear();
    const month = String(today.getMonth() + 1).padStart(2, '0');
    const day = String(today.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  });
  const [trackerData, setTrackerData] = useState(null);
  const [trackerLoading, setTrackerLoading] = useState(false);
  const [trackerError, setTrackerError] = useState(null);

  // Diet state variables
  const [recipes, setRecipes] = useState([]);
  const [loggedMeals, setLoggedMeals] = useState([]);
  const [dietLoading, setDietLoading] = useState(false);
  const [dietError, setDietError] = useState(null);
  const [selectedRecipe, setSelectedRecipe] = useState(null);

  // Consultation history state variables
  const [archivedConsultations, setArchivedConsultations] = useState([]);
  const [selectedArchivedId, setSelectedArchivedId] = useState(null);
  
  const messagesEndRef = useRef(null);

  const fetchConsultations = async () => {
    if (!token) return;
    const API_URL = import.meta.env.VITE_API_URL || '';
    try {
      const response = await fetch(`${API_URL}/api/consultations`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      if (response.status === 401) {
        handleLogoutLocal();
        return;
      }
      if (!response.ok) {
        throw new Error("Failed to fetch consultations");
      }
      const data = await response.json();
      setArchivedConsultations(data.consultations || []);
    } catch (err) {
      console.error("Error fetching consultations:", err);
    }
  };

  const handleArchiveCurrentSession = async () => {
    if (!token) return;
    if (!window.confirm("Archive this conversation and start a new consultation?")) return;
    
    setLoading(true);
    const API_URL = import.meta.env.VITE_API_URL || '';
    try {
      const response = await fetch(`${API_URL}/api/consultations/archive`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      if (response.status === 401) {
        handleLogoutLocal();
        return;
      }
      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.error || "Failed to archive consultation");
      }
      const data = await response.json();
      setArchivedConsultations(data.consultations);
      setMessages(data.active_chat_history);
      setDoshaState(null);
      setSelectedArchivedId(null);
      alert("Consultation archived successfully! Starting a new active session.");
    } catch (err) {
      console.error("Error archiving session:", err);
      alert(err.message || "Failed to archive conversation.");
    } finally {
      setLoading(false);
    }
  };

  const fetchDietData = async (dateString) => {
    if (!token) return;
    setDietLoading(true);
    setDietError(null);
    const API_URL = import.meta.env.VITE_API_URL || '';
    try {
      const response = await fetch(`${API_URL}/api/recipes?date=${dateString}`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      if (response.status === 401) {
        handleLogoutLocal();
        return;
      }
      if (!response.ok) {
        throw new Error("Failed to fetch diet data");
      }
      const data = await response.json();
      if (data.no_profile) {
        setDietError(data.error);
        setRecipes([]);
        setLoggedMeals([]);
      } else {
        setRecipes(data.recipes);
        setLoggedMeals(data.logged_meals);
      }
    } catch (err) {
      console.error("Error fetching diet data:", err);
      setDietError("Failed to load recipes.");
    } finally {
      setDietLoading(false);
    }
  };

  const handleLogMeal = async (recipeId) => {
    if (!token) return;
    
    const recipeObj = recipes.find(r => r.id === recipeId);
    const mockEntry = {
      recipe_id: recipeId,
      name: recipeObj ? recipeObj.name : "Ayurvedic Meal",
      logged_at: new Date().toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', hour12: false })
    };
    
    setLoggedMeals(prev => [...prev, mockEntry]);
    setSelectedRecipe(null);
    
    const API_URL = import.meta.env.VITE_API_URL || '';
    try {
      const response = await fetch(`${API_URL}/api/recipes/log`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          date: trackerDate,
          recipe_id: recipeId,
          local_time: mockEntry.logged_at
        })
      });
      if (response.status === 401) {
        handleLogoutLocal();
        return;
      }
      if (!response.ok) {
        throw new Error("Failed to log meal");
      }
      const data = await response.json();
      setLoggedMeals(data.logged_meals);
    } catch (err) {
      console.error("Error logging meal:", err);
      fetchDietData(trackerDate);
    }
  };

  const fetchTrackerData = async (dateString) => {
    if (!token) return;
    setTrackerLoading(true);
    setTrackerError(null);
    const API_URL = import.meta.env.VITE_API_URL || '';
    try {
      const response = await fetch(`${API_URL}/api/tracker?date=${dateString}`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      if (response.status === 401) {
        handleLogoutLocal();
        return;
      }
      if (!response.ok) {
        throw new Error("Failed to fetch tracker data");
      }
      const data = await response.json();
      if (data.no_profile) {
        setTrackerError(data.error);
        setTrackerData(null);
      } else {
        setTrackerData(data.tracker);
      }
    } catch (err) {
      console.error("Error fetching tracker data:", err);
      setTrackerError("Failed to load daily routines.");
    } finally {
      setTrackerLoading(false);
    }
  };

  const handleToggleTask = async (taskIndex) => {
    if (!token || !trackerData) return;
    
    // Optimistic UI update
    const updatedTasks = [...trackerData.tasks];
    updatedTasks[taskIndex] = {
      ...updatedTasks[taskIndex],
      completed: !updatedTasks[taskIndex].completed
    };
    
    setTrackerData(prev => ({
      ...prev,
      tasks: updatedTasks
    }));
    
    const API_URL = import.meta.env.VITE_API_URL || '';
    try {
      const response = await fetch(`${API_URL}/api/tracker/toggle`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          date: trackerDate,
          task_index: taskIndex
        })
      });
      if (response.status === 401) {
        handleLogoutLocal();
        return;
      }
      if (!response.ok) {
        throw new Error("Failed to toggle task");
      }
      const data = await response.json();
      setTrackerData(data.tracker);
    } catch (err) {
      console.error("Error toggling task:", err);
      fetchTrackerData(trackerDate);
    }
  };

  const handleNavigateDate = (direction) => {
    const current = new Date(trackerDate);
    if (isNaN(current.getTime())) return;
    
    current.setDate(current.getDate() + direction);
    
    const year = current.getFullYear();
    const month = String(current.getMonth() + 1).padStart(2, '0');
    const day = String(current.getDate()).padStart(2, '0');
    setTrackerDate(`${year}-${month}-${day}`);
  };
  
  const formatDatePretty = (dateStr) => {
    try {
      const d = new Date(dateStr);
      if (isNaN(d.getTime())) return dateStr;
      
      const today = new Date();
      if (d.toDateString() === today.toDateString()) {
        return "Today";
      }
      
      const yesterday = new Date();
      yesterday.setDate(yesterday.getDate() - 1);
      if (d.toDateString() === yesterday.toDateString()) {
        return "Yesterday";
      }
      
      return d.toLocaleDateString(undefined, { 
        weekday: 'short', 
        month: 'short', 
        day: 'numeric',
        year: 'numeric'
      });
    } catch (e) {
      return dateStr;
    }
  };

  // Auto scroll to bottom
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, loading]);

  // Load chat history when token changes or on mount
  useEffect(() => {
    if (token) {
      fetchChatHistory();
      fetchConsultations();
    }
  }, [token]);

  // Load tracker data when tab, date, or token changes
  useEffect(() => {
    if (token && activeTab === 'tracker') {
      fetchTrackerData(trackerDate);
    }
  }, [token, trackerDate, activeTab, doshaState]);

  // Load diet data when tab, date, or token changes
  useEffect(() => {
    if (token && activeTab === 'diet') {
      fetchDietData(trackerDate);
    }
  }, [token, trackerDate, activeTab, doshaState]);

  const fetchChatHistory = async () => {
    setInitialLoading(true);
    const API_URL = import.meta.env.VITE_API_URL || '';
    try {
      const response = await fetch(`${API_URL}/api/chat/history`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      if (response.status === 401) {
        handleLogoutLocal();
        return;
      }
      if (!response.ok) {
        throw new Error("Failed to load chat history");
      }
      const data = await response.json();
      if (data.chat_history && data.chat_history.length > 0) {
        setMessages(data.chat_history);
      }
      if (data.dosha_state) {
        setDoshaState(data.dosha_state);
      } else {
        setDoshaState(null);
      }
    } catch (err) {
      console.error("Error loading chat history:", err);
    } finally {
      setInitialLoading(false);
    }
  };

  const handleLoginSuccess = (newToken, newUsername) => {
    localStorage.setItem('prana_token', newToken);
    localStorage.setItem('prana_username', newUsername);
    setToken(newToken);
    setUsername(newUsername);
  };

  const handleLogoutLocal = () => {
    localStorage.removeItem('prana_token');
    localStorage.removeItem('prana_username');
    setToken('');
    setUsername('');
    setMessages([
      {
        text: "Hello! I am your Ayurcare Agent. To guide you, I will collect some details about your symptoms and lifestyle.\n\nTo begin, what main symptoms are you experiencing today?",
        sender: 'agent',
        isWarning: false
      }
    ]);
    setDoshaState(null);
    setActiveTab('chat');
    setTrackerData(null);
    setTrackerError(null);
    setRecipes([]);
    setLoggedMeals([]);
    setDietError(null);
    setSelectedRecipe(null);
    setArchivedConsultations([]);
    setSelectedArchivedId(null);
  };

  const handleLogout = async () => {
    const API_URL = import.meta.env.VITE_API_URL || '';
    try {
      await fetch(`${API_URL}/api/logout`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
    } catch (err) {
      console.error("Error calling logout endpoint:", err);
    } finally {
      handleLogoutLocal();
    }
  };

  const handleClearChat = async () => {
    if (!window.confirm("Are you sure you want to reset your conversation?")) return;
    setLoading(true);
    const API_URL = import.meta.env.VITE_API_URL || '';
    try {
      const response = await fetch(`${API_URL}/api/chat/clear`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      if (response.status === 401) {
        handleLogoutLocal();
        return;
      }
      if (!response.ok) {
        throw new Error("Failed to clear chat");
      }
      setMessages([
        {
          text: "Hello! I am your Ayurcare Agent. To guide you, I will collect some details about your symptoms and lifestyle.\n\nTo begin, what main symptoms are you experiencing today?",
          sender: 'agent',
          isWarning: false
        }
      ]);
      setDoshaState(null);
      setActiveTab('chat');
      setTrackerData(null);
      setTrackerError(null);
      setRecipes([]);
      setLoggedMeals([]);
      setDietError(null);
      setSelectedRecipe(null);
      setArchivedConsultations([]);
      setSelectedArchivedId(null);
    } catch (err) {
      console.error("Error clearing chat:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleDownloadReport = () => {
    if (!token || !doshaState) return;
    const API_URL = import.meta.env.VITE_API_URL || '';
    const downloadUrl = `${API_URL}/api/download_report?token=${token}`;
    window.open(downloadUrl, '_blank');
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!input.trim() || loading) return;

    const userMessage = input.trim();
    setInput('');
    setMessages((prev) => [...prev, { text: userMessage, sender: 'user', isWarning: false }]);
    setLoading(true);

    const API_URL = import.meta.env.VITE_API_URL || '';

    try {
      const response = await fetch(`${API_URL}/api/agent`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          message: userMessage
        })
      });

      if (response.status === 401) {
        handleLogoutLocal();
        return;
      }

      if (!response.ok) {
        throw new Error("Failed to contact the wellness assistant");
      }

      const data = await response.json();
      
      const isSafetyWarning = data.reply.includes("SAFETY WARNING:") || data.reply.includes("emergency care") || data.reply.includes("see a doctor");

      setMessages((prev) => [...prev, {
        text: data.reply,
        sender: 'agent',
        isWarning: isSafetyWarning
      }]);

      if (data.dosha_state) {
        setDoshaState(data.dosha_state);
      }

    } catch (error) {
      setMessages((prev) => [...prev, {
        text: "I apologize, but I encountered an error connecting to the wellness engine. Please try again later.",
        sender: 'agent',
        isWarning: true
      }]);
    } finally {
      setLoading(false);
    }
  };

  // Helper to map dosha strength from Prakriti JSON to percentage heights
  const getDoshaHeight = (doshaName) => {
    const activeArchive = selectedArchivedId ? archivedConsultations.find(c => c.id === selectedArchivedId) : null;
    const currentDoshaState = activeArchive ? activeArchive.dosha_state : doshaState;

    if (!currentDoshaState || !currentDoshaState.constitution_breakdown) {
      return '15%'; // Default resting/breathing height
    }
    const val = currentDoshaState.constitution_breakdown[doshaName];
    if (!val) return '15%';
    
    // Support either descriptive tags (High/Medium/Low) or quantitative values
    const stringVal = String(val).toLowerCase();
    if (stringVal.includes('high') || stringVal === 'h') return '95%';
    if (stringVal.includes('medium') || stringVal === 'med' || stringVal === 'm') return '60%';
    if (stringVal.includes('low') || stringVal === 'l') return '25%';
    
    // Support raw numbers or percentages
    const numVal = parseInt(stringVal);
    if (!isNaN(numVal)) {
      return `${Math.min(Math.max(numVal, 15), 100)}%`;
    }
    return '15%';
  };

  const isDoshaActive = (doshaName) => {
    const activeArchive = selectedArchivedId ? archivedConsultations.find(c => c.id === selectedArchivedId) : null;
    const currentDoshaState = activeArchive ? activeArchive.dosha_state : doshaState;

    if (!currentDoshaState || !currentDoshaState.dominant_dosha) return false;
    return currentDoshaState.dominant_dosha.toLowerCase().includes(doshaName.toLowerCase());
  };

  if (!token) {
    return <Login onLoginSuccess={handleLoginSuccess} />;
  }

  if (initialLoading) {
    return (
      <div className="loading-screen">
        <div className="dot-pulse">
          <div className="dot"></div>
          <div className="dot"></div>
          <div className="dot"></div>
        </div>
        <p style={{ marginTop: '16px', color: 'var(--text-muted)' }}>Restoring your wellness profile...</p>
      </div>
    );
  }

  return (
    <div className="app-container">
      {/* Signature Vertical Pulse Bars Panel */}
      <div className="pulse-bars-panel">
        <div className="panel-title">Constitutional Pulse</div>
        <div className="bars-container">
          {/* Vata Bar */}
          <div className="pulse-bar-wrapper vata">
            <div className="pulse-bar-track">
              <div className="pulse-bar-fill" style={{ height: getDoshaHeight('Vata') }}></div>
            </div>
            <div className={`pulse-bar-label ${isDoshaActive('Vata') ? 'active' : ''}`}>Vata</div>
          </div>

          {/* Pitta Bar */}
          <div className="pulse-bar-wrapper pitta">
            <div className="pulse-bar-track">
              <div className="pulse-bar-fill" style={{ height: getDoshaHeight('Pitta') }}></div>
            </div>
            <div className={`pulse-bar-label ${isDoshaActive('Pitta') ? 'active' : ''}`}>Pitta</div>
          </div>

          {/* Kapha Bar */}
          <div className="pulse-bar-wrapper kapha">
            <div className="pulse-bar-track">
              <div className="pulse-bar-fill" style={{ height: getDoshaHeight('Kapha') }}></div>
            </div>
            <div className={`pulse-bar-label ${isDoshaActive('Kapha') ? 'active' : ''}`}>Kapha</div>
          </div>
        </div>
      </div>

      {/* Main Chat Interface */}
      <div className="main-chat-container">
        <div className="header">
          <div>
            <h1>Ayurcare Guidance</h1>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Welcome, {username}</span>
          </div>
          <div className="header-actions">
            <button 
              onClick={handleClearChat} 
              className="action-button reset-button"
              title="Reset conversation"
              disabled={loading}
            >
              Reset
            </button>
            <button 
              onClick={handleLogout} 
              className="action-button logout-button"
              title="Logout"
            >
              Logout
            </button>
          </div>
        </div>

        {/* Tab Navigation Menu */}
        <div className="tab-navigation">
          <button 
            className={`tab-button ${activeTab === 'chat' ? 'active' : ''}`}
            onClick={() => setActiveTab('chat')}
          >
            Consultation Chat
          </button>
          <button 
            className={`tab-button ${activeTab === 'tracker' ? 'active' : ''}`}
            onClick={() => setActiveTab('tracker')}
          >
            Daily Dinacharya
          </button>
          <button 
            className={`tab-button ${activeTab === 'diet' ? 'active' : ''}`}
            onClick={() => setActiveTab('diet')}
          >
            Ayurvedic Diet
          </button>
        </div>

        {activeTab === 'chat' && (
          <div className="chat-tab-container">
            <div className="chat-main-area">
              {selectedArchivedId && (
                <div className="historical-banner">
                  <span>⚠️ Viewing archived consultation from {formatDatePretty(archivedConsultations.find(c => c.id === selectedArchivedId)?.date)}.</span>
                  <button 
                    className="back-to-active-btn" 
                    onClick={() => {
                      setSelectedArchivedId(null);
                      fetchChatHistory();
                    }}
                  >
                    Back to Active Chat
                  </button>
                </div>
              )}

              <div className="messages-list">
                {(selectedArchivedId 
                  ? (archivedConsultations.find(c => c.id === selectedArchivedId)?.chat_history || [])
                  : messages
                ).map((msg, index) => (
                  <div 
                    key={index} 
                    className={`message-wrapper ${msg.sender} ${msg.isWarning ? 'safety-warning' : ''}`}
                  >
                    <div className="message-bubble">{msg.text}</div>
                    <div className="message-meta">{msg.sender}</div>
                  </div>
                ))}
                
                {loading && !selectedArchivedId && (
                  <div className="loading-wrapper">
                    <div className="dot-pulse">
                      <div className="dot"></div>
                      <div className="dot"></div>
                      <div className="dot"></div>
                    </div>
                  </div>
                )}
                <div ref={messagesEndRef} />
              </div>

              {((selectedArchivedId 
                ? archivedConsultations.find(c => c.id === selectedArchivedId)?.dosha_state 
                : doshaState
              )) && (
                <div className="download-report-container">
                  <button 
                    onClick={() => {
                      if (selectedArchivedId) {
                        const API_URL = import.meta.env.VITE_API_URL || '';
                        window.open(`${API_URL}/api/download_report?token=${token}&consultation_id=${selectedArchivedId}`, '_blank');
                      } else {
                        handleDownloadReport();
                      }
                    }}
                    className="download-button"
                  >
                    Download {selectedArchivedId ? "Archived" : "Weekly"} Wellness Report
                  </button>
                </div>
              )}

              <form onSubmit={handleSubmit} className="input-form">
                <input
                  type="text"
                  className="message-input"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  placeholder={selectedArchivedId ? "Chat disabled in archive viewer" : "Type your reply..."}
                  disabled={loading || !!selectedArchivedId}
                  maxLength={500}
                />
                <button 
                  type="submit" 
                  className="send-button"
                  disabled={loading || !input.trim() || !!selectedArchivedId}
                >
                  Send
                </button>
              </form>
            </div>

            <div className="consultation-sidebar">
              <h3>Consultation History</h3>
              
              <button 
                className="archive-session-btn"
                onClick={handleArchiveCurrentSession}
                disabled={loading || !!selectedArchivedId || !doshaState || messages.length <= 1}
                title="Archive current consultation and start a fresh session"
              >
                + New Consultation
              </button>

              <div className="consultations-list">
                {archivedConsultations.length === 0 ? (
                  <p className="no-consultations-text">No archived consultations yet.</p>
                ) : (
                  archivedConsultations.map(c => (
                    <div 
                      key={c.id} 
                      className={`consultation-item ${selectedArchivedId === c.id ? 'active' : ''}`}
                      onClick={() => setSelectedArchivedId(c.id)}
                    >
                      <div className="consultation-item-date">{formatDatePretty(c.date)}</div>
                      <div className="consultation-item-summary">{c.summary}</div>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        )}

        {activeTab === 'tracker' && (
          <div className="tracker-view">
            {trackerError ? (
              <div className="tracker-error-container">
                <div className="lock-icon">🔒</div>
                <h3>Tracker Locked</h3>
                <p>{trackerError}</p>
                <button className="goto-chat-button" onClick={() => setActiveTab('chat')}>
                  Start Consultation Chat
                </button>
              </div>
            ) : trackerLoading && !trackerData ? (
              <div className="tracker-loading">
                <div className="dot-pulse">
                  <div className="dot"></div>
                  <div className="dot"></div>
                  <div className="dot"></div>
                </div>
                <p>Loading your routine...</p>
              </div>
            ) : trackerData ? (
              <div className="tracker-content">
                <div className="tracker-meta-header">
                  <span className="dosha-badge">{trackerData.dominant_dosha} Balancing Routine</span>
                </div>
                
                <div className="date-navigator">
                  <button className="nav-arrow" onClick={() => handleNavigateDate(-1)}>❮</button>
                  <span className="current-date">{formatDatePretty(trackerDate)}</span>
                  <button className="nav-arrow" onClick={() => handleNavigateDate(1)}>❯</button>
                </div>
                
                <div className="tracker-dashboard">
                  <div className="streak-card current">
                    <div className="streak-value">🔥 {trackerData.streak_count}</div>
                    <div className="streak-label">Current Streak</div>
                  </div>
                  <div className="streak-card longest">
                    <div className="streak-value">⭐ {trackerData.longest_streak}</div>
                    <div className="streak-label">Longest Streak</div>
                  </div>
                </div>
                
                {(() => {
                  const total = trackerData.tasks.length;
                  const completed = trackerData.tasks.filter(t => t.completed).length;
                  const pct = total > 0 ? Math.round((completed / total) * 100) : 0;
                  return (
                    <div className="progress-section">
                      <div className="progress-text-row">
                        <span>Daily Completion</span>
                        <span>{pct}% ({completed}/{total})</span>
                      </div>
                      <div className="progress-bar-track">
                        <div className="progress-bar-fill" style={{ width: `${pct}%` }}></div>
                      </div>
                    </div>
                  );
                })()}
                
                <div className="tasks-list-container">
                  <h3>Daily Dinacharya Practices</h3>
                  <div className="tasks-checkbox-list">
                    {trackerData.tasks.map((task, idx) => (
                      <label 
                        key={task.id} 
                        className={`task-checkbox-item ${task.completed ? 'completed' : ''}`}
                      >
                        <input
                          type="checkbox"
                          checked={task.completed}
                          onChange={() => handleToggleTask(idx)}
                          disabled={trackerLoading}
                        />
                        <span className="custom-checkbox"></span>
                        <span className="task-text">{task.text}</span>
                      </label>
                    ))}
                  </div>
                </div>
                
                <div className="tracker-footer-tip">
                  💡 <strong>Ayurvedic Tip:</strong> Consistency (Dinacharya) is key to balancing your constitution. Performing these habits at the same time each day strengthens your digestive fire (Agni) and stabilizes the mind.
                </div>
              </div>
            ) : (
              <div className="tracker-placeholder">
                <p>No tracker data available. Complete your intake to unlock.</p>
              </div>
            )}
          </div>
        )}

        {activeTab === 'diet' && (
          <div className="tracker-view diet-view">
            {dietError ? (
              <div className="tracker-error-container">
                <div className="lock-icon">🔒</div>
                <h3>Diet Guidelines Locked</h3>
                <p>{dietError}</p>
                <button className="goto-chat-button" onClick={() => setActiveTab('chat')}>
                  Start Consultation Chat
                </button>
              </div>
            ) : dietLoading && recipes.length === 0 ? (
              <div className="tracker-loading">
                <div className="dot-pulse">
                  <div className="dot"></div>
                  <div className="dot"></div>
                  <div className="dot"></div>
                </div>
                <p>Loading healthy recipes...</p>
              </div>
            ) : (
              <div className="tracker-content">
                {doshaState && (
                  <div className="diet-guideline-card">
                    <h4>{doshaState.dominant_dosha} Diet Guidelines</h4>
                    <p>{getDietGuideline(doshaState.dominant_dosha)}</p>
                  </div>
                )}

                <div className="diet-dashboard-row">
                  <div className="date-navigator">
                    <button className="nav-arrow" onClick={() => handleNavigateDate(-1)}>❮</button>
                    <span className="current-date">{formatDatePretty(trackerDate)}</span>
                    <button className="nav-arrow" onClick={() => handleNavigateDate(1)}>❯</button>
                  </div>
                </div>

                <div className="logged-meals-section">
                  <h3>Logged Meals for {formatDatePretty(trackerDate)}</h3>
                  {loggedMeals.length === 0 ? (
                    <p className="no-meals-text">No meals logged for this day yet. Choose a recipe below to log it.</p>
                  ) : (
                    <div className="logged-meals-list">
                      {loggedMeals.map((meal, idx) => (
                        <div key={idx} className="logged-meal-item">
                          <span className="meal-time">🕒 {meal.logged_at}</span>
                          <span className="meal-name">{meal.name}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <div className="recipes-section">
                  <h3>Recommended Ayurvedic Recipes</h3>
                  <div className="recipes-grid">
                    {recipes.map(recipe => (
                      <div 
                        key={recipe.id} 
                        className="recipe-card"
                        onClick={() => setSelectedRecipe(recipe)}
                      >
                        <div className="recipe-card-header">
                          <span className="recipe-meal-type">{recipe.meal_type}</span>
                          <span className="recipe-time">⏱️ {recipe.prep_time}</span>
                        </div>
                        <h4>{recipe.name}</h4>
                        <p className="recipe-desc">{recipe.description}</p>
                        <div className="recipe-effects-row">
                          <span className="recipe-effect-label">
                            {doshaState ? getDominantEffect(recipe, doshaState.dominant_dosha) : ""}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {/* Recipe Details Modal */}
            {selectedRecipe && (
              <div className="recipe-modal-overlay" onClick={() => setSelectedRecipe(null)}>
                <div className="recipe-modal-card" onClick={e => e.stopPropagation()}>
                  <div className="recipe-modal-header">
                    <h2>{selectedRecipe.name}</h2>
                    <button className="recipe-modal-close" onClick={() => setSelectedRecipe(null)}>×</button>
                  </div>
                  
                  <div className="recipe-modal-body">
                    <div className="recipe-modal-meta">
                      <span><strong>Type:</strong> {selectedRecipe.meal_type}</span>
                      <span><strong>Prep:</strong> {selectedRecipe.prep_time}</span>
                      <span><strong>Cook:</strong> {selectedRecipe.cook_time}</span>
                    </div>
                    
                    <p className="recipe-modal-description">{selectedRecipe.description}</p>
                    
                    <div className="recipe-modal-ingredients">
                      <h3>Ingredients</h3>
                      <ul>
                        {selectedRecipe.ingredients.map((ing, idx) => (
                          <li key={idx}>{ing}</li>
                        ))}
                      </ul>
                    </div>
                    
                    <div className="recipe-modal-instructions">
                      <h3>Instructions</h3>
                      <ol>
                        {selectedRecipe.instructions.map((step, idx) => (
                          <li key={idx}>{step}</li>
                        ))}
                      </ol>
                    </div>
                  </div>
                  
                  <div className="recipe-modal-footer">
                    <button 
                      className="log-meal-button"
                      onClick={() => handleLogMeal(selectedRecipe.id)}
                    >
                      Log as Eaten today
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default App;
