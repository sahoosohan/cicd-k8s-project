from flask import Flask
raise RuntimeError("simulated startup crash")
app = Flask(__name__)

@app.route("/")
def home():
    return "Hello from CI/CD pipeline - v1"

@app.route("/health")
def health():
    return {"status": "ok"}, 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)