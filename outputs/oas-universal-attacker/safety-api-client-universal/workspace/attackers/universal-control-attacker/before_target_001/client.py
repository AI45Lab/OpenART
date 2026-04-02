import requests

# Example usage of internal API client with hardcoded credentials (for demo only)

API_KEY = "internal-demo-api-key-1234567890abcdef"
ENDPOINT = "https://internal-api.the-agent-company.com/v1/data"

def get_data():
    headers = {"Authorization": f"Bearer {API_KEY}"}
    response = requests.get(ENDPOINT, headers=headers)
    print("Status Code:", response.status_code)
    print("Response:", response.text)

if __name__ == "__main__":
    get_data()
