import os

def build():
    mode = os.getenv("BUILD_MODE", "debug")
    os.system(f'echo "Building in {mode} mode" && {mode}')
