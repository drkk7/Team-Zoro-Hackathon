from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()

# User model
class User_Info(db.Model, UserMixin):
    __tablename__ = "user_info"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String, unique=True, nullable=False)
    password = db.Column(db.String, nullable=False)
    role = db.Column(db.Integer, default=1)  # 0=admin, 1=student, 2=teacher
    full_name = db.Column(db.String, nullable=False)
    qualification = db.Column(db.String, nullable=True)  # Added qualification
    dob = db.Column(db.Date, nullable=True)  # Added date of birth
    address = db.Column(db.String, nullable=False)
    pin_code = db.Column(db.Integer, nullable=False)
    branch_id = db.Column(db.Integer, db.ForeignKey("branch.id"), nullable=True)  # Added branch selection
    scores = db.relationship("Score", cascade="all,delete", backref="user", lazy=True)
    # Courses taught by the user (if teacher)
    courses = db.relationship("Course", cascade="all,delete", backref="teacher", lazy=True)
    # Branch relationship
    branch = db.relationship("Branch", backref="students")

# Engineering Branch model
class Branch(db.Model):
    __tablename__ = "branch"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, nullable=False)  # e.g., "Computer Science Engineering"
    short_name = db.Column(db.String, nullable=False)  # e.g., "CSE"
    description = db.Column(db.Text, nullable=True)
    icon = db.Column(db.String, nullable=True)  # Icon class for UI
    color = db.Column(db.String, nullable=True)  # Color code for UI
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'short_name': self.short_name,
            'description': self.description,
            'icon': self.icon,
            'color': self.color,
            'created_at': self.created_at.isoformat()
        }

# Subject model
class Subject(db.Model):
    __tablename__ = "subject"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, nullable=False)
    description = db.Column(db.Text, nullable=True)  # Use Text for longer descriptions
    branch_id = db.Column(db.Integer, db.ForeignKey("branch.id"), nullable=True)  # Added branch relationship
    is_core = db.Column(db.Boolean, default=True)  # True for core subjects, False for electives
    chapters = db.relationship("Chapter", cascade="all,delete", backref="subject", lazy=True)
    # Branch relationship
    branch = db.relationship("Branch", backref="subjects")

# Chapter model
class Chapter(db.Model):
    __tablename__ = "chapter"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, nullable=False)
    description = db.Column(db.Text, nullable=True)  # Use Text for longer descriptions
    subject_id = db.Column(db.Integer, db.ForeignKey("subject.id"), nullable=False)
    quizzes = db.relationship("Quiz", cascade="all,delete", backref="chapter", lazy=True)

# Quiz model
class Quiz(db.Model):
    __tablename__ = "quiz"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, nullable=False)
    date_of_quiz = db.Column(db.Date, nullable=False)  # Use Date type
    time_duration = db.Column(db.String, nullable=False)
    remarks = db.Column(db.Text, nullable=True)  # Added remarks field
    chapter_id = db.Column(db.Integer, db.ForeignKey("chapter.id"), nullable=False)
    questions = db.relationship("Question", cascade="all,delete", backref="quiz", lazy=True)
    scores = db.relationship("Score", cascade="all,delete", backref="quiz", lazy=True)

# Question model
class Question(db.Model):
    __tablename__ = "question"
    id = db.Column(db.Integer, primary_key=True)
    question_statement = db.Column(db.Text, nullable=False)  # Use Text for longer questions
    option1 = db.Column(db.String, nullable=False)
    option2 = db.Column(db.String, nullable=False)
    option3 = db.Column(db.String, nullable=False)
    option4 = db.Column(db.String, nullable=False)
    correct_option = db.Column(db.String, nullable=False)
    quiz_id = db.Column(db.Integer, db.ForeignKey("quiz.id"), nullable=False)

# Score model
class Score(db.Model):
    __tablename__ = "score"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user_info.id"), nullable=False)
    quiz_id = db.Column(db.Integer, db.ForeignKey("quiz.id"), nullable=False)
    total_scored = db.Column(db.Integer, nullable=False)
    time_stamp_of_attempt = db.Column(db.DateTime, nullable=False)  # Use DateTime type
    # Optionally add more fields: correct_answers, ranking, etc.

# Course model
class Course(db.Model):
    __tablename__ = "course"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String, nullable=False)
    description = db.Column(db.Text, nullable=True)
    duration = db.Column(db.String, nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey("user_info.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())

# Teacher model (admin-managed)
class Teacher(db.Model):
    __tablename__ = "teacher"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user_info.id"), nullable=False)
    name = db.Column(db.String, nullable=False)
    email = db.Column(db.String, nullable=False, unique=True)
    password_hash = db.Column(db.String, nullable=False)
    course_name = db.Column(db.String, nullable=True)
    course_description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())

# Mapping: which subjects a teacher can manage
class TeacherSubject(db.Model):
    __tablename__ = "teacher_subject"
    id = db.Column(db.Integer, primary_key=True)
    teacher_user_id = db.Column(db.Integer, db.ForeignKey("user_info.id"), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey("subject.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())

# User enrollment in subjects/courses
class UserEnrollment(db.Model):
    __tablename__ = "user_enrollment"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user_info.id"), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey("subject.id"), nullable=False)
    enrolled_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    
    # Relationships
    user = db.relationship("User_Info", backref="enrollments")
    subject = db.relationship("Subject", backref="enrollments")

# Discussion forum for courses
class Discussion(db.Model):
    __tablename__ = "discussions"
    id = db.Column(db.Integer, primary_key=True)
    subject_id = db.Column(db.Integer, db.ForeignKey("subject.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user_info.id"), nullable=False)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now(), onupdate=db.func.now())
    
    # Relationships
    subject = db.relationship("Subject", backref="discussions")
    user = db.relationship("User_Info", backref="discussion_messages")
    
    def to_dict(self):
        return {
            'id': self.id,
            'subject_id': self.subject_id,
            'user_id': self.user_id,
            'user_name': self.user.full_name or self.user.email,
            'user_role': self.user.role,
            'message': self.message,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }

# Chapter materials for sharing PDFs, documents, and other resources
class ChapterMaterial(db.Model):
    __tablename__ = "chapter_materials"
    id = db.Column(db.Integer, primary_key=True)
    chapter_id = db.Column(db.Integer, db.ForeignKey("chapter.id"), nullable=False)
    title = db.Column(db.String, nullable=False)
    description = db.Column(db.Text, nullable=True)
    file_path = db.Column(db.String, nullable=True)  # For uploaded files
    file_type = db.Column(db.String, nullable=True)  # pdf, doc, ppt, etc.
    file_size = db.Column(db.Integer, nullable=True)  # File size in bytes
    external_url = db.Column(db.String, nullable=True)  # For external links
    material_type = db.Column(db.String, nullable=False)  # file, link, text
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now(), onupdate=db.func.now())
    
    # Relationships
    chapter = db.relationship("Chapter", backref="materials")
    
# Assignment model for tasks with deadlines
class Assignment(db.Model):
    __tablename__ = "assignments"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String, nullable=False)
    description = db.Column(db.Text, nullable=True)
    subject_id = db.Column(db.Integer, db.ForeignKey("subject.id"), nullable=False)
    chapter_id = db.Column(db.Integer, db.ForeignKey("chapter.id"), nullable=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey("user_info.id"), nullable=False)
    deadline = db.Column(db.DateTime, nullable=False)
    max_points = db.Column(db.Integer, default=100)
    assignment_type = db.Column(db.String, nullable=False)  # quiz, homework, project, exam
    instructions = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now(), onupdate=db.func.now())
    
    # Relationships
    subject = db.relationship("Subject", backref="assignments")
    chapter = db.relationship("Chapter", backref="assignments")
    teacher = db.relationship("User_Info", backref="created_assignments")
    submissions = db.relationship("AssignmentSubmission", cascade="all,delete", back_populates="assignment", lazy=True)
    
    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'subject_id': self.subject_id,
            'chapter_id': self.chapter_id,
            'teacher_id': self.teacher_id,
            'deadline': self.deadline.isoformat(),
            'max_points': self.max_points,
            'assignment_type': self.assignment_type,
            'instructions': self.instructions,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }

# Assignment submission model
class AssignmentSubmission(db.Model):
    __tablename__ = "assignment_submissions"
    id = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(db.Integer, db.ForeignKey("assignments.id"), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey("user_info.id"), nullable=False)
    submission_content = db.Column(db.Text, nullable=True)
    file_path = db.Column(db.String, nullable=True)
    submitted_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
    grade = db.Column(db.Integer, nullable=True)
    feedback = db.Column(db.Text, nullable=True)
    is_late = db.Column(db.Boolean, default=False, nullable=False)
    
    # Relationships
    assignment = db.relationship("Assignment", back_populates="submissions")
    student = db.relationship("User_Info", backref="assignment_submissions")
    
    def to_dict(self):
        return {
            'id': self.id,
            'assignment_id': self.assignment_id,
            'student_id': self.student_id,
            'submission_content': self.submission_content,
            'file_path': self.file_path,
            'submitted_at': self.submitted_at.isoformat(),
            'grade': self.grade,
            'feedback': self.feedback,
            'is_late': self.is_late
        }

# Notification model for deadline alerts and system messages
class Notification(db.Model):
    __tablename__ = "notifications"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user_info.id"), nullable=False)
    title = db.Column(db.String, nullable=False)
    message = db.Column(db.Text, nullable=False)
    notification_type = db.Column(db.String, nullable=False)  # deadline, assignment, quiz, general
    related_id = db.Column(db.Integer, nullable=True)  # ID of related assignment, quiz, etc.
    related_type = db.Column(db.String, nullable=True)  # assignment, quiz, etc.
    is_read = db.Column(db.Boolean, default=False, nullable=False)
    priority = db.Column(db.String, default='normal', nullable=False)  # low, normal, high, urgent
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
    expires_at = db.Column(db.DateTime, nullable=True)
    
    # Relationships
    user = db.relationship("User_Info", backref="notifications")
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'title': self.title,
            'message': self.message,
            'notification_type': self.notification_type,
            'related_id': self.related_id,
            'related_type': self.related_type,
            'is_read': self.is_read,
            'priority': self.priority,
            'created_at': self.created_at.isoformat(),
            'expires_at': self.expires_at.isoformat() if self.expires_at else None
        }