from dotenv import load_dotenv
load_dotenv()

import google.generativeai as genai
import os

# Configure API key
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

print("Checking available Gemini models...\n")
print("=" * 60)

try:
    models = genai.list_models()
    
    print("Models that support generateContent:")
    print("-" * 60)
    
    for model in models:
        if 'generateContent' in model.supported_generation_methods:
            print(f"✓ {model.name}")
            print(f"  Display name: {model.display_name}")
            print(f"  Description: {model.description}")
            print()
    
    print("=" * 60)
    print("\nUse one of these model names in your code!")
    
except Exception as e:
    print(f"Error: {e}")
    print("\nMake sure:")
    print("1. Your GOOGLE_API_KEY is set in .env file")
    print("2. You've enabled the Generative Language API in Google Cloud Console")