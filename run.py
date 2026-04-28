from flask import Flask, render_template, abort
from flask_cors import CORS
from flask_swagger_ui import get_swaggerui_blueprint
from app.routes.organizations import organizations_bp
from app.routes.consultants import consultants_bp
from app.routes.assessments import assessments_bp
from app.routes.answers import answers_bp
from app.routes.scores import scores_bp
from app.routes.recommendations import recommendations_bp
from app.routes.generate import generate_bp

app = Flask(__name__)
CORS(app)

ALLOWED_PAGES = {'create_assessment', 'dashboard', 'index', 'questionnaire', 'results', 'rating', 'recommendations'}

@app.route('/')
@app.route('/<page>')
def serve_page(page='create_assessment'):
    if page not in ALLOWED_PAGES:
        abort(404)
    return render_template(f'{page}.html')

# Routes
app.register_blueprint(organizations_bp, url_prefix='/api')
app.register_blueprint(consultants_bp, url_prefix='/api')
app.register_blueprint(assessments_bp, url_prefix='/api')
app.register_blueprint(answers_bp, url_prefix='/api')
app.register_blueprint(scores_bp, url_prefix='/api')
app.register_blueprint(recommendations_bp, url_prefix='/api')
app.register_blueprint(generate_bp, url_prefix='/api')

# Swagger UI
SWAGGER_URL = '/docs'
API_URL = '/static/swagger.json'
swagger_ui_blueprint = get_swaggerui_blueprint(
    SWAGGER_URL,
    API_URL,
    config={'app_name': 'DG Toolkit API'}
)
app.register_blueprint(swagger_ui_blueprint, url_prefix=SWAGGER_URL)

@app.route('/health')
def health():
    return {'status': 'ok', 'message': 'DG Toolkit API is running'}

if __name__ == '__main__':
    app.run(debug=True, port=5000)