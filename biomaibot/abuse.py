from openai import AsyncOpenAI
import asyncio
import re
from bot_config import GPT_API_KEY, ABUSE_THRESHOLD

class AbuseDetector:
    def __init__(self):
        self.client = AsyncOpenAI(api_key=GPT_API_KEY) if GPT_API_KEY else None
        self.is_ready = True if GPT_API_KEY else False
        self.local_patterns = [
            r'\b(?:fuck|shit|bitch|bastard|asshole)\b',
            r'\b(?:rape|kill|murder|terror)\b',
            r'\b(?:slur|chutiya|madarchod|bhosdike|lund|randi)\b',
            r'\b(?:harass|abuse|bully)\b',
        ]
        self.local_regex = re.compile('|'.join(self.local_patterns), re.IGNORECASE)
    
    async def detect_abuse(self, text: str) -> dict:
        if self.local_regex.search(text or ""):
            return {"is_abusive": True, "confidence": 0.9, "reason": "local_match"}
        if not self.is_ready or not self.client:
            return {"is_abusive": False, "confidence": 0.0, "reason": "fallback"}
        
        try:
            response = await self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {
                        "role": "system",
                        "content": """You are an abuse detector for Telegram groups. Analyze the message and respond ONLY with JSON:
                        {"is_abusive": true/false, "confidence": 0.0-1.0, "reason": "brief explanation"}
                        
                        Detect profanity, hate speech, threats, harassment, spam, or inappropriate content.
                        Be strict but fair. Ignore normal conversation."""
                    },
                    {
                        "role": "user",
                        "content": f"Analyze this message: {text}"
                    }
                ],
                temperature=0.1,
                max_tokens=150
            )
            
            result = response.choices[0].message.content.strip()
            import json
            return json.loads(result)
            
        except Exception as e:
            msg = str(e).lower()
            if ("invalid api key" in msg) or ("401" in msg) or ("unauthorized" in msg):
                self.is_ready = False
                self.client = None
            if self.local_regex.search(text or ""):
                return {"is_abusive": True, "confidence": 0.8, "reason": "local_fallback"}
            return {"is_abusive": False, "confidence": 0.0, "reason": "fallback_error"}
