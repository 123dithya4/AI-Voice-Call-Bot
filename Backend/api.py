import os
import requests
from dotenv import load_dotenv

load_dotenv()

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID")
VAPI_API_KEY = os.getenv("VAPI_API_KEY")




# Vapi API endpoint
VAPI_BASE_URL = "https://api.vapi.ai"

def test_elevenlabs_connection():
    """Test if ElevenLabs API key is valid with a simple text-to-speech call"""
    print("Testing ElevenLabs connection...")
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"
    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json"
    }
    
    payload = {
        "text": "Test",
        "model_id": "eleven_turbo_v2"
    }
    
    if not ELEVENLABS_API_KEY or not ELEVENLABS_VOICE_ID:
        raise RuntimeError("Set ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID in .env")
    response = requests.post(url, headers=headers, json=payload, timeout=30)
    
    if response.status_code == 200:
        print("✓ ElevenLabs API key is valid!")
        print(f"✓ Voice ID '{ELEVENLABS_VOICE_ID}' is working!")
        return True
    elif response.status_code == 401:
        print(f"✗ ElevenLabs Error: {response.status_code}")
        print(f"Response: {response.text}")
        print("\n⚠ SOLUTION: Your API key needs proper permissions!")
        print("Go to: https://elevenlabs.io/app/settings/api-keys")
        print("Create a NEW API key or regenerate with full permissions")
        return False
    else:
        print(f"✗ ElevenLabs Error: {response.status_code}")
        print(f"Response: {response.text}")
        return False

def create_vapi_assistant_with_elevenlabs():
    """Create a Vapi assistant using ElevenLabs voice"""
    print("\nCreating Vapi assistant with ElevenLabs voice...")
    
    url = f"{VAPI_BASE_URL}/assistant"
    
    headers = {
        "Authorization": f"Bearer {VAPI_API_KEY}",
        "Content-Type": "application/json"
    }
    
    # Assistant configuration with ElevenLabs
    payload = {
        "name": "ElevenLabs Assistant",
        "model": {
            "provider": "openai",
            "model": "gpt-3.5-turbo",
            "messages": [
                {
                    "role": "system",
                    "content": "You are a helpful assistant."
                }
            ]
        },
        "voice": {
            "provider": "11labs",
            "voiceId": ELEVENLABS_VOICE_ID,
            "model": "eleven_flash_v2_5",
            "stability": 0.5,
            "similarityBoost": 0.75,
            "style": 0.0,
            "useSpeakerBoost": True
        },
        "firstMessage": "Hello! How can I help you today?"
    }
    
    if not VAPI_API_KEY:
        raise RuntimeError("Set VAPI_API_KEY in .env")
    response = requests.post(url, headers=headers, json=payload, timeout=30)
    
    if response.status_code in [200, 201]:
        print("✓ Assistant created successfully!")
        assistant_data = response.json()
        print(f"Assistant ID: {assistant_data.get('id')}")
        return assistant_data
    else:
        print(f"✗ Failed to create assistant: {response.status_code}")
        print(f"Response: {response.text}")
        return None

def add_elevenlabs_to_vapi_providers():
    """Add ElevenLabs API key to Vapi provider credentials"""
    print("\nAdding ElevenLabs to Vapi provider credentials...")
    
    url = f"{VAPI_BASE_URL}/credential"
    
    headers = {
        "Authorization": f"Bearer {VAPI_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "provider": "11labs",
        "apiKey": ELEVENLABS_API_KEY
    }
    
    if not VAPI_API_KEY or not ELEVENLABS_API_KEY:
        raise RuntimeError("Set VAPI_API_KEY and ELEVENLABS_API_KEY in .env")
    response = requests.post(url, headers=headers, json=payload, timeout=30)
    
    if response.status_code in [200, 201]:
        print("✓ ElevenLabs credentials added to Vapi!")
        return True
    else:
        print(f"✗ Failed to add credentials: {response.status_code}")
        print(f"Response: {response.text}")
        return False

def main():
    print("=" * 60)
    print("Vapi + ElevenLabs Integration Setup")
    print("=" * 60)
    
    # Step 1: Test ElevenLabs connection
    if not test_elevenlabs_connection():
        print("\n⚠ Please check your ElevenLabs API key and Voice ID")
        return
    
    # Step 2: Add ElevenLabs to Vapi providers
    print("\n" + "=" * 60)
    if add_elevenlabs_to_vapi_providers():
        print("✓ Provider credentials configured!")
    
    # Step 3: Create assistant with ElevenLabs voice
    print("\n" + "=" * 60)
    assistant = create_vapi_assistant_with_elevenlabs()
    
    if assistant:
        print("\n" + "=" * 60)
        print("SUCCESS! Your assistant is ready to use!")
        print("=" * 60)
        print(f"Assistant ID: {assistant.get('id')}")
        print(f"Voice Provider: ElevenLabs (11labs)")
        print(f"Voice ID: {ELEVENLABS_VOICE_ID}")
    else:
        print("\n⚠ Please make sure you've added your Vapi API key in the script")

if __name__ == "__main__":
    main()