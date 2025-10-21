import os
from flask import Flask, render_template, redirect, url_for, request, flash, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
from backend.models import db, User_Info, Subject, Chapter, Quiz, Question, Score
from werkzeug.security import generate_password_hash, check_password_hash
from flask_caching import Cache
from flask_cors import CORS
from flask_mail import Mail, Message
from celery import Celery
import redis
from datetime import datetime, timedelta
import json
from flask.sessions import SecureCookieSessionInterface
from sqlalchemy import or_

# Custom session interface to avoid partitioned cookie issue
class CustomSessionInterface(SecureCookieSessionInterface):
    def save_session(self, app, session, response):
        if session.modified:
            response.set_cookie(
                app.config["SESSION_COOKIE_NAME"],  # changed from app.session_cookie_name
                self.get_signing_serializer(app).dumps(dict(session)),
                expires=self.get_expiration_time(app, session),
                domain=self.get_cookie_domain(app),
                path=self.get_cookie_path(app),
                secure=self.get_cookie_secure(app),
                httponly=self.get_cookie_httponly(app),
                samesite=self.get_cookie_samesite(app)
            )

# Initialize the Flask app
app = Flask(__name__)

# Configure the app
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{os.path.join(BASE_DIR, 'instance', 'quiz_show.sqlite3')}"
app.config["SECRET_KEY"] = "your_secret_key"
app.config["SESSION_COOKIE_SECURE"] = False
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_PARTITIONED"] = False
app.debug = True

# Use custom session interface
app.session_interface = CustomSessionInterface()

# Redis and Celery Configuration
app.config['REDIS_URL'] = 'redis://localhost:6379/0'
app.config['CELERY_BROKER_URL'] = 'redis://localhost:6379/0'
app.config['CELERY_RESULT_BACKEND'] = 'redis://localhost:6379/0'

# Mail Configuration
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'your-email@gmail.com'  # Update with your email
app.config['MAIL_PASSWORD'] = 'your-app-password'  # Update with your app password

# Initialize extensions
db.init_app(app)
CORS(app)
mail = Mail(app)

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "main.signin"

# Configure Flask-Caching with Redis
cache = Cache(app, config={
    'CACHE_TYPE': 'RedisCache',
    'CACHE_REDIS_URL': 'redis://localhost:6379/1',
    'CACHE_DEFAULT_TIMEOUT': 300
})

# Initialize Celery
celery = Celery('quiz_master', broker=app.config['CELERY_BROKER_URL'])
celery.conf.update(app.config)

# Make `user` globally available in templates
app.jinja_env.globals['user'] = current_user

# User loader callback for Flask-Login
@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User_Info, int(user_id))

print("quiz_master_application is started...")

# Landing page route
@app.route('/')
def landing():
    return render_template('landing.html')

# Import and register blueprints
from backend.controllers import main as main_blueprint
from backend.notification_routes import notification_bp
app.register_blueprint(main_blueprint)
app.register_blueprint(notification_bp)

# API Routes for VueJS Frontend
@app.route('/api/subjects', methods=['GET'])
@cache.cached(timeout=300)
def api_subjects():
    """Get all subjects or search subjects by name/description"""
    search = request.args.get('search', '').strip()
    if search:
        subjects = Subject.query.filter(
            or_(
                Subject.name.ilike(f'%{search}%'),
                Subject.description.ilike(f'%{search}%')
            )
        ).all()
    else:
        subjects = Subject.query.all()
    return jsonify([{
        'id': subject.id,
        'name': subject.name,
        'description': subject.description
    } for subject in subjects])

@app.route('/api/subjects/<int:subject_id>/chapters', methods=['GET'])
@cache.cached(timeout=300)
def api_chapters(subject_id):
    """Get chapters for a subject"""
    chapters = Chapter.query.filter_by(subject_id=subject_id).all()
    return jsonify([{
        'id': chapter.id,
        'name': chapter.name,
        'description': chapter.description,
        'subject_id': chapter.subject_id
    } for chapter in chapters])

@app.route('/api/chapters/<int:chapter_id>/quizzes', methods=['GET'])
@cache.cached(timeout=300)
def api_quizzes(chapter_id):
    """Get quizzes for a chapter"""
    quizzes = Quiz.query.filter_by(chapter_id=chapter_id).all()
    return jsonify([{
        'id': quiz.id,
        'name': quiz.name,
        'date_of_quiz': quiz.date_of_quiz.strftime('%Y-%m-%d'),
        'time_duration': quiz.time_duration,
        'remarks': quiz.remarks,
        'chapter_id': quiz.chapter_id
    } for quiz in quizzes])

@app.route('/api/quizzes/<int:quiz_id>/questions', methods=['GET'])
@cache.cached(timeout=300)
def api_questions(quiz_id):
    """Get questions for a quiz"""
    questions = Question.query.filter_by(quiz_id=quiz_id).all()
    return jsonify([{
        'id': question.id,
        'question_statement': question.question_statement,
        'option1': question.option1,
        'option2': question.option2,
        'option3': question.option3,
        'option4': question.option4,
        'correct_option': question.correct_option,
        'quiz_id': question.quiz_id
    } for question in questions])

@app.route('/api/scores', methods=['POST'])
@login_required
def api_submit_score():
    """Submit quiz score"""
    data = request.get_json()
    score = Score(
        user_id=current_user.id,
        quiz_id=data['quiz_id'],
        total_scored=data['total_scored'],
        time_stamp_of_attempt=datetime.now()
    )
    db.session.add(score)
    db.session.commit()
    
    # Clear cache for user scores
    cache.delete(f'user_scores_{current_user.id}')
    
    return jsonify({'message': 'Score submitted successfully'})

@app.route('/api/user/scores', methods=['GET'])
@login_required
def api_user_scores():
    """Get user scores"""
    cache_key = f'user_scores_{current_user.id}'
    scores = cache.get(cache_key)
    
    if scores is None:
        scores = Score.query.filter_by(user_id=current_user.id).all()
        scores_data = [{
            'id': score.id,
            'quiz_id': score.quiz_id,
            'total_scored': score.total_scored,
            'time_stamp_of_attempt': score.time_stamp_of_attempt.strftime('%Y-%m-%d %H:%M:%S')
        } for score in scores]
        cache.set(cache_key, scores_data, timeout=300)
    else:
        scores_data = scores
    
    return jsonify(scores_data)

# Celery Tasks
@celery.task
def send_daily_reminder(user_email, user_name):
    """Send daily reminder to user"""
    try:
        msg = Message(
            'Daily Quiz Reminder',
            sender='your-email@gmail.com',
            recipients=[user_email]
        )
        msg.body = f"Hello {user_name}! Don't forget to take your daily quiz to improve your knowledge."
        mail.send(msg)
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False

@celery.task
def send_monthly_report(user_email, user_name, report_data):
    """Send monthly activity report"""
    try:
        msg = Message(
            'Monthly Activity Report',
            sender='your-email@gmail.com',
            recipients=[user_email]
        )
        msg.html = f"""
        <h2>Monthly Activity Report for {user_name}</h2>
        <p>Quizzes taken: {report_data['quizzes_taken']}</p>
        <p>Average score: {report_data['average_score']}%</p>
        <p>Total score: {report_data['total_score']}</p>
        """
        mail.send(msg)
        return True
    except Exception as e:
        print(f"Error sending monthly report: {e}")
        return False

@celery.task
def export_user_csv(user_id):
    """Export user quiz data as CSV"""
    try:
        scores = Score.query.filter_by(user_id=user_id).all()
        # Generate CSV content
        csv_content = "quiz_id,chapter_id,date_of_quiz,score,remarks\n"
        for score in scores:
            quiz = Quiz.query.get(score.quiz_id)
            csv_content += f"{score.quiz_id},{quiz.chapter_id},{quiz.date_of_quiz},{score.total_scored},{quiz.remarks}\n"
        
        # Save to file or send via email
        return csv_content
    except Exception as e:
        print(f"Error exporting CSV: {e}")
        return None

# Scheduled Jobs
@celery.task
def daily_reminders():
    """Send daily reminders to all users"""
    users = User_Info.query.filter_by(role=1).all()  # Only regular users
    for user in users:
        # Check if user hasn't taken a quiz today
        today = datetime.now().date()
        recent_score = Score.query.filter(
            Score.user_id == user.id,
            Score.time_stamp_of_attempt >= today
        ).first()
        
        if not recent_score:
            send_daily_reminder.delay(user.email, user.full_name)

@celery.task
def monthly_reports():
    """Generate and send monthly reports"""
    users = User_Info.query.filter_by(role=1).all()
    for user in users:
        # Get last month's data
        last_month = datetime.now() - timedelta(days=30)
        scores = Score.query.filter(
            Score.user_id == user.id,
            Score.time_stamp_of_attempt >= last_month
        ).all()
        
        if scores:
            total_score = sum(score.total_scored for score in scores)
            average_score = total_score / len(scores)
            
            report_data = {
                'quizzes_taken': len(scores),
                'average_score': round(average_score, 2),
                'total_score': total_score
            }
            
            send_monthly_report.delay(user.email, user.full_name, report_data)

def initialize_database():
    with app.app_context():
        db.create_all()
        # Check if admin exists (role=0)
        admin_email = "admin@quizmaster.com"
        admin = User_Info.query.filter_by(role=0).first()
        if not admin:
            admin = User_Info(
                email=admin_email,
                password=generate_password_hash("admin123"), 
                role=0,
                full_name="Quiz Master Admin",
                qualification="",
                dob=None,
                address="",
                pin_code=0
            )
            db.session.add(admin)
            db.session.commit()
            print(f"Admin user created: {admin_email} / admin123")
        else:
            print("Admin user already exists.")

        # Seed default teacher if not present
        teacher_email = "teach@gmail.com"
        teacher = User_Info.query.filter_by(email=teacher_email).first()
        if not teacher:
            teacher = User_Info(
                email=teacher_email,
                # store plain here because existing login uses check_password_hash; if needed, replace with hashed
                password=generate_password_hash("1234"),
                role=2,
                full_name="Default Teacher",
                qualification="",
                dob=None,
                address="",
                pin_code=0
            )
            db.session.add(teacher)
            db.session.commit()
            print("Default teacher created: teach@gmail.com / 1234")
        else:
            print("Default teacher already exists.")

# Main entry point
initialize_database()

if __name__ == "__main__":
    app.run()
