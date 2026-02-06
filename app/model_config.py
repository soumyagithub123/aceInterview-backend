    # app/model_config.py
"""
Model-specific optimization settings
Different models need different timeout/temperature configs
"""

MODEL_CONFIGS = {
    # OpenAI Models
    "gpt-4o-mini": {
        "timeout": 15,  # Fast model - lower timeout
        "temperature": 0.2,
        "max_tokens": 800,
        "streaming_chunk_size": 10,  # Smaller chunks for faster delivery
    },
    "gpt-4o": {
        "timeout": 20,  # Slower model - higher timeout
        "temperature": 0.2,
        "max_tokens": 800,
        "streaming_chunk_size": 20,
    },
    "gpt-4-turbo": {
        "timeout": 20,
        "temperature": 0.2,
        "max_tokens": 800,
        "streaming_chunk_size": 20,
    },
    
    # Gemini Models
    "gemini-2.0-flash": {
        "timeout": 15,
        "temperature": 0.2,
        "max_tokens": 800,
        "streaming_chunk_size": 15,
    },
    "gemini-2.0-flash-lite": {
        "timeout": 12,
        "temperature": 0.2,
        "max_tokens": 800,
        "streaming_chunk_size": 10,
    },
    "gemini-1.5-pro": {
        "timeout": 25,  # Slower model
        "temperature": 0.2,
        "max_tokens": 800,
        "streaming_chunk_size": 20,
    },
}

# Default fallback config
DEFAULT_CONFIG = {
    "timeout": 20,
    "temperature": 0.2,
    "max_tokens": 800,
    "streaming_chunk_size": 15,
}


def get_model_config(model: str) -> dict:
    """Get optimized config for specific model"""
    model = model.lower().strip()
    return MODEL_CONFIGS.get(model, DEFAULT_CONFIG)