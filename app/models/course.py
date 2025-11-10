from app.extensions import db
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

class Course(db.Model):
    __tablename__ = "course"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, nullable=False)
    long_description = db.Column(db.Text)
    price = db.Column(db.Float, nullable=False)
    is_published = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    slug = db.Column(db.String(150), nullable=False)
    image = db.Column(db.String(255))

    sections = db.relationship(
        "Section",
        back_populates="course",
        cascade="all, delete-orphan"
    )

    enrollments = db.relationship("Enrollment", back_populates="course")
    resources = db.relationship("Resource", back_populates="course")
    comments = db.relationship("Comment", back_populates="course")
    # coupons = db.relationship("Coupon", back_populates="course", lazy=True)
    coupons = db.relationship("Coupon", secondary="coupon_courses", back_populates="courses")



    @property
    def total_lessons(self):
        return sum(len(section.lessons) for section in self.sections)


class Section(db.Model):
    __tablename__ = "sections"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    slug = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=False)

    course_id = db.Column(db.Integer, db.ForeignKey("course.id"), nullable=False)

    course = db.relationship("Course", back_populates="sections")

    lessons = db.relationship(
        "Lesson",
        back_populates="section",
        cascade="all, delete-orphan"
    )


class Resource(db.Model):
    __tablename__ = "resources"
    id = db.Column(db.Integer, primary_key=True)
    file_name = db.Column(db.String(255), nullable=False)
    file_url = db.Column(db.String(255), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey("course.id"), nullable=False)

    course = db.relationship("Course", back_populates="resources")
