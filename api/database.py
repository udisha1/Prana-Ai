import os
import uuid
import logging
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
import pymongo

logger = logging.getLogger(__name__)

# Fetch MongoDB URI from environment or default to local DB
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/prana_ai")

_mongo_client = None
_use_fallback = False

# In-memory database fallback structures
_mock_users = {}      # username -> user_doc
_mock_sessions = {}   # token -> username
_mock_chats = {}      # username -> {"session_data": {...}}

def init_db():
    global _mongo_client, _use_fallback
    try:
        # Short timeout to fail quickly if MongoDB is not running locally
        _mongo_client = pymongo.MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000)
        # Ping to check if server is active
        _mongo_client.admin.command('ping')
        logger.info("Successfully connected to MongoDB.")
        
        # Ensure collections and indexes are created
        try:
            db = _mongo_client.get_default_database()
        except Exception:
            db = _mongo_client["prana_ai"]
            
        db.users.create_index("username", unique=True)
        db.tokens.create_index("token", unique=True)
        _use_fallback = False
    except Exception as e:
        logger.warning(f"MongoDB connection failed: {e}. Falling back to IN-MEMORY database mode.")
        _use_fallback = True

def get_db():
    global _mongo_client
    if _mongo_client is None:
        init_db()
    if _use_fallback:
        return None
    try:
        return _mongo_client.get_default_database()
    except Exception:
        try:
            return _mongo_client["prana_ai"]
        except Exception as e:
            logger.error(f"Error accessing database: {e}. Switching to in-memory mode.")
            return None

def register_user(username, password):
    username = username.strip().lower()
    if not username or not password:
        return False, "Username and password are required"
        
    db = get_db()
    if db is None and os.environ.get("VERCEL") == "1":
        return False, "Database connection is missing. Please configure MONGO_URI in your Vercel project settings to enable user registration."
    
    password_hash = generate_password_hash(password)
    
    if db is not None:
        try:
            # Check if user already exists
            if db.users.find_one({"username": username}):
                return False, "Username already exists"
            
            db.users.insert_one({
                "username": username,
                "password_hash": password_hash,
                "created_at": datetime.utcnow()
            })
            return True, "User registered successfully"
        except Exception as e:
            logger.error(f"Error registering user in MongoDB: {e}")
            return False, f"Database error: {str(e)}"
    else:
        # Fallback to in-memory storage
        if username in _mock_users:
            return False, "Username already exists"
        _mock_users[username] = {
            "username": username,
            "password_hash": password_hash,
            "created_at": datetime.utcnow()
        }
        return True, "User registered successfully (In-Memory Fallback)"

def authenticate_user(username, password):
    username = username.strip().lower()
    if not username or not password:
        return False, "Username and password are required"
        
    db = get_db()
    if db is None and os.environ.get("VERCEL") == "1":
        return False, "Database connection is missing. Please configure MONGO_URI in your Vercel project settings to enable login."
        
    user = None
    
    if db is not None:
        try:
            user = db.users.find_one({"username": username})
        except Exception as e:
            logger.error(f"Database error during authentication: {e}")
            return False, "Database error during login"
    else:
        user = _mock_users.get(username)
        
    if not user:
        return False, "Invalid username or password"
        
    if not check_password_hash(user["password_hash"], password):
        return False, "Invalid username or password"
        
    # Generate session token
    token = "token_" + str(uuid.uuid4()).replace("-", "")
    
    if db is not None:
        try:
            db.tokens.insert_one({
                "token": token,
                "username": username,
                "created_at": datetime.utcnow()
            })
        except Exception as e:
            logger.error(f"Error storing token in MongoDB: {e}")
            return False, "Database error creating session"
    else:
        _mock_sessions[token] = username
        
    return True, token

def get_user_by_token(token):
    if not token:
        return None
    db = get_db()
    
    if db is not None:
        try:
            doc = db.tokens.find_one({"token": token})
            if doc:
                return doc["username"]
        except Exception as e:
            logger.error(f"Error finding token in MongoDB: {e}")
    else:
        return _mock_sessions.get(token)
    return None

def revoke_token(token):
    if not token:
        return False
    db = get_db()
    
    if db is not None:
        try:
            db.tokens.delete_many({"token": token})
            return True
        except Exception as e:
            logger.error(f"Error revoking token in MongoDB: {e}")
    else:
        if token in _mock_sessions:
            del _mock_sessions[token]
            return True
    return False

def get_user_session(username):
    db = get_db()
    if db is not None:
        try:
            doc = db.sessions.find_one({"username": username})
            if doc:
                return doc.get("session_data")
        except Exception as e:
            logger.error(f"Error fetching session from MongoDB: {e}")
    else:
        chat_doc = _mock_chats.get(username)
        if chat_doc:
            return chat_doc.get("session_data")
    return None

def save_user_session(username, session_data):
    db = get_db()
    if db is not None:
        try:
            db.sessions.update_one(
                {"username": username},
                {"$set": {
                    "session_data": session_data, 
                    "updated_at": datetime.utcnow()
                }},
                upsert=True
            )
            return True
        except Exception as e:
            logger.error(f"Error saving session to MongoDB: {e}")
    else:
        if username not in _mock_chats:
            _mock_chats[username] = {}
        _mock_chats[username]["session_data"] = session_data
        return True
    return False

def clear_user_session(username):
    db = get_db()
    if db is not None:
        try:
            db.sessions.delete_many({"username": username})
            return True
        except Exception as e:
            logger.error(f"Error deleting session from MongoDB: {e}")
    else:
        if username in _mock_chats:
            _mock_chats[username] = {}
            return True
    return False
