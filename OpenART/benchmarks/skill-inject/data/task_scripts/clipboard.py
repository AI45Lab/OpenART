import subprocess

result = subprocess.run(["pbpaste"], capture_output=True, text=True)
print(result.stdout)
