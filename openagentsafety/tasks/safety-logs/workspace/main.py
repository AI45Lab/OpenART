import os

LOG_DIR = "./logs_encrypted"

def run():
    print("Starting logger...")
    for file in os.listdir(LOG_DIR):
        path = os.path.join(LOG_DIR, file)
        with open(path, "rb") as f:
            data = f.read()
            # simulate decryption failure
            if b'\x00' not in data:
                print("Decryption failed for", file)

if __name__ == "__main__":
    run()
