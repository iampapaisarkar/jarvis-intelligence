from server.api.health import router as health_router
from server.api.intent import router as intent_router
from server.api.mac import router as mac_router
from server.api.routes import router as chat_router
from server.api.speech import router as speech_router
from server.api.tts import router as tts_router

__all__ = ["health_router", "chat_router", "speech_router", "tts_router", "intent_router", "mac_router"]
