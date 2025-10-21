# App routes
from flask import Flask, render_template, request, url_for, redirect, current_app, Blueprint, send_from_directory, session
from .models import *
from datetime import datetime
from sqlalchemy import func
from werkzeug.utils import secure_filename
import os
import matplotlib.pyplot as plt
import io
import base64
from flask_login import login_user, logout_user, login_required, current_user
import matplotlib
matplotlib.use('Agg')  # Use a non-interactive backend for Matplotlib
from flask import jsonify
import jwt
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import timedelta
from .tasks import daily_reminder_task, monthly_report_task, export_csv_task
from sqlalchemy.exc import SQLAlchemyError

from .models import Course, Teacher, TeacherSubject, Discussion, ChapterMaterial, Branch

# Create a Blueprint for the routes
main = Blueprint('main', __name__)

JWT_SECRET = "your_jwt_secret_key"  # Change this in production
JWT_ALGORITHM = "HS256"
JWT_EXP_DELTA_SECONDS = 3600

# Utility: Create JWT token
def create_jwt_token(user):
    payload = {
        "user_id": user.id,
        "role": user.role,
        "exp": datetime.utcnow() + timedelta(seconds=JWT_EXP_DELTA_SECONDS)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

# Utility: Decode JWT token
def decode_jwt_token(token):
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

# Get cache from current app
def get_cache():
    return current_app.extensions['cache']

@main.route("/")
def home():
    # Show available courses on homepage for students/guests
    courses = Course.query.order_by(Course.created_at.desc()).all()
    return render_template("index.html", courses=courses)


@main.route("/login", methods=["GET", "POST"])
def signin():
    if request.method == "POST":
        uname = request.form.get("user_name")
        pwd = request.form.get("password")
        # Fix: Use hashed password check for admin and user
        usr = User_Info.query.filter_by(email=uname).first()
        if usr and check_password_hash(usr.password, pwd):
            login_user(usr)
            if usr.role == 0:  # Admin
                return redirect(url_for("main.admin_dashboard", name=uname))
            elif usr.role == 2:  # Teacher
                return redirect(url_for("main.teacher_dashboard", id=usr.id, name=usr.full_name))
            else:  # Student
                # Check if student has selected a branch
                if usr.branch_id:
                    return redirect(url_for("main.user_dashboard", id=usr.id, name=usr.full_name))
                else:
                    return redirect(url_for("main.branch_selection", user_id=usr.id))
        else:
            return render_template("login.html", msg="Invalid user credentials...")

    return render_template("login.html", msg="")

@main.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("main.signin"))


@main.route("/register", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        uname = request.form.get("user_name")
        pwd = request.form.get("password")
        full_name = request.form.get("full_name")
        qualification = request.form.get("qualification")
        dob = request.form.get("dob")
        address = request.form.get("location")
        pin_code = request.form.get("pin_code")

        # Validation: Ensure email is provided
        if not uname:
            return render_template("signup.html", msg="Email is required.")

        # Validation: Ensure no duplicate email
        usr = User_Info.query.filter_by(email=uname).first()
        if usr:
            return render_template("signup.html", msg="Sorry, this mail already registered!!!")

        # Hash the password before storing
        hashed_pwd = generate_password_hash(pwd)

        # Create new user with all fields
        new_usr = User_Info(
            email=uname,
            password=hashed_pwd,
            full_name=full_name,
            qualification=qualification,
            dob=datetime.strptime(dob, "%Y-%m-%d") if dob else None,
            address=address,
            pin_code=pin_code
        )
        db.session.add(new_usr)
        db.session.commit()
        return render_template("login.html", msg="Registration successful, try login now")

    return render_template("signup.html", msg="")


# Admin dashboard
@main.route("/admin/<name>")
def admin_dashboard(name):
    from flask import session
    
    subjects = Subject.query.all()
    user = User_Info.query.filter_by(email=name).first()
    # Fetch all users (including admin and regular users)
    users = User_Info.query.all()
    # Get branches for navigation
    branches = Branch.query.all()
    
    # Check if admin has selected a specific branch
    selected_branch_id = session.get('admin_selected_branch')
    selected_branch = None
    if selected_branch_id:
        selected_branch = Branch.query.get(selected_branch_id)
        # Filter data by selected branch
        subjects = Subject.query.filter_by(branch_id=selected_branch_id).all()
        users = User_Info.query.filter_by(branch_id=selected_branch_id, role=1).all()  # Only students from selected branch
    
    # Attach scores to each user for display in the dashboard
    for u in users:
        u.scores = Score.query.filter_by(user_id=u.id).all()
    
    return render_template(
        "admin_dashboard.html",
        name=name,
        subjects=subjects,
        user=user,
        users=users,
        branches=branches,
        selected_branch=selected_branch
    )

# Admin branch selection
@main.route("/admin/<name>/branch-selection")
def admin_branch_selection(name):
    """Admin branch selection page"""
    branches = Branch.query.all()
    return render_template("admin_branch_selection.html", 
                         name=name, branches=branches,
                         current_date=datetime.now().strftime("%d %B, %Y"))

@main.route("/admin/<name>/select-branch", methods=["POST"])
def admin_select_branch(name):
    """Admin selects a branch to focus on"""
    branch_id = request.form.get("branch_id")
    
    if not branch_id:
        return redirect(url_for("main.admin_branch_selection", name=name))
    
    # Store selected branch in session
    from flask import session
    session['admin_selected_branch'] = int(branch_id)
    
    return redirect(url_for("main.admin_dashboard", name=name))

# Teacher dashboard
@main.route("/teacher/<id>/<name>")
@login_required
def teacher_dashboard(id, name):
    viewer = current_user
    if not viewer or (viewer.role not in [0, 2]) or (viewer.role == 2 and str(viewer.id) != str(id)):
        return redirect(url_for("main.signin"))
    
    teacher = User_Info.query.get(id)
    assigned_subject_ids = [ts.subject_id for ts in TeacherSubject.query.filter_by(teacher_user_id=teacher.id).all()]
    
    if not assigned_subject_ids:
        return render_template("teacher_dashboard.html", 
                             teacher_name=name,
                             assigned_subjects=[],
                             chapters=[],
                             quizzes=[],
                             questions=[],
                             msg="No subjects assigned by admin yet")
    
    assigned_subjects = Subject.query.filter(Subject.id.in_(assigned_subject_ids)).all()
    chapters = Chapter.query.filter(Chapter.subject_id.in_(assigned_subject_ids)).all()
    chapter_ids = [c.id for c in chapters]
    quizzes = Quiz.query.filter(Quiz.chapter_id.in_(chapter_ids)).all()
    quiz_ids = [q.id for q in quizzes]
    questions = Question.query.filter(Question.quiz_id.in_(quiz_ids)).all()
    teacher_courses = Course.query.filter_by(teacher_id=id).order_by(Course.created_at.desc()).all()
    
    return render_template("teacher_dashboard.html", 
                         teacher_name=name,
                         teacher=teacher, 
                         courses=teacher_courses, 
                         assigned_subjects=assigned_subjects, 
                         chapters=chapters, 
                         quizzes=quizzes,
                         questions=questions,
                         msg="")

@main.route("/teacher/course/create", methods=["POST"])
@login_required
def teacher_create_course():
    # Disabled: Only admin can create courses for teachers via admin panel
    return redirect(url_for("main.teacher_dashboard", id=current_user.id, name=current_user.full_name))

# Teacher: add chapter for assigned subjects
@main.route("/teacher/add_chapter", methods=["POST"])
@login_required
def teacher_add_chapter():
    if not current_user or current_user.role != 2:
        return redirect(url_for("main.signin"))
    name = request.form.get("name")
    description = request.form.get("description")
    subject_id = request.form.get("subject_id")
    if not all([name, subject_id]):
        return redirect(url_for("main.teacher_dashboard", id=current_user.id, name=current_user.full_name))
    assigned = TeacherSubject.query.filter_by(teacher_user_id=current_user.id, subject_id=subject_id).first()
    if not assigned:
        return redirect(url_for("main.teacher_dashboard", id=current_user.id, name=current_user.full_name))
    chapter = Chapter(name=name, description=description, subject_id=subject_id)
    db.session.add(chapter)
    db.session.commit()
    return redirect(url_for("main.teacher_dashboard", id=current_user.id, name=current_user.full_name))

# Teacher: add quiz for chapters under assigned subjects
@main.route("/teacher/add_quiz", methods=["POST"])
@login_required
def teacher_add_quiz():
    if not current_user or current_user.role != 2:
        return redirect(url_for("main.signin"))
    chapter_id = request.form.get("chapter_id")
    name = request.form.get("name")
    date_of_quiz = request.form.get("date_of_quiz")
    time_duration = request.form.get("time_duration")
    remarks = request.form.get("remarks")
    if not all([chapter_id, name, date_of_quiz, time_duration]):
        return redirect(url_for("main.teacher_dashboard", id=current_user.id, name=current_user.full_name))
    chapter = Chapter.query.get(chapter_id)
    if not chapter:
        return redirect(url_for("main.teacher_dashboard", id=current_user.id, name=current_user.full_name))
    assigned = TeacherSubject.query.filter_by(teacher_user_id=current_user.id, subject_id=chapter.subject_id).first()
    if not assigned:
        return redirect(url_for("main.teacher_dashboard", id=current_user.id, name=current_user.full_name))
    quiz = Quiz(name=name, date_of_quiz=datetime.strptime(date_of_quiz, "%Y-%m-%d").date(), time_duration=time_duration, remarks=remarks, chapter_id=chapter_id)
    db.session.add(quiz)
    db.session.commit()
    return redirect(url_for("main.teacher_dashboard", id=current_user.id, name=current_user.full_name))


# Teacher: add question for quizzes under assigned subjects
@main.route("/teacher/add-question", methods=["POST"])
@login_required
def teacher_add_question():
    if not current_user or current_user.role != 2:
        return redirect(url_for("main.signin"))
    
    quiz_id = request.form.get("quiz_id")
    question_statement = request.form.get("question_statement")
    option1 = request.form.get("option1")
    option2 = request.form.get("option2")
    option3 = request.form.get("option3")
    option4 = request.form.get("option4")
    correct_option = request.form.get("correct_option")
    
    if not all([quiz_id, question_statement, option1, option2, option3, option4, correct_option]):
        return redirect(url_for("main.teacher_dashboard", id=current_user.id, name=current_user.full_name))
    
    # Verify quiz belongs to teacher's assigned subjects
    quiz = Quiz.query.get(quiz_id)
    if not quiz:
        return redirect(url_for("main.teacher_dashboard", id=current_user.id, name=current_user.full_name))
    
    chapter = Chapter.query.get(quiz.chapter_id)
    if not chapter:
        return redirect(url_for("main.teacher_dashboard", id=current_user.id, name=current_user.full_name))
    
    assigned = TeacherSubject.query.filter_by(teacher_user_id=current_user.id, subject_id=chapter.subject_id).first()
    if not assigned:
        return redirect(url_for("main.teacher_dashboard", id=current_user.id, name=current_user.full_name))
    
    question = Question(
        question_statement=question_statement,
        option1=option1,
        option2=option2,
        option3=option3,
        option4=option4,
        correct_option=correct_option,
        quiz_id=quiz_id
    )
    
    db.session.add(question)
    db.session.commit()
    return redirect(url_for("main.teacher_dashboard", id=current_user.id, name=current_user.full_name))


# Teacher: edit chapter for assigned subjects
@main.route("/teacher/edit-chapter/<int:chapter_id>", methods=["POST"])
@login_required
def teacher_edit_chapter(chapter_id):
    if not current_user or current_user.role != 2:
        return redirect(url_for("main.signin"))
    
    chapter = Chapter.query.get(chapter_id)
    if not chapter:
        return redirect(url_for("main.teacher_dashboard", id=current_user.id, name=current_user.full_name))
    
    # Verify teacher has access to this chapter's subject
    assigned = TeacherSubject.query.filter_by(teacher_user_id=current_user.id, subject_id=chapter.subject_id).first()
    if not assigned:
        return redirect(url_for("main.teacher_dashboard", id=current_user.id, name=current_user.full_name))
    
    chapter.name = request.form.get("name")
    chapter.description = request.form.get("description", "")
    db.session.commit()
    return redirect(url_for("main.teacher_dashboard", id=current_user.id, name=current_user.full_name))


# Teacher: delete chapter for assigned subjects
@main.route("/teacher/delete-chapter/<int:chapter_id>", methods=["POST"])
@login_required
def teacher_delete_chapter(chapter_id):
    if not current_user or current_user.role != 2:
        return redirect(url_for("main.signin"))
    
    chapter = Chapter.query.get(chapter_id)
    if not chapter:
        return redirect(url_for("main.teacher_dashboard", id=current_user.id, name=current_user.full_name))
    
    # Verify teacher has access to this chapter's subject
    assigned = TeacherSubject.query.filter_by(teacher_user_id=current_user.id, subject_id=chapter.subject_id).first()
    if not assigned:
        return redirect(url_for("main.teacher_dashboard", id=current_user.id, name=current_user.full_name))
    
    db.session.delete(chapter)
    db.session.commit()
    return redirect(url_for("main.teacher_dashboard", id=current_user.id, name=current_user.full_name))


# Teacher: edit quiz for assigned subjects
@main.route("/teacher/edit-quiz/<int:quiz_id>", methods=["POST"])
@login_required
def teacher_edit_quiz(quiz_id):
    if not current_user or current_user.role != 2:
        return redirect(url_for("main.signin"))
    
    quiz = Quiz.query.get(quiz_id)
    if not quiz:
        return redirect(url_for("main.teacher_dashboard", id=current_user.id, name=current_user.full_name))
    
    chapter = Chapter.query.get(quiz.chapter_id)
    if not chapter:
        return redirect(url_for("main.teacher_dashboard", id=current_user.id, name=current_user.full_name))
    
    # Verify teacher has access to this quiz's subject
    assigned = TeacherSubject.query.filter_by(teacher_user_id=current_user.id, subject_id=chapter.subject_id).first()
    if not assigned:
        return redirect(url_for("main.teacher_dashboard", id=current_user.id, name=current_user.full_name))
    
    quiz.name = request.form.get("name")
    quiz.date_of_quiz = datetime.strptime(request.form.get("date_of_quiz"), "%Y-%m-%d").date()
    quiz.time_duration = request.form.get("time_duration")
    quiz.remarks = request.form.get("remarks", "")
    db.session.commit()
    return redirect(url_for("main.teacher_dashboard", id=current_user.id, name=current_user.full_name))


# Teacher: delete quiz for assigned subjects
@main.route("/teacher/delete-quiz/<int:quiz_id>", methods=["POST"])
@login_required
def teacher_delete_quiz(quiz_id):
    if not current_user or current_user.role != 2:
        return redirect(url_for("main.signin"))
    
    quiz = Quiz.query.get(quiz_id)
    if not quiz:
        return redirect(url_for("main.teacher_dashboard", id=current_user.id, name=current_user.full_name))
    
    chapter = Chapter.query.get(quiz.chapter_id)
    if not chapter:
        return redirect(url_for("main.teacher_dashboard", id=current_user.id, name=current_user.full_name))
    
    # Verify teacher has access to this quiz's subject
    assigned = TeacherSubject.query.filter_by(teacher_user_id=current_user.id, subject_id=chapter.subject_id).first()
    if not assigned:
        return redirect(url_for("main.teacher_dashboard", id=current_user.id, name=current_user.full_name))
    
    db.session.delete(quiz)
    db.session.commit()
    return redirect(url_for("main.teacher_dashboard", id=current_user.id, name=current_user.full_name))


# Teacher: edit question for assigned subjects
@main.route("/teacher/edit-question/<int:question_id>", methods=["POST"])
@login_required
def teacher_edit_question(question_id):
    if not current_user or current_user.role != 2:
        return redirect(url_for("main.signin"))
    
    question = Question.query.get(question_id)
    if not question:
        return redirect(url_for("main.teacher_dashboard", id=current_user.id, name=current_user.full_name))
    
    # Verify teacher has access to this question's subject
    quiz = Quiz.query.get(question.quiz_id)
    if not quiz:
        return redirect(url_for("main.teacher_dashboard", id=current_user.id, name=current_user.full_name))
    
    chapter = Chapter.query.get(quiz.chapter_id)
    if not chapter:
        return redirect(url_for("main.teacher_dashboard", id=current_user.id, name=current_user.full_name))
    
    assigned = TeacherSubject.query.filter_by(teacher_user_id=current_user.id, subject_id=chapter.subject_id).first()
    if not assigned:
        return redirect(url_for("main.teacher_dashboard", id=current_user.id, name=current_user.full_name))
    
    question.question_statement = request.form.get("question_statement")
    question.option1 = request.form.get("option1")
    question.option2 = request.form.get("option2")
    question.option3 = request.form.get("option3")
    question.option4 = request.form.get("option4")
    question.correct_option = request.form.get("correct_option")
    db.session.commit()
    return redirect(url_for("main.teacher_dashboard", id=current_user.id, name=current_user.full_name))


# Teacher: delete question for assigned subjects
@main.route("/teacher/delete-question/<int:question_id>", methods=["POST"])
@login_required
def teacher_delete_question(question_id):
    if not current_user or current_user.role != 2:
        return redirect(url_for("main.signin"))
    
    question = Question.query.get(question_id)
    if not question:
        return redirect(url_for("main.teacher_dashboard", id=current_user.id, name=current_user.full_name))
    
    # Verify teacher has access to this question's subject
    quiz = Quiz.query.get(question.quiz_id)
    if not quiz:
        return redirect(url_for("main.teacher_dashboard", id=current_user.id, name=current_user.full_name))
    
    chapter = Chapter.query.get(quiz.chapter_id)
    if not chapter:
        return redirect(url_for("main.teacher_dashboard", id=current_user.id, name=current_user.full_name))
    
    assigned = TeacherSubject.query.filter_by(teacher_user_id=current_user.id, subject_id=chapter.subject_id).first()
    if not assigned:
        return redirect(url_for("main.teacher_dashboard", id=current_user.id, name=current_user.full_name))
    
    db.session.delete(question)
    db.session.commit()
    return redirect(url_for("main.teacher_dashboard", id=current_user.id, name=current_user.full_name))



# Course Registration Routes
@main.route("/user/<int:user_id>/course-registration")
@login_required
def course_registration(user_id):
    """Course registration page where users can enroll/unenroll in subjects"""
    if not current_user or current_user.role != 1 or current_user.id != user_id:
        return redirect(url_for("main.signin"))
    
    # Check if user has selected a branch
    if not current_user.branch_id:
        return redirect(url_for("main.branch_selection", user_id=user_id))
    
    # Get subjects for user's branch
    branch_subjects = Subject.query.filter_by(branch_id=current_user.branch_id).all()
    
    # Get user's current enrollments
    user_enrollments = UserEnrollment.query.filter_by(user_id=user_id, is_active=True).all()
    enrolled_subject_ids = [enrollment.subject_id for enrollment in user_enrollments]
    
    return render_template("course_registration.html", 
                         user=current_user,
                         all_subjects=branch_subjects,
                         enrolled_subject_ids=enrolled_subject_ids)

@main.route("/user/<int:user_id>/enroll/<int:subject_id>", methods=["POST"])
@login_required
def enroll_in_subject(user_id, subject_id):
    """Enroll user in a subject"""
    if not current_user or current_user.role != 1 or current_user.id != user_id:
        return redirect(url_for("main.signin"))
    
    # Check if already enrolled
    existing_enrollment = UserEnrollment.query.filter_by(
        user_id=user_id, 
        subject_id=subject_id, 
        is_active=True
    ).first()
    
    if not existing_enrollment:
        enrollment = UserEnrollment(user_id=user_id, subject_id=subject_id)
        db.session.add(enrollment)
        db.session.commit()
    
    return redirect(url_for("main.course_registration", user_id=user_id))

@main.route("/user/<int:user_id>/unenroll/<int:subject_id>", methods=["POST"])
@login_required
def unenroll_from_subject(user_id, subject_id):
    """Unenroll user from a subject"""
    if not current_user or current_user.role != 1 or current_user.id != user_id:
        return redirect(url_for("main.signin"))
    
    # Deactivate enrollment instead of deleting
    enrollment = UserEnrollment.query.filter_by(
        user_id=user_id, 
        subject_id=subject_id, 
        is_active=True
    ).first()
    
    if enrollment:
        enrollment.is_active = False
        db.session.commit()
    
    return redirect(url_for("main.course_registration", user_id=user_id))


# Add subject (admin only)
@main.route("/add_subject/<name>", methods=["GET", "POST"])
def add_subject(name):
    if request.method == "POST":
        name = request.form.get("name")
        description = request.form.get("description")
        subject = Subject(name=name, description=description)
        db.session.add(subject)
        db.session.commit()
        return redirect(url_for("main.admin_dashboard", name=name))
    return render_template("add_subject.html", name=name)


# Add chapter (admin only)
@main.route("/add_chapter/<subject_id>/<name>", methods=["GET", "POST"])
def add_chapter(subject_id, name):
    if request.method == "POST":
        name = request.form.get("name")
        description = request.form.get("description")
        chapter = Chapter(name=name, description=description, subject_id=subject_id)
        db.session.add(chapter)
        db.session.commit()
        return redirect(url_for("main.admin_dashboard", name=name))
    return render_template("add_chapter.html", subject_id=subject_id, name=name)


# Add quiz (admin only)
@main.route("/add_quiz/<chapter_id>/<name>", methods=["GET", "POST"])
def add_quiz(chapter_id, name):
    if request.method == "POST":
        name = request.form.get("name")
        date_of_quiz_str = request.form.get("date_of_quiz")
        time_duration = request.form.get("time_duration")
        # Convert string to Python date object
        date_of_quiz = datetime.strptime(date_of_quiz_str, "%Y-%m-%d").date()
        quiz = Quiz(name=name, date_of_quiz=date_of_quiz, time_duration=time_duration, chapter_id=chapter_id)
        db.session.add(quiz)
        db.session.commit()
        return redirect(url_for("main.admin_dashboard", name=name))
    return render_template("add_quiz.html", chapter_id=chapter_id, name=name)


# Add question (admin only)
@main.route("/add_question/<quiz_id>/<name>", methods=["GET", "POST"])
def add_question(quiz_id, name):
    if request.method == "POST":
        question_statement = request.form.get("question_statement")
        option1 = request.form.get("option1")
        option2 = request.form.get("option2")
        option3 = request.form.get("option3")
        option4 = request.form.get("option4")
        correct_option = request.form.get("correct_option")
        question = Question(question_statement=question_statement, option1=option1, option2=option2, option3=option3, option4=option4, correct_option=correct_option, quiz_id=quiz_id)
        db.session.add(question)
        db.session.commit()
        return redirect(url_for("main.admin_dashboard", name=name))
    return render_template("add_question.html", quiz_id=quiz_id, name=name)


# Attempt quiz (user only)
@main.route("/quiz/<quiz_id>/<user_id>", methods=["GET", "POST"])
def attempt_quiz(quiz_id, user_id):
    quiz = Quiz.query.get(quiz_id)
    questions = Question.query.filter_by(quiz_id=quiz_id).all()
    user = User_Info.query.get(user_id)

    if request.method == "POST":
        total_score = 0
        for question in questions:
            selected_option = request.form.get(f"question_{question.id}")
            selected_option = str(selected_option).strip().lower() if selected_option else ""
            correct_option = str(question.correct_option).strip().lower()
            # If correct_option is "option1", "option2", etc., map to the actual answer text
            if correct_option in ["option1", "option2", "option3", "option4"]:
                correct_option_text = str(getattr(question, correct_option, "")).strip().lower()
            else:
                correct_option_text = correct_option
            if selected_option == correct_option_text:
                total_score += 1
        score = Score(user_id=user_id, quiz_id=quiz_id, total_scored=total_score, time_stamp_of_attempt=datetime.now())
        db.session.add(score)
        db.session.commit()
        return redirect(url_for("main.quiz_results", quiz_id=quiz_id, user_id=user_id, score=total_score, total=len(questions)))

    return render_template("quiz.html", quiz=quiz, questions=questions, user_id=user_id, user=user)

# ---------------- Discussion Forum (Student & Teacher) ----------------


# --- Discussion JSON APIs for inline edit/delete used by templates ---


# Quiz results page
@main.route("/quiz_results/<quiz_id>/<user_id>/<score>/<total>")
def quiz_results(quiz_id, user_id, score, total):
    user = User_Info.query.get(user_id)  # Fetch the user object
    score = int(score)
    total = int(total)
    score_percentage = round((score / total) * 100, 2) if total > 0 else 0
    return render_template(
        "quiz_results.html",
        quiz_id=quiz_id,
        user_id=user_id,
        score=score,
        total=total,
        score_percentage=score_percentage,
        user=user
    )


# Edit subject (admin only)
@main.route("/edit_subject/<subject_id>/<name>", methods=["GET", "POST"])
def edit_subject(subject_id, name):
    subject = Subject.query.get(subject_id)
    if request.method == "POST":
        subject.name = request.form.get("name")
        subject.description = request.form.get("description")
        db.session.commit()
        return redirect(url_for("main.admin_dashboard", name=name))
    return render_template("edit_subject.html", subject=subject, name=name)


# Edit chapter (admin only)
@main.route("/edit_chapter/<chapter_id>/<name>", methods=["GET", "POST"])
def edit_chapter(chapter_id, name):
    chapter = Chapter.query.get(chapter_id)
    if request.method == "POST":
        chapter.name = request.form.get("name")
        chapter.description = request.form.get("description")
        db.session.commit()
        return redirect(url_for("main.admin_dashboard", name=name))
    return render_template("edit_chapter.html", chapter=chapter, name=name)


# Edit quiz (admin only)
@main.route("/edit_quiz/<quiz_id>/<name>", methods=["GET", "POST"])
def edit_quiz(quiz_id, name):
    quiz = Quiz.query.get(quiz_id)
    if request.method == "POST":
        quiz.name = request.form.get("name")
        date_of_quiz_str = request.form.get("date_of_quiz")
        # Convert string to Python date object
        quiz.date_of_quiz = datetime.strptime(date_of_quiz_str, "%Y-%m-%d").date()
        quiz.time_duration = request.form.get("time_duration")
        db.session.commit()
        return redirect(url_for("main.admin_dashboard", name=name))
    return render_template("edit_quiz.html", quiz=quiz, name=name)


# Edit question (admin only)
@main.route("/edit_question/<question_id>/<name>", methods=["GET", "POST"])
def edit_question(question_id, name):
    question = Question.query.get(question_id)
    if request.method == "POST":
        question.question_statement = request.form.get("question_statement")
        question.option1 = request.form.get("option1")
        question.option2 = request.form.get("option2")
        question.option3 = request.form.get("option3")
        question.option4 = request.form.get("option4")
        question.correct_option = request.form.get("correct_option")
        db.session.commit()
        return redirect(url_for("main.admin_dashboard", name=name))
    return render_template("edit_question.html", question=question, name=name)


# Delete subject (admin only)
@main.route("/delete_subject/<subject_id>/<name>", methods=["GET"])
def delete_subject(subject_id, name):
    subject = Subject.query.get(subject_id)
    db.session.delete(subject)
    db.session.commit()
    return redirect(url_for("main.admin_dashboard", name=name))


# Delete chapter (admin only)
@main.route("/delete_chapter/<chapter_id>/<name>", methods=["GET"])
def delete_chapter(chapter_id, name):
    chapter = Chapter.query.get(chapter_id)
    db.session.delete(chapter)
    db.session.commit()
    return redirect(url_for("main.admin_dashboard", name=name))


# Delete quiz (admin only)
@main.route("/delete_quiz/<quiz_id>/<name>", methods=["GET"])
def delete_quiz(quiz_id, name):
    quiz = Quiz.query.get(quiz_id)
    db.session.delete(quiz)
    db.session.commit()
    return redirect(url_for("main.admin_dashboard", name=name))


# Delete question (admin only)
@main.route("/delete_question/<question_id>/<name>", methods=["GET"])
def delete_question(question_id, name):
    question = Question.query.get(question_id)
    db.session.delete(question)
    db.session.commit()
    return redirect(url_for("main.admin_dashboard", name=name))


# Search functionality (admin only)
@main.route("/search/<name>", methods=["GET", "POST"])
def search(name):
    if request.method == "POST":
        search_text = request.form.get("search_text")
        # Search for subjects
        subjects = Subject.query.filter(Subject.name.ilike(f"%{search_text}%")).all()
        # Search for chapters
        chapters = Chapter.query.filter(Chapter.name.ilike(f"%{search_text}%")).all()
        return render_template("admin_dashboard.html", name=name, subjects=subjects, chapters=chapters, search_text=search_text)
    return redirect(url_for("main.admin_dashboard", name=name))


# Search functionality (user only)
@main.route("/user_search/<id>/<name>", methods=["GET", "POST"])
def user_search(id, name):
    if request.method == "POST":
        search_text = request.form.get("search_text")
        user = User_Info.query.get(id)
        
        # Get all subjects and filter based on search
        all_subjects = Subject.query.all()
        filtered_subjects = []
        
        for subject in all_subjects:
            # Check if subject name matches search
            subject_matches = search_text.lower() in subject.name.lower()
            
            # Check if any chapter in this subject matches search
            chapters_match = False
            for chapter in subject.chapters:
                if search_text.lower() in chapter.name.lower():
                    chapters_match = True
                    break
                
                # Check if any quiz in this chapter matches search
                for quiz in chapter.quizzes:
                    if search_text.lower() in quiz.name.lower():
                        chapters_match = True
                        break
            
            # If subject, chapter, or quiz matches, include this subject
            if subject_matches or chapters_match:
                filtered_subjects.append(subject)
        
        from datetime import datetime
        return render_template(
            "user_dashboard.html",
            id=id,
            name=name,
            search_text=search_text,
            user=user,
            subjects=filtered_subjects,
            current_date=datetime.now().strftime("%d %B, %Y")
        )
    return redirect(url_for("main.user_dashboard", id=id, name=name))


# Summary page (admin only)
@main.route("/admin_summary")
def admin_summary():
    # Fetch all scores from the database
    scores = Score.query.all()

    if not scores:
        return render_template("admin_summary.html", plot_url=None)

    # Prepare data for the bar graph
    quiz_ids = [score.quiz_id for score in scores]
    total_scores = [score.total_scored for score in scores]

    # Create a bar graph
    plt.figure(figsize=(10, 6))
    plt.bar(quiz_ids, total_scores, color='blue')
    plt.xlabel("Quiz ID")
    plt.ylabel("Total Score")
    plt.title("Quiz ID vs Total Score")
    plt.xticks(quiz_ids)

    # Save the plot to a BytesIO object
    img = io.BytesIO()
    plt.savefig(img, format='png')
    img.seek(0)
    plot_url = base64.b64encode(img.getvalue()).decode('utf8')
    plt.close()

    # Render the summary page with the graph
    return render_template("admin_summary.html", plot_url=plot_url)


# User summary page
@main.route("/user_summary/<user_id>")
def user_summary(user_id):
    # Fetch scores for the specific user
    scores = Score.query.filter_by(user_id=user_id).all()
    user = User_Info.query.get(user_id)  # Fetch the user object

    if not scores:
        # Generate a placeholder graph if no data is available
        plt.figure(figsize=(10, 6))
        plt.text(0.5, 0.5, "No performance data available", fontsize=18, ha='center', va='center')
        plt.axis('off')

        # Save the placeholder graph to a BytesIO object
        img = io.BytesIO()
        plt.savefig(img, format='png')
        img.seek(0)
        plot_url = base64.b64encode(img.getvalue()).decode('utf8')
        plt.close()

        print("DEBUG: No scores available. Placeholder graph generated.")
        return render_template("user_summary.html", plot_url=plot_url, user=user)

    # Prepare data for the bar graph
    quiz_ids = [score.quiz_id for score in scores]
    user_scores = [score.total_scored for score in scores]

    print(f"DEBUG: Quiz IDs: {quiz_ids}")
    print(f"DEBUG: User Scores: {user_scores}")

    # Create a bar graph
    plt.figure(figsize=(10, 6))
    plt.bar(quiz_ids, user_scores, color='green')
    plt.xlabel("Quiz ID")
    plt.ylabel("Your Score")
    plt.title("Quiz ID vs Your Score")
    plt.xticks(quiz_ids)

    # Save the plot to a BytesIO object
    img = io.BytesIO()
    plt.savefig(img, format='png')
    img.seek(0)
    plot_url = base64.b64encode(img.getvalue()).decode('utf8')
    plt.close()

    print("DEBUG: Graph generated successfully.")
    return render_template("user_summary.html", plot_url=plot_url, user=user)

# API: User registration
@main.route("/api/register", methods=["POST"])
def api_register():
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")
    full_name = data.get("full_name")
    qualification = data.get("qualification")
    dob = data.get("dob")
    address = data.get("address")
    pin_code = data.get("pin_code")
    if not all([email, password, full_name, address, pin_code]):
        return jsonify({"error": "Missing required fields"}), 400
    if User_Info.query.filter_by(email=email).first():
        return jsonify({"error": "Email already registered"}), 409
    user = User_Info(
        email=email,
        password=generate_password_hash(password),
        full_name=full_name,
        qualification=qualification,
        dob=datetime.strptime(dob, "%Y-%m-%d") if dob else None,
        address=address,
        pin_code=pin_code
    )
    db.session.add(user)
    db.session.commit()
    return jsonify({"message": "Registration successful"}), 201

# API: Login (user or admin)
@main.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")
    user = User_Info.query.filter_by(email=email).first()
    if not user or not check_password_hash(user.password, password):
        return jsonify({"error": "Invalid credentials"}), 401
    token = create_jwt_token(user)
    return jsonify({
        "token": token,
        "role": "admin" if user.role == 0 else "user",
        "user_id": user.id,
        "full_name": user.full_name
    })

# Decorator: JWT-protected route
def jwt_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", None)
        if not auth_header or not auth_header.startswith("Bearer "):
            return jsonify({"error": "Missing or invalid token"}), 401
        token = auth_header.split(" ")[1]
        payload = decode_jwt_token(token)
        if not payload:
            return jsonify({"error": "Invalid or expired token"}), 401
        request.user = payload
        return f(*args, **kwargs)
    return decorated

# --- Admin-only decorator ---
def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not hasattr(request, 'user') or request.user["role"] != 0:
            return jsonify({"error": "Admin access required"}), 403
        return f(*args, **kwargs)
    return decorated

# --- Teacher-only decorator ---
def teacher_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 2:
            return jsonify({"error": "Teacher access required"}), 403
        return f(*args, **kwargs)
    return decorated

# --- Courses APIs ---
@main.route("/api/courses", methods=["POST"])
@jwt_required
@teacher_required
def create_course():
    try:
        data = request.get_json() or {}
        title = data.get("title")
        description = data.get("description", "")
        duration = data.get("duration")
        if not all([title, duration]):
            return jsonify({"error": "title and duration are required"}), 400
        teacher_id = request.user["user_id"]
        course = Course(title=title, description=description, duration=duration, teacher_id=teacher_id)
        db.session.add(course)
        db.session.commit()
        return jsonify({
            "id": course.id,
            "title": course.title,
            "description": course.description,
            "duration": course.duration,
            "teacher_id": course.teacher_id
        }), 201
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify({"error": "Failed to create course"}), 500

@main.route("/api/courses", methods=["GET"])
def list_courses():
    courses = Course.query.order_by(Course.created_at.desc()).all()
    return jsonify([
        {
            "id": c.id,
            "title": c.title,
            "description": c.description,
            "duration": c.duration,
            "teacher": {
                "id": c.teacher.id if c.teacher else None,
                "full_name": c.teacher.full_name if c.teacher else None
            }
        } for c in courses
    ])

# --- Subject CRUD ---
@main.route("/api/subjects", methods=["GET"])
@jwt_required
def get_subjects():
    subjects = Subject.query.all()
    return jsonify([
        {"id": s.id, "name": s.name, "description": s.description} for s in subjects
    ])

@main.route("/api/subjects", methods=["POST"])
@jwt_required
@admin_required
def create_subject():
    data = request.get_json()
    name = data.get("name")
    description = data.get("description")
    if not name:
        return jsonify({"error": "Name required"}), 400
    subject = Subject(name=name, description=description)
    db.session.add(subject)
    db.session.commit()
    return jsonify({"message": "Subject created", "id": subject.id}), 201

@main.route("/api/subjects/<int:subject_id>", methods=["PUT", "PATCH"])
@jwt_required
@admin_required
def update_subject(subject_id):
    subject = Subject.query.get(subject_id)
    if not subject:
        return jsonify({"error": "Subject not found"}), 404
    data = request.get_json()
    subject.name = data.get("name", subject.name)
    subject.description = data.get("description", subject.description)
    db.session.commit()
    return jsonify({"message": "Subject updated"})

@main.route("/api/subjects/<int:subject_id>", methods=["DELETE"])
@jwt_required
@admin_required
def api_delete_subject(subject_id):
    subject = Subject.query.get(subject_id)
    if not subject:
        return jsonify({"error": "Subject not found"}), 404
    db.session.delete(subject)
    db.session.commit()
    return jsonify({"message": "Subject deleted"})

# --- Chapter CRUD ---
@main.route("/api/chapters", methods=["GET"])
@jwt_required
def get_chapters():
    chapters = Chapter.query.all()
    return jsonify([
        {"id": c.id, "name": c.name, "description": c.description, "subject_id": c.subject_id} for c in chapters
    ])

@main.route("/api/chapters", methods=["POST"])
@jwt_required
@admin_required
def create_chapter():
    data = request.get_json()
    name = data.get("name")
    description = data.get("description")
    subject_id = data.get("subject_id")
    if not all([name, subject_id]):
        return jsonify({"error": "Name and subject_id required"}), 400
    chapter = Chapter(name=name, description=description, subject_id=subject_id)
    db.session.add(chapter)
    db.session.commit()
    return jsonify({"message": "Chapter created", "id": chapter.id}), 201

@main.route("/api/chapters/<int:chapter_id>", methods=["PUT", "PATCH"])
@jwt_required
@admin_required
def update_chapter(chapter_id):
    chapter = Chapter.query.get(chapter_id)
    if not chapter:
        return jsonify({"error": "Chapter not found"}), 404
    data = request.get_json()
    chapter.name = data.get("name", chapter.name)
    chapter.description = data.get("description", chapter.description)
    db.session.commit()
    return jsonify({"message": "Chapter updated"})

@main.route("/api/chapters/<int:chapter_id>", methods=["DELETE"])
@jwt_required
@admin_required
def api_delete_chapter(chapter_id):
    chapter = Chapter.query.get(chapter_id)
    if not chapter:
        return jsonify({"error": "Chapter not found"}), 404
    db.session.delete(chapter)
    db.session.commit()
    return jsonify({"message": "Chapter deleted"})

# --- Quiz CRUD ---
@main.route("/api/quizzes", methods=["GET"])
@jwt_required
def get_quizzes():
    quizzes = Quiz.query.all()
    return jsonify([
        {"id": q.id, "name": q.name, "date_of_quiz": q.date_of_quiz.isoformat(), "time_duration": q.time_duration, "remarks": q.remarks, "chapter_id": q.chapter_id} for q in quizzes
    ])

@main.route("/api/quizzes", methods=["POST"])
@jwt_required
@admin_required
def create_quiz():
    data = request.get_json()
    name = data.get("name")
    date_of_quiz = data.get("date_of_quiz")
    time_duration = data.get("time_duration")
    remarks = data.get("remarks")
    chapter_id = data.get("chapter_id")
    if not all([name, date_of_quiz, time_duration, chapter_id]):
        return jsonify({"error": "Missing required fields"}), 400
    quiz = Quiz(
        name=name,
        date_of_quiz=datetime.strptime(date_of_quiz, "%Y-%m-%d"),
        time_duration=time_duration,
        remarks=remarks,
        chapter_id=chapter_id
    )
    db.session.add(quiz)
    db.session.commit()
    return jsonify({"message": "Quiz created", "id": quiz.id}), 201

@main.route("/api/quizzes/<int:quiz_id>", methods=["PUT", "PATCH"])
@jwt_required
@admin_required
def update_quiz(quiz_id):
    quiz = Quiz.query.get(quiz_id)
    if not quiz:
        return jsonify({"error": "Quiz not found"}), 404
    data = request.get_json()
    quiz.name = data.get("name", quiz.name)
    if data.get("date_of_quiz"):
        quiz.date_of_quiz = datetime.strptime(data["date_of_quiz"], "%Y-%m-%d")
    quiz.time_duration = data.get("time_duration", quiz.time_duration)
    quiz.remarks = data.get("remarks", quiz.remarks)
    db.session.commit()
    return jsonify({"message": "Quiz updated"})

@main.route("/api/quizzes/<int:quiz_id>", methods=["DELETE"])
@jwt_required
@admin_required
def api_delete_quiz(quiz_id):
    quiz = Quiz.query.get(quiz_id)
    if not quiz:
        return jsonify({"error": "Quiz not found"}), 404
    db.session.delete(quiz)
    db.session.commit()
    return jsonify({"message": "Quiz deleted"})

# --- Question CRUD ---
@main.route("/api/questions", methods=["GET"])
@jwt_required
def get_questions():
    questions = Question.query.all()
    return jsonify([
        {"id": q.id, "question_statement": q.question_statement, "option1": q.option1, "option2": q.option2, "option3": q.option3, "option4": q.option4, "correct_option": q.correct_option, "quiz_id": q.quiz_id} for q in questions
    ])

@main.route("/api/questions", methods=["POST"])
@jwt_required
@admin_required
def create_question():
    data = request.get_json()
    question_statement = data.get("question_statement")
    option1 = data.get("option1")
    option2 = data.get("option2")
    option3 = data.get("option3")
    option4 = data.get("option4")
    correct_option = data.get("correct_option")
    quiz_id = data.get("quiz_id")
    if not all([question_statement, option1, option2, option3, option4, correct_option, quiz_id]):
        return jsonify({"error": "Missing required fields"}), 400
    question = Question(
        question_statement=question_statement,
        option1=option1,
        option2=option2,
        option3=option3,
        option4=option4,
        correct_option=correct_option,
        quiz_id=quiz_id
    )
    db.session.add(question)
    db.session.commit()
    return jsonify({"message": "Question created", "id": question.id}), 201

@main.route("/api/questions/<int:question_id>", methods=["PUT", "PATCH"])
@jwt_required
@admin_required
def update_question(question_id):
    question = Question.query.get(question_id)
    if not question:
        return jsonify({"error": "Question not found"}), 404
    data = request.get_json()
    question.question_statement = data.get("question_statement", question.question_statement)
    question.option1 = data.get("option1", question.option1)
    question.option2 = data.get("option2", question.option2)
    question.option3 = data.get("option3", question.option3)
    question.option4 = data.get("option4", question.option4)
    question.correct_option = data.get("correct_option", question.correct_option)
    db.session.commit()
    return jsonify({"message": "Question updated"})

@main.route("/api/questions/<int:question_id>", methods=["DELETE"])
@jwt_required
@admin_required
def api_delete_question(question_id):
    question = Question.query.get(question_id)
    if not question:
        return jsonify({"error": "Question not found"}), 404
    db.session.delete(question)
    db.session.commit()
    return jsonify({"message": "Question deleted"})

# API: Example protected profile endpoint
@main.route("/api/profile", methods=["GET"])
@jwt_required
def api_profile():
    user_id = request.user["user_id"]
    user = User_Info.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    return jsonify({
        "user_id": user.id,
        "email": user.email,
        "role": "admin" if user.role == 0 else "user",
        "full_name": user.full_name,
        "qualification": user.qualification,
        "dob": user.dob.isoformat() if user.dob else None,
        "address": user.address,
        "pin_code": user.pin_code
    })

# --- User Quiz Endpoints ---

# List all available quizzes (with subject/chapter info)
@main.route("/api/user/quizzes", methods=["GET"])
@jwt_required
def user_list_quizzes():
    cache = get_cache()
    cached_result = cache.get('user_quizzes')
    if cached_result:
        return jsonify(cached_result)
    
    quizzes = Quiz.query.all()
    result = []
    for q in quizzes:
        chapter = Chapter.query.get(q.chapter_id)
        subject = Subject.query.get(chapter.subject_id) if chapter else None
        result.append({
            "id": q.id,
            "name": q.name,
            "date_of_quiz": q.date_of_quiz.isoformat(),
            "time_duration": q.time_duration,
            "remarks": q.remarks,
            "chapter": {"id": chapter.id, "name": chapter.name} if chapter else None,
            "subject": {"id": subject.id, "name": subject.name} if subject else None
        })
    
    cache.set('user_quizzes', result, timeout=300)
    return jsonify(result)

# Get quiz details (questions, options)
@main.route("/api/user/quizzes/<int:quiz_id>", methods=["GET"])
@jwt_required
def user_quiz_detail(quiz_id):
    quiz = Quiz.query.get(quiz_id)
    if not quiz:
        return jsonify({"error": "Quiz not found"}), 404
    questions = Question.query.filter_by(quiz_id=quiz_id).all()
    return jsonify({
        "id": quiz.id,
        "name": quiz.name,
        "date_of_quiz": quiz.date_of_quiz.isoformat(),
        "time_duration": quiz.time_duration,
        "remarks": quiz.remarks,
        "questions": [
            {
                "id": q.id,
                "question_statement": q.question_statement,
                "option1": q.option1,
                "option2": q.option2,
                "option3": q.option3,
                "option4": q.option4
            } for q in questions
        ]
    })

# Attempt a quiz (submit answers, auto-score, record attempt)
@main.route("/api/user/quizzes/<int:quiz_id>/attempt", methods=["POST"])
@jwt_required
def user_attempt_quiz(quiz_id):
    user_id = request.user["user_id"]
    quiz = Quiz.query.get(quiz_id)
    if not quiz:
        return jsonify({"error": "Quiz not found"}), 404
    questions = Question.query.filter_by(quiz_id=quiz_id).all()
    data = request.get_json()
    answers = data.get("answers")  # {question_id: selected_option}
    if not answers or not isinstance(answers, dict):
        return jsonify({"error": "Answers must be provided as a dict"}), 400
    total_score = 0
    for q in questions:
        selected = answers.get(str(q.id)) or answers.get(q.id)
        if selected and selected == q.correct_option:
            total_score += 1
    # Record the attempt
    score = Score(user_id=user_id, quiz_id=quiz_id, total_scored=total_score, time_stamp_of_attempt=datetime.now())
    db.session.add(score)
    db.session.commit()
    return jsonify({
        "message": "Quiz submitted",
        "total_scored": total_score,
        "total_questions": len(questions)
    })

# View user's quiz history/scores
@main.route("/api/user/scores", methods=["GET"])
@jwt_required
def user_scores():
    user_id = request.user["user_id"]
    scores = Score.query.filter_by(user_id=user_id).all()
    result = []
    for s in scores:
        quiz = Quiz.query.get(s.quiz_id)
        result.append({
            "score_id": s.id,
            "quiz_id": s.quiz_id,
            "quiz_name": quiz.name if quiz else None,
            "total_scored": s.total_scored,
            "time_stamp_of_attempt": s.time_stamp_of_attempt.isoformat() if s.time_stamp_of_attempt else None
        })
    return jsonify(result)

# --- Celery Task Trigger Endpoints ---

# Admin: Trigger daily reminders
@main.route("/api/admin/daily_reminder", methods=["POST"])
@jwt_required
@admin_required
def trigger_daily_reminder():
    task = daily_reminder_task.delay()
    return jsonify({"message": "Daily reminder task started", "task_id": task.id})

# Admin: Trigger monthly report
@main.route("/api/admin/monthly_report", methods=["POST"])
@jwt_required
@admin_required
def trigger_monthly_report():
    task = monthly_report_task.delay()
    return jsonify({"message": "Monthly report task started", "task_id": task.id})

# User: Trigger their own CSV export
@main.route("/api/user/export_csv", methods=["POST"])
@jwt_required
def trigger_user_csv_export():
    user_id = request.user["user_id"]
    task = export_csv_task.delay(user_id)
    return jsonify({"message": "CSV export started", "task_id": task.id})

# Admin: Trigger CSV export for any user
@main.route("/api/admin/export_csv/<int:user_id>", methods=["POST"])
@jwt_required
@admin_required
def trigger_admin_csv_export(user_id):
    task = export_csv_task.delay(user_id)
    return jsonify({"message": f"CSV export for user {user_id} started", "task_id": task.id})

# --- Admin Statistics Endpoint ---
@main.route("/api/admin/stats", methods=["GET"])
@jwt_required
@admin_required
def admin_stats():
    """Get comprehensive admin statistics"""
    try:
        # Basic counts
        total_users = User_Info.query.filter(User_Info.role == 1).count()
        total_subjects = Subject.query.count()
        total_chapters = Chapter.query.count()
        total_quizzes = Quiz.query.count()
        total_attempts = Score.query.count()
        
        # Enhanced user analytics
        users_with_attempts = db.session.query(User_Info).join(Score).filter(User_Info.role == 1).distinct().count()
        
        # Calculate average score across all attempts
        avg_score_result = db.session.query(db.func.avg(Score.total_scored)).scalar()
        average_score = round(avg_score_result or 0, 1)
        
        # Today's attempts
        today = datetime.now().date()
        todays_attempts = Score.query.filter(
            db.func.date(Score.time_stamp_of_attempt) == today
        ).count()
        
        # Active users this week (users with attempts in last 7 days)
        week_ago = datetime.now() - timedelta(days=7)
        active_this_week = db.session.query(User_Info).join(Score).filter(
            User_Info.role == 1,
            Score.time_stamp_of_attempt >= week_ago
        ).distinct().count()
        
        # Get all users with their detailed analytics
        users = db.session.query(User_Info).filter(User_Info.role == 1).all()
        users_data = []
        
        for user in users:
            user_scores = Score.query.filter_by(user_id=user.id).all()
            
            # Calculate user-specific analytics
            avg_score = 0
            best_score = 0
            last_activity = None
            status = 'inactive'
            
            if user_scores:
                scores_list = [score.total_scored for score in user_scores]
                avg_score = round(sum(scores_list) / len(scores_list), 1)
                best_score = max(scores_list)
                last_activity = max(score.time_stamp_of_attempt for score in user_scores)
                
                # Determine status based on recent activity
                if last_activity and (datetime.now() - last_activity).days <= 7:
                    status = 'active'
                elif last_activity and (datetime.now() - last_activity).days <= 30:
                    status = 'recent'
            
            users_data.append({
                'id': user.id,
                'full_name': user.full_name,
                'email': user.email,
                'qualification': user.qualification,
                'dob': user.dob.isoformat() if user.dob else None,
                'address': user.address,
                'pin_code': user.pin_code,
                'scores': [{
                    'id': score.id,
                    'total_scored': score.total_scored,
                    'time_stamp_of_attempt': score.time_stamp_of_attempt.isoformat(),
                    'quiz': {
                        'name': score.quiz.name if score.quiz else 'Unknown Quiz',
                        'chapter': {
                            'subject': {
                                'name': score.quiz.chapter.subject.name if score.quiz and score.quiz.chapter else 'Unknown Subject'
                            }
                        } if score.quiz and score.quiz.chapter else None
                    } if score.quiz else None
                } for score in user_scores],
                'averageScore': avg_score,
                'bestScore': best_score,
                'lastActivity': last_activity.isoformat() if last_activity else None,
                'status': status
            })

        return jsonify({
            'totalUsers': total_users,
            'totalSubjects': total_subjects,
            'totalChapters': total_chapters,
            'totalQuizzes': total_quizzes,
            'totalAttempts': total_attempts,
            'activeUsers': active_this_week,
            'usersAttemptingQuizzes': users_with_attempts,
            'averageScore': average_score,
            'todaysAttempts': todays_attempts,
            'activeThisWeek': active_this_week,
            'users': users_data,
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# --- Admin Users Endpoint ---
@main.route("/api/admin/users", methods=["GET"])
@jwt_required
@admin_required
def admin_users():
    """Get all users for admin management"""
    try:
        users = User_Info.query.filter_by(role=1).all()
        users_data = []
        
        for user in users:
            scores_count = Score.query.filter_by(user_id=user.id).count()
            users_data.append({
                "id": user.id,
                "full_name": user.full_name,
                "email": user.email,
                "qualification": user.qualification,
                "dob": user.dob.isoformat() if user.dob else None,
                "address": user.address,
                "pin_code": user.pin_code,
                "scores_count": scores_count
            })
        
        return jsonify(users_data)
    except Exception as e:
        return jsonify({"error": "Failed to fetch users"}), 500

# --- Admin Teacher Management APIs ---
@main.route("/api/admin/teachers", methods=["GET"])
@jwt_required
@admin_required
def admin_list_teachers():
    teachers = User_Info.query.filter_by(role=2).all()
    return jsonify([
        {
            "id": t.id,
            "full_name": t.full_name,
            "email": t.email,
            "qualification": t.qualification,
            "address": t.address,
            "pin_code": t.pin_code
        } for t in teachers
    ])

@main.route("/api/admin/teachers", methods=["POST"])
@jwt_required
@admin_required
def admin_create_teacher():
    data = request.get_json() or {}
    email = data.get("email")
    password = data.get("password") or "1234"
    full_name = data.get("full_name") or "Teacher"
    qualification = data.get("qualification") or ""
    address = data.get("address") or ""
    pin_code = data.get("pin_code") or 0
    if not email:
        return jsonify({"error": "email is required"}), 400
    if User_Info.query.filter_by(email=email).first():
        return jsonify({"error": "Email already exists"}), 409
    teacher = User_Info(
        email=email,
        password=generate_password_hash(password),
        role=2,
        full_name=full_name,
        qualification=qualification,
        dob=None,
        address=address,
        pin_code=pin_code,
    )
    db.session.add(teacher)
    db.session.commit()
    return jsonify({"id": teacher.id, "email": teacher.email}), 201

@main.route("/api/admin/teachers/<int:teacher_id>", methods=["DELETE"])
@jwt_required
@admin_required
def admin_delete_teacher(teacher_id):
    teacher = User_Info.query.get(teacher_id)
    if not teacher or teacher.role != 2:
        return jsonify({"error": "Teacher not found"}), 404
    db.session.delete(teacher)
    db.session.commit()
    return jsonify({"message": "Teacher deleted"})

# --- Admin Export Users Endpoint ---
@main.route("/api/admin/export-users", methods=["POST"])
@jwt_required
@admin_required
def admin_export_users():
    """Export all users data as CSV"""
    try:
        users = User_Info.query.filter_by(role=1).all()
        
        # Generate CSV content
        csv_content = "user_id,full_name,email,qualification,dob,address,pin_code,quiz_attempts\n"
        for user in users:
            scores_count = Score.query.filter_by(user_id=user.id).count()
            csv_content += f"{user.id},{user.full_name},{user.email},{user.qualification or ''},{user.dob or ''},{user.address},{user.pin_code},{scores_count}\n"
        
        return csv_content, 200, {
            'Content-Type': 'text/csv',
            'Content-Disposition': 'attachment; filename=users_export.csv'
        }
    except Exception as e:
        return jsonify({"error": "Failed to export users"}), 500

# --- User Export CSV Endpoint ---
@main.route("/api/user/export_csv", methods=["POST"])
@jwt_required
def user_export_csv():
    """Export user's quiz data as CSV"""
    try:
        user_id = request.user["user_id"]
        scores = Score.query.filter_by(user_id=user_id).all()
        
        # Generate CSV content
        csv_content = "quiz_id,chapter_id,date_of_quiz,score,remarks\n"
        for score in scores:
            quiz = Quiz.query.get(score.quiz_id)
            if quiz:
                csv_content += f"{score.quiz_id},{quiz.chapter_id},{quiz.date_of_quiz},{score.total_scored},{quiz.remarks or ''}\n"
        
        return csv_content, 200, {
            'Content-Type': 'text/csv',
            'Content-Disposition': 'attachment; filename=quiz_results.csv'
        }
    except Exception as e:
        return jsonify({"error": "Failed to export data"}), 500

# --- Admin Export User CSV Endpoint ---
@main.route("/api/admin/export_csv/<int:user_id>", methods=["POST"])
@jwt_required
@admin_required
def admin_export_user_csv(user_id):
    """Export specific user's quiz data as CSV"""
    try:
        scores = Score.query.filter_by(user_id=user_id).all()
        
        # Generate CSV content
        csv_content = "quiz_id,chapter_id,date_of_quiz,score,remarks\n"
        for score in scores:
            quiz = Quiz.query.get(score.quiz_id)
            if quiz:
                csv_content += f"{score.quiz_id},{quiz.chapter_id},{quiz.date_of_quiz},{score.total_scored},{quiz.remarks or ''}\n"
        
        return csv_content, 200, {
            'Content-Type': 'text/csv',
            'Content-Disposition': f'attachment; filename=user_{user_id}_data.csv'
        }
    except Exception as e:
        return jsonify({"error": "Failed to export user data"}), 500

# --- Admin Daily Reminder Endpoint ---
@main.route("/api/admin/daily_reminder", methods=["POST"])
@jwt_required
@admin_required
def admin_daily_reminder():
    """Trigger daily reminders manually"""
    try:
        # Import the task here to avoid circular imports
        from .tasks import daily_reminder_task
        task = daily_reminder_task.delay()
        return jsonify({"message": "Daily reminders triggered", "task_id": task.id})
    except Exception as e:
        return jsonify({"error": "Failed to trigger reminders"}), 500

# --- Admin Monthly Report Endpoint ---
@main.route("/api/admin/monthly_report", methods=["POST"])
@jwt_required
@admin_required
def admin_monthly_report():
    """Trigger monthly reports manually"""
    try:
        # Import the task here to avoid circular imports
        from .tasks import monthly_report_task
        task = monthly_report_task.delay()
        return jsonify({"message": "Monthly reports triggered", "task_id": task.id})
    except Exception as e:
        return jsonify({"error": "Failed to trigger monthly reports"}), 500

# --- Admin User Management Route ---
@main.route("/admin/user-management", methods=["GET", "POST"])
def admin_user_management():
    name = request.args.get("name") or (current_user.email if hasattr(current_user, "email") else "")
    search_text = None
    if request.method == "POST":
        search_text = request.form.get("search_text")
        if search_text:
            users = User_Info.query.filter(
                db.or_(
                    User_Info.full_name.ilike(f"%{search_text}%"),
                    User_Info.email.ilike(f"%{search_text}%"),
                    User_Info.qualification.ilike(f"%{search_text}%")
                )
            ).all()
        else:
            users = User_Info.query.all()
    else:
        users = User_Info.query.all()

    # Attach scores to each user
    for u in users:
        u.scores = Score.query.filter_by(user_id=u.id).all()

    return render_template("user_management.html", users=users, name=name, user=current_user, search_text=search_text)

# --- Admin Teacher Management Page ---
@main.route("/admin/teacher-management", methods=["GET", "POST"])
@login_required
def admin_teacher_management():
    # Only admin can access the page
    if not current_user or current_user.role != 0:
        return redirect(url_for("main.signin"))
    name = current_user.email
    if request.method == "POST":
        # Handle creation via form
        course_name = request.form.get("course_name")
        course_description = request.form.get("course_description")
        teacher_email = request.form.get("teacher_email")
        password = request.form.get("password")
        teacher_name = request.form.get("teacher_name") or teacher_email
        if not all([teacher_email, password]):
            return redirect(url_for('main.admin_teacher_management'))
        # Create or fetch User_Info
        existing_user = User_Info.query.filter_by(email=teacher_email).first()
        if existing_user:
            existing_user.role = 2
            teacher_user = existing_user
        else:
            teacher_user = User_Info(
                email=teacher_email,
                password=generate_password_hash(password),
                role=2,
                full_name=teacher_name,
                qualification="",
                dob=None,
                address="",
                pin_code=0
            )
            db.session.add(teacher_user)
            db.session.flush()
        # Create Teacher record
        teacher = Teacher(
            user_id=teacher_user.id,
            name=teacher_name,
            email=teacher_email,
            password_hash=generate_password_hash(password),
            course_name=course_name,
            course_description=course_description
        )
        db.session.add(teacher)
        db.session.commit()
        # If course provided, auto-create a subject (admin-only responsibility) and assign to teacher
        if course_name:
            # Create Subject if not exists
            subject = Subject.query.filter_by(name=course_name).first()
            if not subject:
                subject = Subject(name=course_name, description=course_description or "")
                db.session.add(subject)
                db.session.flush()
            # Assign subject to teacher via mapping
            if not TeacherSubject.query.filter_by(teacher_user_id=teacher_user.id, subject_id=subject.id).first():
                db.session.add(TeacherSubject(teacher_user_id=teacher_user.id, subject_id=subject.id))
            db.session.commit()
        return redirect(url_for('main.admin_teacher_management'))

    # GET: list teachers
    teachers = Teacher.query.order_by(Teacher.created_at.desc()).all()
    total_teachers = len(teachers)
    all_subjects = Subject.query.all()
    teacher_id_to_subjects = {}
    for t in teachers:
        subject_ids = [ts.subject_id for ts in TeacherSubject.query.filter_by(teacher_user_id=t.user_id).all()]
        teacher_id_to_subjects[t.id] = Subject.query.filter(Subject.id.in_(subject_ids)).all() if subject_ids else []
    return render_template("teacher_management.html", name=name, teachers=teachers, total_teachers=total_teachers, subjects=all_subjects, teacher_id_to_subjects=teacher_id_to_subjects)

@main.route('/admin/teacher/delete/<int:teacher_id>', methods=['POST'])
@login_required
def admin_delete_teacher_page(teacher_id):
    if not current_user or current_user.role != 0:
        return redirect(url_for("main.signin"))
    teacher = Teacher.query.get(teacher_id)
    if teacher:
        linked_user = User_Info.query.get(teacher.user_id)
        TeacherSubject.query.filter_by(teacher_user_id=teacher.user_id).delete()
        db.session.delete(teacher)
        if linked_user and linked_user.role == 2:
            db.session.delete(linked_user)
        db.session.commit()
    return redirect(url_for('main.admin_teacher_management'))

@main.route('/admin/teacher/assign-subject', methods=['POST'])
@login_required
def admin_assign_subject_to_teacher():
    if not current_user or current_user.role != 0:
        return redirect(url_for("main.signin"))
    teacher_id = request.form.get('teacher_id')
    subject_id = request.form.get('subject_id')
    teacher = Teacher.query.get(teacher_id)
    subject = Subject.query.get(subject_id)
    if not teacher or not subject:
        return redirect(url_for('main.admin_teacher_management'))
    exists = TeacherSubject.query.filter_by(teacher_user_id=teacher.user_id, subject_id=subject.id).first()
    if not exists:
        db.session.add(TeacherSubject(teacher_user_id=teacher.user_id, subject_id=subject.id))
        db.session.commit()
    return redirect(url_for('main.admin_teacher_management'))

@main.route('/admin/teacher/unassign-subject', methods=['POST'])
@login_required
def admin_unassign_subject_from_teacher():
    if not current_user or current_user.role != 0:
        return redirect(url_for("main.signin"))
    teacher_id = request.form.get('teacher_id')
    subject_id = request.form.get('subject_id')
    teacher = Teacher.query.get(teacher_id)
    if not teacher:
        return redirect(url_for('main.admin_teacher_management'))
    TeacherSubject.query.filter_by(teacher_user_id=teacher.user_id, subject_id=subject_id).delete()
    db.session.commit()
    return redirect(url_for('main.admin_teacher_management'))


@main.route("/teacher/<int:id>/user-management")
@teacher_required
def teacher_user_management(id):
    """Teacher can see students who attempted their quizzes"""
    # Get teacher's assigned subjects
    teacher_subjects = TeacherSubject.query.filter_by(teacher_user_id=id).all()
    subject_ids = [ts.subject_id for ts in teacher_subjects]
    
    if not subject_ids:
        return render_template("teacher_user_management.html", 
                             teacher_name="Teacher",
                             students=[],
                             msg="No subjects assigned yet")
    
    # Get all chapters under teacher's subjects
    chapters = Chapter.query.filter(Chapter.subject_id.in_(subject_ids)).all()
    chapter_ids = [c.id for c in chapters]
    
    if not chapter_ids:
        return render_template("teacher_user_management.html", 
                             teacher_name="Teacher",
                             students=[],
                             msg="No chapters available for your subjects")
    
    # Get all quizzes under teacher's chapters
    quizzes = Quiz.query.filter(Quiz.chapter_id.in_(chapter_ids)).all()
    quiz_ids = [q.id for q in quizzes]
    
    if not quiz_ids:
        return render_template("teacher_user_management.html", 
                             teacher_name="Teacher",
                             students=[],
                             msg="No quizzes available for your subjects")
    
    # Get students who attempted these quizzes
    students = db.session.query(User_Info).join(Score).filter(
        Score.quiz_id.in_(quiz_ids),
        User_Info.role == 1  # Only students
    ).distinct().all()
    
    # Compute attempt counts per student (for teacher's quizzes only)
    attempt_counts = dict(
        db.session.query(Score.user_id, db.func.count(Score.id))
        .filter(Score.quiz_id.in_(quiz_ids))
        .group_by(Score.user_id)
        .all()
    )

    # Build detailed score rows per student to show in modal
    score_rows = (
        db.session.query(Score, Quiz)
        .join(Quiz, Score.quiz_id == Quiz.id)
        .filter(Score.quiz_id.in_(quiz_ids))
        .order_by(Score.time_stamp_of_attempt.desc())
        .all()
    )

    scores_by_student = {}
    for score, quiz in score_rows:
        scores_by_student.setdefault(score.user_id, []).append({
            "quiz_name": quiz.name,
            "score": score.total_scored,
            "attempted_at": score.time_stamp_of_attempt.strftime('%Y-%m-%d %H:%M') if score.time_stamp_of_attempt else 'N/A',
        })

    return render_template(
        "teacher_user_management.html",
                         teacher_name="Teacher",
                         students=students,
        attempt_counts=attempt_counts,
        scores_by_student=scores_by_student,
        msg="",
    )

# User Dashboard Route
@main.route("/user/<int:id>/<name>")
@login_required
def user_dashboard(id, name):
    """User dashboard showing enrolled courses with progress tracking"""
    from datetime import datetime
    
    # Get user
    user = User_Info.query.get_or_404(id)
    
    # Check if user has selected a branch
    if not user.branch_id:
        return redirect(url_for("main.branch_selection", user_id=id))
    
    # Get user's enrolled subjects
    user_enrollments = UserEnrollment.query.filter_by(user_id=id, is_active=True).all()
    enrolled_subject_ids = [enrollment.subject_id for enrollment in user_enrollments]
    
    if not enrolled_subject_ids:
        return render_template("user_dashboard.html", 
                             id=id, name=name, subjects=[], user=user, 
                             current_date=datetime.now().strftime("%d %B, %Y"))
    
    # Get subjects with progress data (only from user's branch)
    subjects = Subject.query.filter(
        Subject.id.in_(enrolled_subject_ids),
        Subject.branch_id == user.branch_id
    ).all()
    
    # Calculate progress for each subject
    for subject in subjects:
        # Get all quizzes in this subject
        all_quizzes = []
        for chapter in subject.chapters:
            all_quizzes.extend(chapter.quizzes)
        
        # Get user's scores for these quizzes (get the latest attempt for each quiz)
        quiz_ids = [quiz.id for quiz in all_quizzes]
        user_scores = []
        for quiz_id in quiz_ids:
            # Get the latest score for this quiz
            latest_score = Score.query.filter(
                Score.user_id == id,
                Score.quiz_id == quiz_id
            ).order_by(Score.time_stamp_of_attempt.desc()).first()
            if latest_score:
                user_scores.append(latest_score)
        
        # Calculate progress based on actual scores
        total_quizzes = len(all_quizzes)
        if total_quizzes > 0:
            # Calculate average score percentage across all quizzes
            total_score_percentage = 0
            scored_quizzes = 0
            
            for quiz in all_quizzes:
                # Get the latest score for this quiz
                latest_score = Score.query.filter(
                    Score.user_id == id,
                    Score.quiz_id == quiz.id
                ).order_by(Score.time_stamp_of_attempt.desc()).first()
                
                if latest_score:
                    # Get total questions in this quiz
                    total_questions = Question.query.filter_by(quiz_id=quiz.id).count()
                    if total_questions > 0:
                        # Calculate percentage for this quiz
                        quiz_percentage = (latest_score.total_scored / total_questions) * 100
                        total_score_percentage += quiz_percentage
                        scored_quizzes += 1
                        quiz.user_score = latest_score.total_scored
                        quiz.user_percentage = quiz_percentage
                    else:
                        quiz.user_score = None
                        quiz.user_percentage = 0
                else:
                    quiz.user_score = None
                    quiz.user_percentage = 0
            
            # Calculate overall progress percentage
            if scored_quizzes > 0:
                subject.progress_percentage = total_score_percentage / scored_quizzes
            else:
                subject.progress_percentage = 0
        else:
            subject.progress_percentage = 0
        
        # Add progress data to subject
        subject.total_quizzes = total_quizzes
        subject.completed_quizzes = len(user_scores)
    
    return render_template("user_dashboard.html", 
                         id=id, name=name, subjects=subjects, user=user,
                         current_date=datetime.now().strftime("%d %B, %Y"))

# Subject Details Route (for viewing quizzes)
@main.route("/user/<int:user_id>/subject/<int:subject_id>")
@login_required
def user_subject_details(user_id, subject_id):
    """Show subject details with quizzes for a user"""
    # Get user
    user = User_Info.query.get_or_404(user_id)
    
    # Get subject
    subject = Subject.query.get_or_404(subject_id)
    
    # Check if user is enrolled in this subject
    enrollment = UserEnrollment.query.filter_by(
        user_id=user_id, 
        subject_id=subject_id, 
        is_active=True
    ).first()
    
    if not enrollment:
        return redirect(url_for("main.user_dashboard", id=user_id, name=user.full_name))
    
    # Get user's scores for this subject's quizzes (latest attempt for each quiz)
    for chapter in subject.chapters:
        for quiz in chapter.quizzes:
            # Get the latest score for this quiz
            latest_score = Score.query.filter(
                Score.user_id == user_id,
                Score.quiz_id == quiz.id
            ).order_by(Score.time_stamp_of_attempt.desc()).first()
            
            if latest_score:
                # Get total questions in this quiz
                total_questions = Question.query.filter_by(quiz_id=quiz.id).count()
                if total_questions > 0:
                    quiz.user_score = latest_score.total_scored
                    quiz.user_percentage = (latest_score.total_scored / total_questions) * 100
                    quiz.total_questions = total_questions
                else:
                    quiz.user_score = None
                    quiz.user_percentage = 0
                    quiz.total_questions = 0
            else:
                quiz.user_score = None
                quiz.user_percentage = 0
                quiz.total_questions = Question.query.filter_by(quiz_id=quiz.id).count()
    
    return render_template("user_subject_details.html", 
                         user=user, subject=subject, 
                         current_date=datetime.now().strftime("%d %B, %Y"))

# Discussion Forum Routes
@main.route("/user/<int:user_id>/subject/<int:subject_id>/discussion")
@login_required
def course_discussion(user_id, subject_id):
    """Course discussion forum page"""
    # Get user
    user = User_Info.query.get_or_404(user_id)
    
    # Get subject
    subject = Subject.query.get_or_404(subject_id)
    
    # Check if user is enrolled in this subject
    enrollment = UserEnrollment.query.filter_by(
        user_id=user_id, 
        subject_id=subject_id, 
        is_active=True
    ).first()
    
    if not enrollment:
        return redirect(url_for("main.user_dashboard", id=user_id, name=user.full_name))
    
    # Get all discussions for this subject
    discussions = Discussion.query.filter_by(subject_id=subject_id).order_by(Discussion.created_at.asc()).all()
    
    return render_template("course_discussion.html", 
                         user=user, subject=subject, discussions=discussions,
                         current_date=datetime.now().strftime("%d %B, %Y"))

@main.route("/user/<int:user_id>/subject/<int:subject_id>/discussion", methods=["POST"])
@login_required
def post_discussion_message(user_id, subject_id):
    """Post a new message to the discussion forum"""
    # Get user
    user = User_Info.query.get_or_404(user_id)
    
    # Get subject
    subject = Subject.query.get_or_404(subject_id)
    
    # Check if user is enrolled in this subject
    enrollment = UserEnrollment.query.filter_by(
        user_id=user_id, 
        subject_id=subject_id, 
        is_active=True
    ).first()
    
    if not enrollment:
        return redirect(url_for("main.user_dashboard", id=user_id, name=user.full_name))
    
    # Get message from form
    message = request.form.get("message", "").strip()
    
    if not message:
        return redirect(url_for("main.course_discussion", user_id=user_id, subject_id=subject_id))
    
    # Create new discussion message
    discussion = Discussion(
        subject_id=subject_id,
        user_id=user_id,
        message=message
    )
    
    db.session.add(discussion)
    db.session.commit()
    
    return redirect(url_for("main.course_discussion", user_id=user_id, subject_id=subject_id))

@main.route("/teacher/<int:teacher_id>/subject/<int:subject_id>/discussion")
@login_required
def teacher_course_discussion(teacher_id, subject_id):
    """Teacher view of course discussion forum"""
    # Check if teacher has access to this subject
    teacher_subject = TeacherSubject.query.filter_by(
        teacher_user_id=teacher_id, 
        subject_id=subject_id
    ).first()
    
    if not teacher_subject:
        return redirect(url_for("main.teacher_dashboard", id=teacher_id, name=current_user.full_name))
    
    # Get subject
    subject = Subject.query.get_or_404(subject_id)
    
    # Get all discussions for this subject
    discussions = Discussion.query.filter_by(subject_id=subject_id).order_by(Discussion.created_at.asc()).all()
    
    return render_template("teacher_course_discussion.html", 
                         teacher=current_user, subject=subject, discussions=discussions,
                         current_date=datetime.now().strftime("%d %B, %Y"))

@main.route("/teacher/<int:teacher_id>/subject/<int:subject_id>/discussion", methods=["POST"])
@login_required
def teacher_post_discussion_message(teacher_id, subject_id):
    """Teacher posts a new message to the discussion forum"""
    # Check if teacher has access to this subject
    teacher_subject = TeacherSubject.query.filter_by(
        teacher_user_id=teacher_id, 
        subject_id=subject_id
    ).first()
    
    if not teacher_subject:
        return redirect(url_for("main.teacher_dashboard", id=teacher_id, name=current_user.full_name))
    
    # Get subject
    subject = Subject.query.get_or_404(subject_id)
    
    # Get message from form
    message = request.form.get("message", "").strip()
    
    if not message:
        return redirect(url_for("main.teacher_course_discussion", teacher_id=teacher_id, subject_id=subject_id))
    
    # Create new discussion message
    discussion = Discussion(
        subject_id=subject_id,
        user_id=teacher_id,
        message=message
    )
    
    db.session.add(discussion)
    db.session.commit()
    
    return redirect(url_for("main.teacher_course_discussion", teacher_id=teacher_id, subject_id=subject_id))

@main.route("/api/discussions/<int:subject_id>", methods=["GET"])
@login_required
def api_get_discussions(subject_id):
    """API endpoint to get discussions for a subject"""
    # Check if user has access to this subject
    if current_user.role == 1:  # Student
        enrollment = UserEnrollment.query.filter_by(
            user_id=current_user.id, 
            subject_id=subject_id, 
            is_active=True
        ).first()
        if not enrollment:
            return jsonify({"error": "Access denied"}), 403
    elif current_user.role == 2:  # Teacher
        teacher_subject = TeacherSubject.query.filter_by(
            teacher_user_id=current_user.id, 
            subject_id=subject_id
        ).first()
        if not teacher_subject:
            return jsonify({"error": "Access denied"}), 403
    elif current_user.role != 0:  # Not admin
        return jsonify({"error": "Access denied"}), 403
    
    # Get discussions
    discussions = Discussion.query.filter_by(subject_id=subject_id).order_by(Discussion.created_at.asc()).all()
    
    return jsonify([discussion.to_dict() for discussion in discussions])

@main.route("/api/discussions/<int:subject_id>", methods=["POST"])
@login_required
def api_post_discussion(subject_id):
    """API endpoint to post a new discussion message"""
    # Check if user has access to this subject
    if current_user.role == 1:  # Student
        enrollment = UserEnrollment.query.filter_by(
            user_id=current_user.id, 
            subject_id=subject_id, 
            is_active=True
        ).first()
        if not enrollment:
            return jsonify({"error": "Access denied"}), 403
    elif current_user.role == 2:  # Teacher
        teacher_subject = TeacherSubject.query.filter_by(
            teacher_user_id=current_user.id, 
            subject_id=subject_id
        ).first()
        if not teacher_subject:
            return jsonify({"error": "Access denied"}), 403
    elif current_user.role != 0:  # Not admin
        return jsonify({"error": "Access denied"}), 403
    
    # Get message from request
    data = request.get_json()
    message = data.get("message", "").strip()
    
    if not message:
        return jsonify({"error": "Message is required"}), 400
    
    # Create new discussion message
    discussion = Discussion(
        subject_id=subject_id,
        user_id=current_user.id,
        message=message
    )
    
    db.session.add(discussion)
    db.session.commit()
    
    return jsonify(discussion.to_dict()), 201

@main.route("/api/discussions/<int:discussion_id>/edit", methods=["PUT", "PATCH"])
@login_required
def api_edit_discussion(discussion_id):
    """API endpoint to edit a discussion message"""
    discussion = Discussion.query.get_or_404(discussion_id)
    
    # Check if user owns this message
    if discussion.user_id != current_user.id:
        return jsonify({"error": "You can only edit your own messages"}), 403
    
    # Get message from request
    data = request.get_json()
    message = data.get("message", "").strip()
    
    if not message:
        return jsonify({"error": "Message is required"}), 400
    
    # Update the message
    discussion.message = message
    discussion.updated_at = datetime.utcnow()
    db.session.commit()
    
    return jsonify(discussion.to_dict())

@main.route("/api/discussions/<int:discussion_id>/delete", methods=["DELETE"])
@login_required
def api_delete_discussion(discussion_id):
    """API endpoint to delete a discussion message"""
    discussion = Discussion.query.get_or_404(discussion_id)
    
    # Check if user owns this message
    if discussion.user_id != current_user.id:
        return jsonify({"error": "You can only delete your own messages"}), 403
    
    # Delete the message
    db.session.delete(discussion)
    db.session.commit()
    
    return jsonify({"message": "Discussion deleted successfully"})

# Chapter Materials Routes
@main.route("/teacher/<int:teacher_id>/chapter/<int:chapter_id>/materials")
@login_required
def teacher_chapter_materials(teacher_id, chapter_id):
    """Teacher view of chapter materials"""
    # Check if teacher has access to this chapter's subject
    chapter = Chapter.query.get_or_404(chapter_id)
    teacher_subject = TeacherSubject.query.filter_by(
        teacher_user_id=teacher_id, 
        subject_id=chapter.subject_id
    ).first()
    
    if not teacher_subject:
        return redirect(url_for("main.teacher_dashboard", id=teacher_id, name=current_user.full_name))
    
    # Get materials for this chapter
    materials = ChapterMaterial.query.filter_by(chapter_id=chapter_id).order_by(ChapterMaterial.created_at.desc()).all()
    
    return render_template("teacher_chapter_materials.html", 
                         teacher=current_user, chapter=chapter, materials=materials,
                         current_date=datetime.now().strftime("%d %B, %Y"))

@main.route("/teacher/<int:teacher_id>/chapter/<int:chapter_id>/materials", methods=["POST"])
@login_required
def teacher_add_material(teacher_id, chapter_id):
    """Teacher adds material to chapter"""
    # Check if teacher has access to this chapter's subject
    chapter = Chapter.query.get_or_404(chapter_id)
    teacher_subject = TeacherSubject.query.filter_by(
        teacher_user_id=teacher_id, 
        subject_id=chapter.subject_id
    ).first()
    
    if not teacher_subject:
        return redirect(url_for("main.teacher_dashboard", id=teacher_id, name=current_user.full_name))
    
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    material_type = request.form.get("material_type", "text")
    external_url = request.form.get("external_url", "").strip()
    
    if not title:
        return redirect(url_for("main.teacher_chapter_materials", teacher_id=teacher_id, chapter_id=chapter_id))
    
    # Handle file upload
    file_path = None
    file_type = None
    file_size = None
    
    if material_type == "file" and "file" in request.files:
        file = request.files["file"]
        if file and file.filename:
            # Create uploads directory if it doesn't exist
            import os
            upload_dir = os.path.join(current_app.root_path, "static", "uploads", "materials")
            os.makedirs(upload_dir, exist_ok=True)
            
            # Secure filename and save
            filename = secure_filename(file.filename)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_")
            filename = timestamp + filename
            # Always store forward-slash paths to avoid Windows backslash issues in URLs
            file_path = f"uploads/materials/{filename}"
            file.save(os.path.join(current_app.root_path, "static", file_path))
            
            # Get file info
            file_type = filename.split('.')[-1].lower() if '.' in filename else 'unknown'
            file_size = os.path.getsize(os.path.join(current_app.root_path, "static", file_path))
    
    # Create material
    material = ChapterMaterial(
        chapter_id=chapter_id,
        title=title,
        description=description,
        file_path=file_path,
        file_type=file_type,
        file_size=file_size,
        external_url=external_url if material_type == "link" else None,
        material_type=material_type
    )
    
    db.session.add(material)
    db.session.commit()
    
    return redirect(url_for("main.teacher_chapter_materials", teacher_id=teacher_id, chapter_id=chapter_id))

@main.route("/teacher/<int:teacher_id>/material/<int:material_id>/delete", methods=["POST"])
@login_required
def teacher_delete_material(teacher_id, material_id):
    """Teacher deletes material"""
    material = ChapterMaterial.query.get_or_404(material_id)
    chapter = Chapter.query.get(material.chapter_id)
    
    # Check if teacher has access to this chapter's subject
    teacher_subject = TeacherSubject.query.filter_by(
        teacher_user_id=teacher_id, 
        subject_id=chapter.subject_id
    ).first()
    
    if not teacher_subject:
        return redirect(url_for("main.teacher_dashboard", id=teacher_id, name=current_user.full_name))
    
    # Delete file if it exists
    if material.file_path:
        import os
        file_full_path = os.path.join(current_app.root_path, "static", material.file_path)
        if os.path.exists(file_full_path):
            os.remove(file_full_path)
    
    # Delete material from database
    db.session.delete(material)
    db.session.commit()
    
    return redirect(url_for("main.teacher_chapter_materials", teacher_id=teacher_id, chapter_id=material.chapter_id))

@main.route("/user/<int:user_id>/chapter/<int:chapter_id>/materials")
@login_required
def user_chapter_materials(user_id, chapter_id):
    """User view of chapter materials"""
    # Get user and chapter
    user = User_Info.query.get_or_404(user_id)
    chapter = Chapter.query.get_or_404(chapter_id)
    
    # Check if user is enrolled in this subject
    enrollment = UserEnrollment.query.filter_by(
        user_id=user_id, 
        subject_id=chapter.subject_id, 
        is_active=True
    ).first()
    
    if not enrollment:
        return redirect(url_for("main.user_dashboard", id=user_id, name=user.full_name))
    
    # Get materials for this chapter
    materials = ChapterMaterial.query.filter_by(chapter_id=chapter_id).order_by(ChapterMaterial.created_at.desc()).all()
    
    return render_template("user_chapter_materials.html", 
                         user=user, chapter=chapter, materials=materials,
                         current_date=datetime.now().strftime("%d %B, %Y"))

@main.route("/static/uploads/materials/<path:filename>")
def uploaded_file(filename):
    """Serve uploaded files safely from the materials directory.

    Accepts either a bare filename or a path that may contain Windows backslashes
    or an 'uploads/materials/' prefix; normalizes before serving.
    """
    # Normalize incoming path: convert backslashes to slashes and strip directories
    safe_name = filename.replace("\\", "/").split("/")[-1]
    materials_dir = os.path.join(current_app.root_path, "static", "uploads", "materials")
    return send_from_directory(materials_dir, safe_name, as_attachment=True)

# Branch Selection Routes
@main.route("/user/<int:user_id>/branch-selection")
@login_required
def branch_selection(user_id):
    """Branch selection page for students"""
    # Get user
    user = User_Info.query.get_or_404(user_id)
    
    # Only allow students to access this page
    if user.role != 1:
        return redirect(url_for("main.signin"))
    
    # Get all available branches
    branches = Branch.query.all()
    
    return render_template("branch_selection.html", 
                         user=user, branches=branches,
                         current_date=datetime.now().strftime("%d %B, %Y"))

@main.route("/user/<int:user_id>/select-branch", methods=["POST"])
@login_required
def select_branch(user_id):
    """Student selects their engineering branch"""
    # Get user
    user = User_Info.query.get_or_404(user_id)
    
    # Only allow students to access this page
    if user.role != 1:
        return redirect(url_for("main.signin"))
    
    # Get selected branch
    branch_id = request.form.get("branch_id")
    
    if not branch_id:
        return redirect(url_for("main.branch_selection", user_id=user_id))
    
    # Update user's branch
    user.branch_id = int(branch_id)
    db.session.commit()
    
    return redirect(url_for("main.user_dashboard", id=user_id, name=user.full_name))

@main.route("/admin/branches")
@login_required
def admin_branches():
    """Admin management of branches"""
    # Only admin can access
    if not current_user or current_user.role != 0:
        return redirect(url_for("main.signin"))
    
    branches = Branch.query.all()
    subjects = Subject.query.all()
    
    return render_template("admin_branches.html",
                         branches=branches, subjects=subjects,
                         current_date=datetime.now().strftime("%d %B, %Y"),
                         name=current_user.full_name if current_user else "Admin")

@main.route("/admin/branches", methods=["POST"])
@login_required
def admin_add_branch():
    """Admin adds a new branch"""
    # Only admin can access
    if not current_user or current_user.role != 0:
        return redirect(url_for("main.signin"))
    
    name = request.form.get("name", "").strip()
    short_name = request.form.get("short_name", "").strip()
    description = request.form.get("description", "").strip()
    icon = request.form.get("icon", "").strip()
    color = request.form.get("color", "").strip()
    
    if not name or not short_name:
        return redirect(url_for("main.admin_branches"))
    
    # Create new branch
    branch = Branch(
        name=name,
        short_name=short_name,
        description=description,
        icon=icon,
        color=color
    )
    
    db.session.add(branch)
    db.session.commit()
    
    return redirect(url_for("main.admin_branches"))

@main.route("/admin/branches/<int:branch_id>/edit", methods=["POST"])
@login_required
def admin_edit_branch(branch_id):
    """Admin edits a branch"""
    # Only admin can access
    if not current_user or current_user.role != 0:
        return redirect(url_for("main.signin"))
    
    branch = Branch.query.get_or_404(branch_id)
    
    name = request.form.get("name", "").strip()
    short_name = request.form.get("short_name", "").strip()
    description = request.form.get("description", "").strip()
    icon = request.form.get("icon", "").strip()
    color = request.form.get("color", "").strip()
    
    if not name or not short_name:
        return redirect(url_for("main.admin_branches"))
    
    branch.name = name
    branch.short_name = short_name
    branch.description = description
    branch.icon = icon
    branch.color = color
    
    db.session.commit()
    
    return redirect(url_for("main.admin_branches"))

@main.route("/admin/branches/<int:branch_id>/delete", methods=["POST"])
@login_required
def admin_delete_branch(branch_id):
    """Admin deletes a branch"""
    # Only admin can access
    if not current_user or current_user.role != 0:
        return redirect(url_for("main.signin"))
    
    branch = Branch.query.get_or_404(branch_id)
    
    # Check if branch has any students or subjects
    students_count = len(branch.students)
    subjects_count = len(branch.subjects)
    
    if students_count > 0 or subjects_count > 0:
        # Don't delete if there are students or subjects
        return redirect(url_for("main.admin_branches"))
    
    db.session.delete(branch)
    db.session.commit()
    
    return redirect(url_for("main.admin_branches"))

# Branch-specific Dashboard Routes
@main.route("/admin/branch/<int:branch_id>/dashboard")
@login_required
def admin_branch_dashboard(branch_id):
    """Admin dashboard for a specific branch"""
    # Only admin can access
    if not current_user or current_user.role != 0:
        return redirect(url_for("main.signin"))
    
    branch = Branch.query.get_or_404(branch_id)
    
    # Get branch-specific data
    students = User_Info.query.filter_by(branch_id=branch_id, role=1).all()
    subjects = Subject.query.filter_by(branch_id=branch_id).all()
    teachers = User_Info.query.filter_by(role=2).all()
    
    # Get enrollment statistics
    total_enrollments = db.session.query(UserEnrollment).join(Subject, UserEnrollment.subject_id == Subject.id).filter(Subject.branch_id == branch_id).count()
    active_enrollments = db.session.query(UserEnrollment).join(Subject, UserEnrollment.subject_id == Subject.id).filter(
        Subject.branch_id == branch_id, 
        UserEnrollment.is_active == True
    ).count()
    
    # Get recent activity
    recent_scores = db.session.query(Score).join(Quiz, Score.quiz_id == Quiz.id).join(Chapter, Quiz.chapter_id == Chapter.id).join(Subject, Chapter.subject_id == Subject.id).filter(
        Subject.branch_id == branch_id
    ).order_by(Score.time_stamp_of_attempt.desc()).limit(10).all()
    
    return render_template("admin_branch_dashboard.html", 
                         branch=branch, students=students, subjects=subjects, teachers=teachers,
                         total_enrollments=total_enrollments, active_enrollments=active_enrollments,
                         recent_scores=recent_scores,
                         current_date=datetime.now().strftime("%d %B, %Y"))

@main.route("/admin/branch/<int:branch_id>/students")
@login_required
def admin_branch_students(branch_id):
    """Admin view of students in a specific branch"""
    # Only admin can access
    if not current_user or current_user.role != 0:
        return redirect(url_for("main.signin"))
    
    branch = Branch.query.get_or_404(branch_id)
    students = User_Info.query.filter_by(branch_id=branch_id, role=1).all()
    
    return render_template("admin_branch_students.html", 
                         branch=branch, students=students,
                         current_date=datetime.now().strftime("%d %B, %Y"))

@main.route("/admin/branch/<int:branch_id>/subjects")
@login_required
def admin_branch_subjects(branch_id):
    """Admin view of subjects in a specific branch"""
    # Only admin can access
    if not current_user or current_user.role != 0:
        return redirect(url_for("main.signin"))
    
    branch = Branch.query.get_or_404(branch_id)
    subjects = Subject.query.filter_by(branch_id=branch_id).all()
    
    return render_template("admin_branch_subjects.html", 
                         branch=branch, subjects=subjects,
                         current_date=datetime.now().strftime("%d %B, %Y"))

@main.route("/admin/subjects/<int:subject_id>/assign-branch", methods=["POST"])
@login_required
def admin_assign_subject_to_branch(subject_id):
    """Admin assigns subject to a branch"""
    # Only admin can access
    if not current_user or current_user.role != 0:
        return redirect(url_for("main.signin"))
    
    subject = Subject.query.get_or_404(subject_id)
    branch_id = request.form.get("branch_id")
    is_core = request.form.get("is_core") == "on"
    
    if branch_id:
        subject.branch_id = int(branch_id)
        subject.is_core = is_core
        db.session.commit()
    
    return redirect(url_for("main.admin_branches"))

# Subject Management Routes
@main.route("/admin/branches/<int:branch_id>/add-subject", methods=["POST"])
@login_required
def admin_add_subject_to_branch(branch_id):
    """Admin adds a new subject to a specific branch"""
    # Only admin can access
    if not current_user or current_user.role != 0:
        return redirect(url_for("main.signin"))
    
    branch = Branch.query.get_or_404(branch_id)
    
    name = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip()
    is_core = request.form.get("is_core") == "on"
    
    if not name:
        return redirect(url_for("main.admin_branches"))
    
    # Create new subject
    subject = Subject(
        name=name,
        description=description,
        branch_id=branch_id,
        is_core=is_core
    )
    
    db.session.add(subject)
    db.session.commit()
    
    return redirect(url_for("main.admin_branches"))

@main.route("/admin/subjects/<int:subject_id>/edit", methods=["POST"])
@login_required
def admin_edit_subject(subject_id):
    """Admin edits a subject"""
    # Only admin can access
    if not current_user or current_user.role != 0:
        return redirect(url_for("main.signin"))
    
    subject = Subject.query.get_or_404(subject_id)
    
    name = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip()
    is_core = request.form.get("is_core") == "on"
    branch_id = request.form.get("branch_id")
    
    if not name:
        return redirect(url_for("main.admin_branches"))
    
    subject.name = name
    subject.description = description
    subject.is_core = is_core
    
    if branch_id:
        subject.branch_id = int(branch_id)
    
    db.session.commit()
    
    return redirect(url_for("main.admin_branches"))

@main.route("/admin/subjects/<int:subject_id>/delete", methods=["POST"])
@login_required
def admin_delete_subject(subject_id):
    """Admin deletes a subject"""
    # Only admin can access
    if not current_user or current_user.role != 0:
        return redirect(url_for("main.signin"))
    
    subject = Subject.query.get_or_404(subject_id)
    
    # Check if subject has any enrollments or scores
    enrollments = UserEnrollment.query.filter_by(subject_id=subject_id).count()
    scores = Score.query.join(Quiz).filter(Quiz.subject_id == subject_id).count()
    
    if enrollments > 0 or scores > 0:
        # Don't delete if there are enrollments or scores
        return redirect(url_for("main.admin_branches"))
    
    db.session.delete(subject)
    db.session.commit()
    
    return redirect(url_for("main.admin_branches"))

# Admin Chapter Management Routes
@main.route("/admin/chapters")
@login_required
def admin_chapter_management():
    """Admin chapter management across all branches"""
    # Only admin can access
    if not current_user or current_user.role != 0:
        return redirect(url_for("main.signin"))
    
    # Get all chapters with their subjects and branches
    chapters = Chapter.query.join(Subject).join(Branch).all()
    subjects = Subject.query.all()
    branches = Branch.query.all()
    
    return render_template("admin_chapter_management.html", 
                         chapters=chapters, subjects=subjects, branches=branches,
                         current_date=datetime.now().strftime("%d %B, %Y"),
                         name=current_user.full_name if current_user else "Admin")

@main.route("/admin/chapters", methods=["POST"])
@login_required
def admin_add_chapter():
    """Admin adds a new chapter"""
    # Only admin can access
    if not current_user or current_user.role != 0:
        return redirect(url_for("main.signin"))
    
    name = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip()
    subject_id = request.form.get("subject_id")
    
    if not name or not subject_id:
        return redirect(url_for("main.admin_chapter_management"))
    
    # Create new chapter
    chapter = Chapter(
        name=name,
        description=description,
        subject_id=int(subject_id)
    )
    
    db.session.add(chapter)
    db.session.commit()
    
    return redirect(url_for("main.admin_chapter_management"))

@main.route("/admin/chapters/<int:chapter_id>/edit", methods=["POST"])
@login_required
def admin_edit_chapter(chapter_id):
    """Admin edits a chapter"""
    # Only admin can access
    if not current_user or current_user.role != 0:
        return redirect(url_for("main.signin"))
    
    chapter = Chapter.query.get_or_404(chapter_id)
    
    name = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip()
    subject_id = request.form.get("subject_id")
    
    if not name:
        return redirect(url_for("main.admin_chapter_management"))
    
    chapter.name = name
    chapter.description = description
    
    if subject_id:
        chapter.subject_id = int(subject_id)
    
    db.session.commit()
    
    return redirect(url_for("main.admin_chapter_management"))

@main.route("/admin/chapters/<int:chapter_id>/delete", methods=["POST"])
@login_required
def admin_delete_chapter(chapter_id):
    """Admin deletes a chapter"""
    # Only admin can access
    if not current_user or current_user.role != 0:
        return redirect(url_for("main.signin"))
    
    chapter = Chapter.query.get_or_404(chapter_id)
    
    # Check if chapter has any quizzes
    quizzes_count = Quiz.query.filter_by(chapter_id=chapter_id).count()
    
    if quizzes_count > 0:
        # Don't delete if there are quizzes
        return redirect(url_for("main.admin_chapter_management"))
    
    db.session.delete(chapter)
    db.session.commit()
    
    return redirect(url_for("main.admin_chapter_management"))

@main.route("/admin/branches/<int:branch_id>/chapters")
@login_required
def admin_branch_chapters(branch_id):
    """Admin view of chapters in a specific branch"""
    # Only admin can access
    if not current_user or current_user.role != 0:
        return redirect(url_for("main.signin"))
    
    branch = Branch.query.get_or_404(branch_id)
    chapters = Chapter.query.join(Subject).filter(Subject.branch_id == branch_id).all()
    subjects = Subject.query.filter_by(branch_id=branch_id).all()
    
    return render_template("admin_branch_chapters.html", 
                         branch=branch, chapters=chapters, subjects=subjects,
                         current_date=datetime.now().strftime("%d %B, %Y"))

@main.route("/admin/dashboard")
@login_required
def admin_dashboard_new():
    """Admin dashboard"""
    # Only admin can access
    if not current_user or current_user.role != 0:
        return redirect(url_for("main.signin"))
    
    # Get all branches
    branches = Branch.query.all()
    
    # Get selected branch from session
    selected_branch_id = session.get('admin_selected_branch')
    selected_branch = None
    if selected_branch_id:
        selected_branch = Branch.query.get(selected_branch_id)
    
    # Get subjects and users based on selected branch
    if selected_branch:
        subjects = Subject.query.filter_by(branch_id=selected_branch_id).all()
        users = User_Info.query.filter_by(branch_id=selected_branch_id, role=1).all()
    else:
        subjects = Subject.query.all()
        users = User_Info.query.filter_by(role=1).all()
    
    # Get recent activity
    recent_scores = Score.query.order_by(Score.time_stamp_of_attempt.desc()).limit(10).all()
    
    return render_template("admin_dashboard.html",
                         branches=branches,
                         selected_branch=selected_branch,
                         subjects=subjects,
                         users=users,
                         recent_scores=recent_scores,
                         current_date=datetime.now().strftime("%d %B, %Y"),
                         name=current_user.full_name if current_user else "Admin")

@main.route("/admin/branches-new")
@login_required
def admin_branches_new():
    """Admin branch management"""
    # Only admin can access
    if not current_user or current_user.role != 0:
        return redirect(url_for("main.signin"))
    
    branches = Branch.query.all()
    subjects = Subject.query.all()
    
    return render_template("admin_branches.html",
                         branches=branches, subjects=subjects,
                         current_date=datetime.now().strftime("%d %B, %Y"),
                         name=current_user.full_name if current_user else "Admin")


