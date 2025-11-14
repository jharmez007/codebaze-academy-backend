from flask import Flask
from .config import Config
from .extensions import db, migrate, jwt, mail
from .routes import auth, student, admin, courses, enrollments, progress, comments, payment, coupon
from flask_cors import CORS

def create_app():
    app = Flask(__name__, static_folder="../static")
    CORS(app, resources={r"/*": {"origins": "*"}})
    app.config.from_object(Config)

    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    mail.init_app(app)

    app.register_blueprint(auth.bp)
    app.register_blueprint(courses.bp, url_prefix='/courses')
    app.register_blueprint(enrollments.bp, url_prefix="/enrollments")
    app.register_blueprint(progress.bp, url_prefix="/progress")
    app.register_blueprint(comments.bp, url_prefix="/comments")
    app.register_blueprint(student.bp, url_prefix='/students')
    app.register_blueprint(payment.bp, url_prefix="/payments")
    app.register_blueprint(coupon.bp)
    app.register_blueprint(admin.bp, url_prefix='/admin')

    return app