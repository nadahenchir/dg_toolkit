from flask import Flask
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# Routes will be registered here as we build them

@app.route('/health')
def health():
    return {'status': 'ok', 'message': 'DG Toolkit API is running'}

if __name__ == '__main__':
    app.run(debug=True, port=5000)