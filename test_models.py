from google import genai
from dotenv import load_dotenv
import os

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

print("Available models:")
print("-" * 50)

try:
    models = client.models.list()
    for model in models:
        print(f"✅ {model.name}")
        if hasattr(model, 'supported_generation_methods'):
            print(f"   Methods: {model.supported_generation_methods}")
        print()
except Exception as e:
    print(f"Error listing models: {e}")