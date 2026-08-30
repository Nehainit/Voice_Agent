
def speech_to_text(audio_text):
      return audio_text

def decide_response(user_text):
    text = user_text.lower()

    if "price" in text or "cost" in text:
        return "Our pricing depends on your call volume. Would you like to talk to sales?"

    if "book" in text or "demo" in text:
        return "Sure, I can help book a demo. What day works for you?"

    return "Can you tell me a little more about what you need?"

def text_to_speech(response_text):
      return f"AUDIO: {response_text}"

def run_voice_turn(audio_text):
      user_text = speech_to_text(audio_text)
      response_text = decide_response(user_text)
      audio_response = text_to_speech(response_text)

      return {
          "user_text": user_text,
          "response_text": response_text,
          "audio_response": audio_response,
      }

