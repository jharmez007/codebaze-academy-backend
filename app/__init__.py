from flask import Flask
from .config import Config
from .extensions import db, migrate, jwt, mail
from .routes import auth, student, admin, courses, enrollments, progress, comments, payment, coupon, lessons
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix


def create_app():
    app = Flask(__name__, static_folder="../static")
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)
    CORS(app, resources={r"/*": {"origins": "*"}})
    app.config.from_object(Config)
    
    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    
    # CRITICAL FIX: Ensure mail config is loaded before init
    app.config['MAIL_SERVER'] = app.config.get('MAIL_SERVER', 'smtp.zoho.com')
    app.config['MAIL_PORT'] = int(app.config.get('MAIL_PORT', 587))
    app.config['MAIL_USE_TLS'] = app.config.get('MAIL_USE_TLS', True)
    app.config['MAIL_USE_SSL'] = app.config.get('MAIL_USE_SSL', False)
    app.config['MAIL_USERNAME'] = app.config.get('MAIL_USERNAME')
    app.config['MAIL_PASSWORD'] = app.config.get('MAIL_PASSWORD')
    app.config['MAIL_DEFAULT_SENDER'] = app.config.get('MAIL_DEFAULT_SENDER')
    
    mail.init_app(app)
    
    # Verify mail is initialized
    with app.app_context():
        print(f"DEBUG: Mail state after init: {mail.state}")
        print(f"DEBUG: Mail server: {app.config.get('MAIL_SERVER')}")

    # Register blueprints
    app.register_blueprint(auth.bp)
    app.register_blueprint(courses.bp, url_prefix='/courses')
    app.register_blueprint(enrollments.bp, url_prefix="/enrollments")
    app.register_blueprint(progress.bp, url_prefix="/progress")
    app.register_blueprint(comments.bp, url_prefix="/comments")
    app.register_blueprint(student.bp, url_prefix='/students')
    app.register_blueprint(payment.bp, url_prefix="/payments")
    app.register_blueprint(coupon.bp)
    app.register_blueprint(admin.bp, url_prefix='/admin')
    app.register_blueprint(lessons.bp, url_prefix='/lessons')

    return app