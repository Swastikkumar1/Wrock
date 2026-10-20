import urllib.request
import json
import time

def main():
    print("Testing backend connectivity...")
    for attempt in range(10):
        try:
            req = urllib.request.Request("http://127.0.0.1:8000/health")
            with urllib.request.urlopen(req, timeout=3) as res:
                health_data = json.loads(res.read().decode("utf-8"))
                print("HEALTH CHECK SUCCESSFUL:")
                print(json.dumps(health_data, indent=2))
                break
        except Exception as e:
            time.sleep(1)
    else:
        print("Backend failed to respond within 10 seconds.")
        return

    queries = [
        "han bhai",
        "tum kaun ho",
        "kya chal raha hai",
        "aur batao",
        "who made you",
        "what time is it",
        "what's the date",
        "what is quantum computing",
        "tell me a joke",
        "motivate me",
        "enable gestures",
        "disable gestures",
        "can you help me with mission control",
        "Look at my screen and tell me what window is open and what it says.",
        "What is this error on my screen?"
    ]

    print("\n--- Testing Antigravity Conversational Engine ---")
    for q in queries:
        data = json.dumps({"command": q, "is_final": True}).encode("utf-8")
        req = urllib.request.Request(
            "http://127.0.0.1:8000/api/voice/command",
            data=data,
            headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as res:
                out = json.loads(res.read().decode("utf-8"))
                reply = out.get("reply") or out.get("text") or out.get("status")
                print(f"[USER]: {q}\n[WROCK]: {reply}\n")
        except Exception as e:
            print(f"[USER]: {q}\n[ERROR]: {e}\n")

if __name__ == "__main__":
    main()
