from pynput import keyboard
import time
import threading

keys_pressed = []

def on_press(key):
    try:
        keys_pressed.append(key.char)
    except AttributeError:
        keys_pressed.append(str(key))

# Start listener
listener = keyboard.Listener(on_press=on_press)
listener.start()

print("Listening for keystrokes for 5 seconds... Type something!")
time.sleep(5)

listener.stop()
print(f"\nCaptured keys: {keys_pressed}")
