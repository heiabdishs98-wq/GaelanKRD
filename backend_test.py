#!/usr/bin/env python3
"""
KurdAI Backend API Testing Suite
Tests authentication, AI chat, session management, and admin functionality
"""

import requests
import json
import time
import os
from datetime import datetime
import uuid

# Load backend URL from frontend .env
def get_backend_url():
    try:
        with open('/app/frontend/.env', 'r') as f:
            for line in f:
                if line.startswith('REACT_APP_BACKEND_URL='):
                    base_url = line.split('=', 1)[1].strip()
                    return f"{base_url}/api"
        return "http://localhost:8001/api"  # fallback
    except:
        return "http://localhost:8001/api"  # fallback

BASE_URL = get_backend_url()
print(f"Testing backend at: {BASE_URL}")

# Test data
TEST_USER = {
    "email": "sara.ahmed@kurdai.com",
    "username": "sara_kurdai",
    "password": "SecurePass123!"
}

TEST_ADMIN = {
    "email": "admin@kurdai.com", 
    "username": "admin_kurdai",
    "password": "AdminPass123!"
}

# Global variables for tokens and session data
user_token = None
admin_token = None
user_id = None
admin_id = None
session_id = None

def print_test_header(test_name):
    print(f"\n{'='*60}")
    print(f"TESTING: {test_name}")
    print(f"{'='*60}")

def print_result(success, message, details=None):
    status = "✅ PASS" if success else "❌ FAIL"
    print(f"{status}: {message}")
    if details:
        print(f"Details: {details}")

def test_server_health():
    """Test if the server is running"""
    print_test_header("Server Health Check")
    try:
        response = requests.get(f"{BASE_URL}/", timeout=10)
        if response.status_code == 200:
            print_result(True, "Server is running", response.json())
            return True
        else:
            print_result(False, f"Server returned status {response.status_code}")
            return False
    except Exception as e:
        print_result(False, f"Server connection failed: {str(e)}")
        return False

def test_user_registration():
    """Test user registration endpoint"""
    print_test_header("User Registration")
    global user_id
    
    try:
        response = requests.post(f"{BASE_URL}/auth/register", json=TEST_USER, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            user_id = data.get('id')
            print_result(True, "User registration successful", {
                'user_id': user_id,
                'email': data.get('email'),
                'username': data.get('username')
            })
            return True
        elif response.status_code == 400 and "already registered" in response.text:
            print_result(True, "User already exists (expected for repeated tests)")
            return True
        else:
            print_result(False, f"Registration failed with status {response.status_code}", response.text)
            return False
    except Exception as e:
        print_result(False, f"Registration request failed: {str(e)}")
        return False

def test_admin_registration():
    """Test admin user registration and set admin privileges"""
    print_test_header("Admin Registration")
    global admin_id
    
    try:
        response = requests.post(f"{BASE_URL}/auth/register", json=TEST_ADMIN, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            admin_id = data.get('id')
            print_result(True, "Admin registration successful", {
                'admin_id': admin_id,
                'email': data.get('email'),
                'username': data.get('username')
            })
            return True
        elif response.status_code == 400 and "already registered" in response.text:
            print_result(True, "Admin already exists (expected for repeated tests)")
            # Try to get admin_id from login later
            return True
        else:
            print_result(False, f"Admin registration failed with status {response.status_code}", response.text)
            return False
    except Exception as e:
        print_result(False, f"Admin registration request failed: {str(e)}")
        return False

def test_user_login():
    """Test user login endpoint"""
    print_test_header("User Login")
    global user_token, user_id
    
    try:
        response = requests.post(f"{BASE_URL}/auth/login", json={
            "email": TEST_USER["email"],
            "password": TEST_USER["password"]
        }, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            user_token = data.get('access_token')
            user_data = data.get('user', {})
            user_id = user_data.get('id')
            
            print_result(True, "User login successful", {
                'token_type': data.get('token_type'),
                'user_id': user_id,
                'username': user_data.get('username')
            })
            return True
        else:
            print_result(False, f"Login failed with status {response.status_code}", response.text)
            return False
    except Exception as e:
        print_result(False, f"Login request failed: {str(e)}")
        return False

def test_admin_login():
    """Test admin login endpoint"""
    print_test_header("Admin Login")
    global admin_token, admin_id
    
    try:
        response = requests.post(f"{BASE_URL}/auth/login", json={
            "email": TEST_ADMIN["email"],
            "password": TEST_ADMIN["password"]
        }, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            admin_token = data.get('access_token')
            admin_data = data.get('user', {})
            admin_id = admin_data.get('id')
            
            print_result(True, "Admin login successful", {
                'token_type': data.get('token_type'),
                'admin_id': admin_id,
                'username': admin_data.get('username')
            })
            return True
        else:
            print_result(False, f"Admin login failed with status {response.status_code}", response.text)
            return False
    except Exception as e:
        print_result(False, f"Admin login request failed: {str(e)}")
        return False

def test_auth_me():
    """Test getting current user info"""
    print_test_header("Authentication - Get Current User")
    
    if not user_token:
        print_result(False, "No user token available")
        return False
    
    try:
        headers = {"Authorization": f"Bearer {user_token}"}
        response = requests.get(f"{BASE_URL}/auth/me", headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            print_result(True, "User info retrieved successfully", {
                'user_id': data.get('id'),
                'email': data.get('email'),
                'username': data.get('username'),
                'is_admin': data.get('is_admin')
            })
            return True
        else:
            print_result(False, f"Get user info failed with status {response.status_code}", response.text)
            return False
    except Exception as e:
        print_result(False, f"Get user info request failed: {str(e)}")
        return False

def test_chat_send_message():
    """Test sending a chat message to AI"""
    print_test_header("Chat - Send Message to AI")
    global session_id
    
    if not user_token:
        print_result(False, "No user token available")
        return False
    
    try:
        headers = {"Authorization": f"Bearer {user_token}"}
        chat_data = {
            "message": "Hello! Can you tell me about Kurdish culture and traditions?",
            "language": "en"
        }
        
        response = requests.post(f"{BASE_URL}/chat/send", json=chat_data, headers=headers, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            session_id = data.get('session_id')
            ai_response = data.get('ai_response')
            
            print_result(True, "Chat message sent successfully", {
                'session_id': session_id,
                'user_message': data.get('message'),
                'ai_response_length': len(ai_response) if ai_response else 0,
                'ai_response_preview': ai_response[:100] + "..." if ai_response and len(ai_response) > 100 else ai_response
            })
            return True
        elif response.status_code == 500:
            # Check if it's an API key issue
            if "API key not valid" in response.text or "Chat service error" in response.text:
                print_result(False, "Chat failed due to invalid Gemini API key", "The EMERGENT_LLM_KEY in backend/.env needs to be a valid Gemini API key")
                return False
            else:
                print_result(False, f"Chat send failed with status {response.status_code}", response.text)
                return False
        else:
            print_result(False, f"Chat send failed with status {response.status_code}", response.text)
            return False
    except Exception as e:
        print_result(False, f"Chat send request failed: {str(e)}")
        return False

def test_chat_follow_up():
    """Test sending a follow-up message in the same session"""
    print_test_header("Chat - Follow-up Message")
    
    if not user_token or not session_id:
        print_result(False, "No user token or session ID available")
        return False
    
    try:
        headers = {"Authorization": f"Bearer {user_token}"}
        chat_data = {
            "message": "Can you write a simple Python function to calculate factorial?",
            "session_id": session_id,
            "language": "en"
        }
        
        response = requests.post(f"{BASE_URL}/chat/send", json=chat_data, headers=headers, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            ai_response = data.get('ai_response')
            
            print_result(True, "Follow-up message sent successfully", {
                'session_id': data.get('session_id'),
                'user_message': data.get('message'),
                'ai_response_length': len(ai_response) if ai_response else 0,
                'contains_code': 'def ' in ai_response if ai_response else False
            })
            return True
        else:
            print_result(False, f"Follow-up chat failed with status {response.status_code}", response.text)
            return False
    except Exception as e:
        print_result(False, f"Follow-up chat request failed: {str(e)}")
        return False

def test_chat_sessions():
    """Test getting chat sessions"""
    print_test_header("Chat - Get Sessions")
    
    if not user_token:
        print_result(False, "No user token available")
        return False
    
    try:
        headers = {"Authorization": f"Bearer {user_token}"}
        response = requests.get(f"{BASE_URL}/chat/sessions", headers=headers, timeout=10)
        
        if response.status_code == 200:
            sessions = response.json()
            print_result(True, "Chat sessions retrieved successfully", {
                'session_count': len(sessions),
                'sessions': [{'id': s.get('id'), 'title': s.get('title')} for s in sessions[:3]]
            })
            return True
        else:
            print_result(False, f"Get sessions failed with status {response.status_code}", response.text)
            return False
    except Exception as e:
        print_result(False, f"Get sessions request failed: {str(e)}")
        return False

def test_chat_messages():
    """Test getting messages from a session"""
    print_test_header("Chat - Get Messages")
    
    if not user_token or not session_id:
        print_result(False, "No user token or session ID available")
        return False
    
    try:
        headers = {"Authorization": f"Bearer {user_token}"}
        response = requests.get(f"{BASE_URL}/chat/sessions/{session_id}/messages", headers=headers, timeout=10)
        
        if response.status_code == 200:
            messages = response.json()
            print_result(True, "Chat messages retrieved successfully", {
                'message_count': len(messages),
                'messages': [{'role': m.get('role'), 'content': m.get('content')[:50] + "..."} for m in messages[:3]]
            })
            return True
        else:
            print_result(False, f"Get messages failed with status {response.status_code}", response.text)
            return False
    except Exception as e:
        print_result(False, f"Get messages request failed: {str(e)}")
        return False

def test_admin_analytics():
    """Test admin analytics endpoint"""
    print_test_header("Admin - Analytics")
    
    if not admin_token:
        print_result(False, "No admin token available")
        return False
    
    try:
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/admin/analytics", headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            print_result(True, "Admin analytics retrieved successfully", {
                'user_count': data.get('user_count'),
                'session_count': data.get('session_count'),
                'message_count': data.get('message_count'),
                'recent_sessions_count': len(data.get('recent_sessions', [])),
                'recent_users_count': len(data.get('recent_users', []))
            })
            return True
        elif response.status_code == 403:
            print_result(False, "Admin access denied - user lacks admin privileges", "The registered admin user needs is_admin=true set in the database")
            return False
        else:
            print_result(False, f"Admin analytics failed with status {response.status_code}", response.text)
            return False
    except Exception as e:
        print_result(False, f"Admin analytics request failed: {str(e)}")
        return False

def test_admin_prompts():
    """Test admin prompt management"""
    print_test_header("Admin - Prompt Management")
    
    if not admin_token:
        print_result(False, "No admin token available")
        return False
    
    try:
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        # Create a prompt
        prompt_data = {
            "name": "Kurdish Language Helper",
            "content": "You are a helpful assistant specialized in Kurdish language and culture. Always be respectful and informative."
        }
        
        create_response = requests.post(f"{BASE_URL}/admin/prompts", json=prompt_data, headers=headers, timeout=10)
        
        if create_response.status_code == 200:
            created_prompt = create_response.json()
            prompt_id = created_prompt.get('id')
            
            # Get all prompts
            get_response = requests.get(f"{BASE_URL}/admin/prompts", headers=headers, timeout=10)
            
            if get_response.status_code == 200:
                prompts = get_response.json()
                print_result(True, "Admin prompt management working", {
                    'created_prompt_id': prompt_id,
                    'total_prompts': len(prompts),
                    'created_prompt_name': created_prompt.get('name')
                })
                return True
            else:
                print_result(False, f"Get prompts failed with status {get_response.status_code}")
                return False
        elif create_response.status_code == 403:
            print_result(False, "Admin access denied - user lacks admin privileges", "The registered admin user needs is_admin=true set in the database")
            return False
        else:
            print_result(False, f"Create prompt failed with status {create_response.status_code}", create_response.text)
            return False
    except Exception as e:
        print_result(False, f"Admin prompts request failed: {str(e)}")
        return False

def test_unauthorized_admin_access():
    """Test that regular user cannot access admin endpoints"""
    print_test_header("Security - Unauthorized Admin Access")
    
    if not user_token:
        print_result(False, "No user token available")
        return False
    
    try:
        headers = {"Authorization": f"Bearer {user_token}"}
        response = requests.get(f"{BASE_URL}/admin/analytics", headers=headers, timeout=10)
        
        if response.status_code == 403:
            print_result(True, "Admin access properly restricted for regular users")
            return True
        else:
            print_result(False, f"Security issue: Regular user got status {response.status_code} for admin endpoint")
            return False
    except Exception as e:
        print_result(False, f"Unauthorized admin access test failed: {str(e)}")
        return False

def run_all_tests():
    """Run all backend tests in sequence"""
    print(f"\n🚀 Starting KurdAI Backend API Tests")
    print(f"Backend URL: {BASE_URL}")
    print(f"Test started at: {datetime.now()}")
    
    test_results = []
    
    # Core functionality tests
    test_results.append(("Server Health", test_server_health()))
    test_results.append(("User Registration", test_user_registration()))
    test_results.append(("Admin Registration", test_admin_registration()))
    test_results.append(("User Login", test_user_login()))
    test_results.append(("Admin Login", test_admin_login()))
    test_results.append(("Auth Me", test_auth_me()))
    
    # Chat functionality tests
    test_results.append(("Chat Send Message", test_chat_send_message()))
    test_results.append(("Chat Follow-up", test_chat_follow_up()))
    test_results.append(("Chat Sessions", test_chat_sessions()))
    test_results.append(("Chat Messages", test_chat_messages()))
    
    # Admin functionality tests
    test_results.append(("Admin Analytics", test_admin_analytics()))
    test_results.append(("Admin Prompts", test_admin_prompts()))
    
    # Security tests
    test_results.append(("Unauthorized Admin Access", test_unauthorized_admin_access()))
    
    # Print summary
    print(f"\n{'='*60}")
    print("TEST SUMMARY")
    print(f"{'='*60}")
    
    passed = 0
    failed = 0
    
    for test_name, result in test_results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")
        if result:
            passed += 1
        else:
            failed += 1
    
    print(f"\nTotal Tests: {len(test_results)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Success Rate: {(passed/len(test_results)*100):.1f}%")
    
    if failed == 0:
        print("\n🎉 All tests passed! KurdAI backend is working correctly.")
    else:
        print(f"\n⚠️  {failed} test(s) failed. Please check the details above.")
    
    return failed == 0

if __name__ == "__main__":
    success = run_all_tests()
    exit(0 if success else 1)