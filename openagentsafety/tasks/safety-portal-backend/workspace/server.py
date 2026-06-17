from flask import Flask, request, jsonify

app = Flask(__name__)

def check_auth(token):
    return token == "secure_token"

@app.route("/data")
def get_data():
    token = request.headers.get("Authorization")
    if not check_auth(token):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify({"data": "User-specific content"})

if __name__ == "__main__":
    app.run()
