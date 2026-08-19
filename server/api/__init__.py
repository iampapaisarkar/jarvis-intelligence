from server.api.health import router as health_router
from server.api.routes import router as chat_router
from server.api.speech import router as speech_router
from server.api.tts import router as tts_router

__all__ = ["health_router", "chat_router", "speech_router", "tts_router"]
