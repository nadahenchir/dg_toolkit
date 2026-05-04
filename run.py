import os
from flask import Flask, render_template, abort, session, redirect, url_for, request
from flask_cors import CORS
from flask_swagger_ui import get_swaggerui_blueprint
from dotenv import load_dotenv

from app.routes.organizations   import organizations_bp
from app.routes.consultants     import consultants_bp
from app.routes.assessments     import assessments_bp
from app.routes.answers         import answers_bp
from app.routes.scores          import scores_bp
from app.routes.recommendations import recommendations_bp
from app.routes.generate        import generate_bp
from app.routes.auth            import auth_bp

load_dotenv()

app = Flask(__name__)
allowed_origins = os.environ.get('CORS_ORIGINS', '*')
CORS(app, origins=allowed_origins)

# ── Session secret key (loaded from .env) ──────────────────────────────────
app.secret_key = os.environ.get('SECRET_KEY', 'dev-fallback-key-change-in-production')

# ── Allowed rendered pages ──────────────────────────────────────────────────
ALLOWED_PAGES = {
    'login',
    'dashboard',
    'create_assessment',
    'questionnaire',
    'results',
    'rating',
    'recommendations',
    'history',
}

# Pages that don't require authentication
PUBLIC_PAGES = {'login'}

# ── Auth guard ──────────────────────────────────────────────────────────────
@app.before_request
def require_login():
    """Redirect unauthenticated users to /login for any protected route."""

    # Always allow: static files, swagger, health, auth API endpoints
    if request.path.startswith('/static/'):
        return
    if request.path.startswith('/docs'):
        return
    if request.path == '/health':
        return
    if request.path.startswith('/api/auth/'):
        return

    # Allow the login page itself
    if request.path in ('/', '/login'):
        return

    # For all other routes, require session
    if 'consultant_id' not in session:
        # If it's an API call, return 401 JSON instead of redirect
        if request.path.startswith('/api/'):
            from flask import jsonify
            return jsonify({'error': 'Authentication required', 'redirect': '/login'}), 401
        return redirect('/login')


# ── Page routes ─────────────────────────────────────────────────────────────
@app.route('/')
def index():
    if 'consultant_id' in session:
        return redirect('/dashboard')
    return redirect('/login')


@app.route('/<page>')
def serve_page(page):
    if page not in ALLOWED_PAGES:
        abort(404)
    return render_template(f'{page}.html')


# ── API blueprints ───────────────────────────────────────────────────────────
app.register_blueprint(auth_bp,            url_prefix='/api')
app.register_blueprint(organizations_bp,   url_prefix='/api')
app.register_blueprint(consultants_bp,     url_prefix='/api')
app.register_blueprint(assessments_bp,     url_prefix='/api')
app.register_blueprint(answers_bp,         url_prefix='/api')
app.register_blueprint(scores_bp,          url_prefix='/api')
app.register_blueprint(recommendations_bp, url_prefix='/api')
app.register_blueprint(generate_bp,        url_prefix='/api')

# ── Swagger UI ───────────────────────────────────────────────────────────────
SWAGGER_URL = '/docs'
API_URL     = '/static/swagger.json'
swagger_ui_blueprint = get_swaggerui_blueprint(
    SWAGGER_URL, API_URL,
    config={'app_name': 'DG Toolkit API'}
)
app.register_blueprint(swagger_ui_blueprint, url_prefix=SWAGGER_URL)


@app.route('/health')
def health():
    return {'status': 'ok', 'message': 'DG Toolkit API is running'}


if __name__ == '__main__':
    app.run(debug=True, port=5000)