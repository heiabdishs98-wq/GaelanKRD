from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timedelta
from emergentintegrations.llm.chat import LlmChat, UserMessage
import json
from jose import JWTError, jwt
from passlib.context import CryptContext
import hashlib

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# Security
SECRET_KEY = os.environ.get('SECRET_KEY', 'your-secret-key-here')
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Create the main app without a prefix
app = FastAPI(title="KurdAI API", version="1.0.0")

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Models
class User(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    email: str
    username: str
    password_hash: str
    is_admin: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class UserCreate(BaseModel):
    email: str
    username: str
    password: str

class UserLogin(BaseModel):
    email: str
    password: str

class UserResponse(BaseModel):
    id: str
    email: str
    username: str
    is_admin: bool
    created_at: datetime

class ChatSession(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    title: str = "New Chat"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class ChatMessage(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    user_id: str
    content: str
    role: str  # 'user' or 'assistant'
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    language: str = "en"

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    language: Optional[str] = "en"

class ChatResponse(BaseModel):
    message: str
    session_id: str
    ai_response: str
    timestamp: datetime

class AdminPrompt(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    content: str
    is_active: bool = True
    created_by: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

class AdminPromptCreate(BaseModel):
    name: str
    content: str

class StatusCheck(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_name: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class StatusCheckCreate(BaseModel):
    client_name: str

# Utility functions
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    user = await db.users.find_one({"id": user_id})
    if user is None:
        raise credentials_exception
    return User(**user)

async def get_current_admin_user(current_user: User = Depends(get_current_user)):
    if not current_user.is_admin:
        raise HTTPException(
            status_code=403,
            detail="Not enough permissions"
        )
    return current_user

# Authentication endpoints
@api_router.post("/auth/register", response_model=UserResponse)
async def register(user_data: UserCreate):
    # Check if user already exists
    existing_user = await db.users.find_one({"email": user_data.email})
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    existing_username = await db.users.find_one({"username": user_data.username})
    if existing_username:
        raise HTTPException(status_code=400, detail="Username already taken")
    
    # Create new user
    password_hash = get_password_hash(user_data.password)
    user = User(
        email=user_data.email,
        username=user_data.username,
        password_hash=password_hash
    )
    
    await db.users.insert_one(user.dict())
    return UserResponse(**user.dict())

@api_router.post("/auth/login")
async def login(user_data: UserLogin):
    user = await db.users.find_one({"email": user_data.email})
    if not user or not verify_password(user_data.password, user["password_hash"]):
        raise HTTPException(
            status_code=401,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user["id"]}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer", "user": UserResponse(**user)}

@api_router.get("/auth/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    return UserResponse(**current_user.dict())

# Chat endpoints
@api_router.post("/chat/send", response_model=ChatResponse)
async def send_message(chat_request: ChatRequest, current_user: User = Depends(get_current_user)):
    try:
        # Get or create session
        session_id = chat_request.session_id
        if not session_id:
            session = ChatSession(user_id=current_user.id)
            await db.chat_sessions.insert_one(session.dict())
            session_id = session.id
        else:
            session = await db.chat_sessions.find_one({"id": session_id, "user_id": current_user.id})
            if not session:
                raise HTTPException(status_code=404, detail="Session not found")
        
        # Save user message
        user_message = ChatMessage(
            session_id=session_id,
            user_id=current_user.id,
            content=chat_request.message,
            role="user",
            language=chat_request.language
        )
        await db.chat_messages.insert_one(user_message.dict())
        
        # Get chat history for context
        messages = await db.chat_messages.find(
            {"session_id": session_id}
        ).sort("timestamp", 1).to_list(100)
        
        # Create system message with custom prompt
        system_message = f"""You are KurdAI, a helpful AI assistant. You are designed to be:
        1. Multilingual - Respond in the user's language ({chat_request.language})
        2. Code-aware - Format code blocks properly with syntax highlighting
        3. Helpful and professional
        4. Capable of handling complex technical questions
        
        When showing code, use proper markdown formatting with language tags.
        Always maintain context from previous messages in this conversation.
        """
        
        # Initialize LLM chat
        emergent_key = os.environ.get('EMERGENT_LLM_KEY')
        if not emergent_key:
            raise HTTPException(status_code=500, detail="LLM service not configured")
        
        chat = LlmChat(
            api_key=emergent_key,
            session_id=session_id,
            system_message=system_message
        ).with_model("gemini", "gemini-2.0-flash")
        
        # Send message to AI
        user_msg = UserMessage(text=chat_request.message)
        ai_response = await chat.send_message(user_msg)
        
        # Save AI response
        ai_message = ChatMessage(
            session_id=session_id,
            user_id=current_user.id,
            content=ai_response,
            role="assistant",
            language=chat_request.language
        )
        await db.chat_messages.insert_one(ai_message.dict())
        
        # Update session
        await db.chat_sessions.update_one(
            {"id": session_id},
            {"$set": {"updated_at": datetime.utcnow()}}
        )
        
        return ChatResponse(
            message=chat_request.message,
            session_id=session_id,
            ai_response=ai_response,
            timestamp=datetime.utcnow()
        )
        
    except Exception as e:
        logging.error(f"Chat error: {str(e)}")
        raise HTTPException(status_code=500, detail="Chat service error")

@api_router.get("/chat/sessions", response_model=List[ChatSession])
async def get_chat_sessions(current_user: User = Depends(get_current_user)):
    sessions = await db.chat_sessions.find(
        {"user_id": current_user.id}
    ).sort("updated_at", -1).to_list(100)
    return [ChatSession(**session) for session in sessions]

@api_router.get("/chat/sessions/{session_id}/messages", response_model=List[ChatMessage])
async def get_chat_messages(session_id: str, current_user: User = Depends(get_current_user)):
    # Verify session belongs to user
    session = await db.chat_sessions.find_one({"id": session_id, "user_id": current_user.id})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    messages = await db.chat_messages.find(
        {"session_id": session_id}
    ).sort("timestamp", 1).to_list(1000)
    return [ChatMessage(**message) for message in messages]

@api_router.delete("/chat/sessions/{session_id}")
async def delete_chat_session(session_id: str, current_user: User = Depends(get_current_user)):
    # Verify session belongs to user
    session = await db.chat_sessions.find_one({"id": session_id, "user_id": current_user.id})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Delete messages and session
    await db.chat_messages.delete_many({"session_id": session_id})
    await db.chat_sessions.delete_one({"id": session_id})
    
    return {"message": "Session deleted successfully"}

# Admin endpoints
@api_router.get("/admin/analytics")
async def get_analytics(current_user: User = Depends(get_current_admin_user)):
    # Get user count
    user_count = await db.users.count_documents({})
    
    # Get chat session count
    session_count = await db.chat_sessions.count_documents({})
    
    # Get message count
    message_count = await db.chat_messages.count_documents({})
    
    # Get recent activity
    recent_sessions = await db.chat_sessions.find().sort("updated_at", -1).limit(10).to_list(10)
    recent_users = await db.users.find().sort("created_at", -1).limit(10).to_list(10)
    
    return {
        "user_count": user_count,
        "session_count": session_count,
        "message_count": message_count,
        "recent_sessions": recent_sessions,
        "recent_users": recent_users
    }

@api_router.post("/admin/prompts", response_model=AdminPrompt)
async def create_admin_prompt(prompt_data: AdminPromptCreate, current_user: User = Depends(get_current_admin_user)):
    prompt = AdminPrompt(
        name=prompt_data.name,
        content=prompt_data.content,
        created_by=current_user.id
    )
    await db.admin_prompts.insert_one(prompt.dict())
    return prompt

@api_router.get("/admin/prompts", response_model=List[AdminPrompt])
async def get_admin_prompts(current_user: User = Depends(get_current_admin_user)):
    prompts = await db.admin_prompts.find().sort("created_at", -1).to_list(100)
    return [AdminPrompt(**prompt) for prompt in prompts]

@api_router.put("/admin/prompts/{prompt_id}")
async def update_admin_prompt(prompt_id: str, prompt_data: AdminPromptCreate, current_user: User = Depends(get_current_admin_user)):
    await db.admin_prompts.update_one(
        {"id": prompt_id},
        {"$set": {
            "name": prompt_data.name,
            "content": prompt_data.content
        }}
    )
    return {"message": "Prompt updated successfully"}

@api_router.delete("/admin/prompts/{prompt_id}")
async def delete_admin_prompt(prompt_id: str, current_user: User = Depends(get_current_admin_user)):
    await db.admin_prompts.delete_one({"id": prompt_id})
    return {"message": "Prompt deleted successfully"}

# Legacy endpoints
@api_router.get("/")
async def root():
    return {"message": "KurdAI API is running"}

@api_router.post("/status", response_model=StatusCheck)
async def create_status_check(input: StatusCheckCreate):
    status_dict = input.dict()
    status_obj = StatusCheck(**status_dict)
    _ = await db.status_checks.insert_one(status_obj.dict())
    return status_obj

@api_router.get("/status", response_model=List[StatusCheck])
async def get_status_checks():
    status_checks = await db.status_checks.find().to_list(1000)
    return [StatusCheck(**status_check) for status_check in status_checks]

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()