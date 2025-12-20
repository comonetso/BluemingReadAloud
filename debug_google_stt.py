from google.cloud import speech_v2
import inspect

print("--- Members of google.cloud.speech_v2 ---")
for name, obj in inspect.getmembers(speech_v2):
    if not name.startswith('_'):
        print(name)
