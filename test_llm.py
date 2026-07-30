from app.llm_provider import GeminiProvider

def test():
    try:
        provider = GeminiProvider()
        print("Initialized.")
        response = provider.generate("You are a helpful assistant.", "What is 2+2?", max_tokens=10)
        print("Response:", response.text)
    except Exception as e:
        print("Error:", type(e))
        print("Message:", e)
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test()
