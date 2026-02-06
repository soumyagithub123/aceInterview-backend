
import sys
import os

# Add the project root to sys.path
sys.path.append(os.getcwd())

try:
    print("Checking app.client.openai_client...")
    import app.client.openai_client
    print("✅ app.client.openai_client imported")

    print("Checking app.client.gemini_client...")
    import app.client.gemini_client
    print("✅ app.client.gemini_client imported")

    print("Checking app.client.openai_tts...")
    import app.client.openai_tts
    print("✅ app.client.openai_tts imported")

    print("Checking app.services.qa...")
    import app.services.qa
    print("✅ app.services.qa imported")

    print("Checking app.services.complete_settings...")
    import app.services.complete_settings
    print("✅ app.services.complete_settings imported")

    print("Checking app.services.transcript...")
    import app.services.transcript
    print("✅ app.services.transcript imported")

    print("Checking app.ai_router...")
    import app.ai_router
    print("✅ app.ai_router imported")

    print("Checking app.ws.ws_live_interview...")
    import app.ws.ws_live_interview
    print("✅ app.ws.ws_live_interview imported")

    print("Checking app.routes.voice...")
    import app.routes.voice
    print("✅ app.routes.voice imported")

    print("Checking app.mock_interview...")
    import app.mock_interview
    print("✅ app.mock_interview imported")

    print("Checking app.session_manager...")
    import app.session_manager
    print("✅ app.session_manager imported")

    print("ALL IMPORTS SUCCESSFUL")

except ImportError as e:
    print(f"❌ ImportError: {e}")
    sys.exit(1)
except Exception as e:
    print(f"❌ Error: {e}")
    sys.exit(1)
