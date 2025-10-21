from flask import Blueprint, render_template, redirect, url_for, request, flash, jsonify
from flask_login import login_required, current_user
from backend.models import db, User_Info, Assignment, AssignmentSubmission, Notification, UserEnrollment, TeacherSubject
from datetime import datetime, timedelta

# Create blueprint for notification routes
notification_bp = Blueprint('notifications', __name__)

# Notification and Assignment Management Routes

@notification_bp.route("/teacher/<int:teacher_id>/assignments")
@login_required
def teacher_assignments(teacher_id):
    """Teacher view of all assignments"""
    teacher = User_Info.query.get_or_404(teacher_id)
    
    # Check if current user is the teacher
    if current_user.id != teacher_id or current_user.role != 2:
        return redirect(url_for("main.signin"))
    
    # Get assignments created by this teacher
    assignments = Assignment.query.filter_by(teacher_id=teacher_id).order_by(Assignment.deadline.asc()).all()
    
    # Get upcoming deadlines (next 7 days)
    upcoming_deadlines = Assignment.query.filter(
        Assignment.teacher_id == teacher_id,
        Assignment.deadline >= datetime.now(),
        Assignment.deadline <= datetime.now() + timedelta(days=7),
        Assignment.is_active == True
    ).order_by(Assignment.deadline.asc()).all()
    
    return render_template("teacher_assignments.html",
                         teacher=teacher,
                         assignments=assignments,
                         upcoming_deadlines=upcoming_deadlines,
                         current_date=datetime.now().strftime("%d %B, %Y"))

@notification_bp.route("/teacher/<int:teacher_id>/assignments/new", methods=["GET", "POST"])
@login_required
def teacher_create_assignment(teacher_id):
    """Teacher creates new assignment"""
    teacher = User_Info.query.get_or_404(teacher_id)
    
    # Check if current user is the teacher
    if current_user.id != teacher_id or current_user.role != 2:
        return redirect(url_for("main.signin"))
    
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        subject_id = request.form.get("subject_id")
        chapter_id = request.form.get("chapter_id") or None
        deadline_str = request.form.get("deadline")
        max_points = request.form.get("max_points", 100)
        assignment_type = request.form.get("assignment_type", "homework")
        instructions = request.form.get("instructions", "").strip()
        
        if not title or not subject_id or not deadline_str:
            flash("Please fill in all required fields.", "error")
            return redirect(url_for("notifications.teacher_create_assignment", teacher_id=teacher_id))
        
        try:
            deadline = datetime.strptime(deadline_str, "%Y-%m-%dT%H:%M")
        except ValueError:
            flash("Invalid deadline format.", "error")
            return redirect(url_for("notifications.teacher_create_assignment", teacher_id=teacher_id))
        
        # Create assignment
        assignment = Assignment(
            title=title,
            description=description,
            subject_id=int(subject_id),
            chapter_id=int(chapter_id) if chapter_id else None,
            teacher_id=teacher_id,
            deadline=deadline,
            max_points=int(max_points),
            assignment_type=assignment_type,
            instructions=instructions
        )
        
        db.session.add(assignment)
        db.session.commit()
        
        # Create notifications for enrolled students
        enrolled_students = UserEnrollment.query.filter_by(
            subject_id=int(subject_id),
            is_active=True
        ).all()
        
        for enrollment in enrolled_students:
            notification = Notification(
                user_id=enrollment.user_id,
                title=f"New Assignment: {title}",
                message=f"A new {assignment_type} has been assigned. Deadline: {deadline.strftime('%B %d, %Y at %I:%M %p')}",
                notification_type="assignment",
                related_id=assignment.id,
                related_type="assignment",
                priority="high" if deadline <= datetime.now() + timedelta(days=3) else "normal"
            )
            db.session.add(notification)
        
        db.session.commit()
        flash("Assignment created successfully!", "success")
        return redirect(url_for("notifications.teacher_assignments", teacher_id=teacher_id))
    
    # Get subjects taught by this teacher
    teacher_subjects = TeacherSubject.query.filter_by(teacher_user_id=teacher_id).all()
    subjects = [ts.subject for ts in teacher_subjects]
    
    return render_template("teacher_create_assignment.html",
                         teacher=teacher,
                         subjects=subjects,
                         current_date=datetime.now().strftime("%d %B, %Y"))

@notification_bp.route("/user/<int:user_id>/assignments")
@login_required
def user_assignments(user_id):
    """Student view of assignments"""
    user = User_Info.query.get_or_404(user_id)
    
    # Check if current user is the student
    if current_user.id != user_id or current_user.role != 1:
        return redirect(url_for("main.signin"))
    
    # Get enrolled subjects
    enrollments = UserEnrollment.query.filter_by(user_id=user_id, is_active=True).all()
    subject_ids = [e.subject_id for e in enrollments]
    
    # Get assignments for enrolled subjects
    assignments = Assignment.query.filter(
        Assignment.subject_id.in_(subject_ids),
        Assignment.is_active == True
    ).order_by(Assignment.deadline.asc()).all()
    
    # Get upcoming deadlines (next 7 days)
    upcoming_deadlines = Assignment.query.filter(
        Assignment.subject_id.in_(subject_ids),
        Assignment.deadline >= datetime.now(),
        Assignment.deadline <= datetime.now() + timedelta(days=7),
        Assignment.is_active == True
    ).order_by(Assignment.deadline.asc()).all()
    
    # Get notifications
    notifications = Notification.query.filter_by(
        user_id=user_id,
        is_read=False
    ).order_by(Notification.created_at.desc()).limit(10).all()
    
    return render_template("user_assignments.html",
                         user=user,
                         assignments=assignments,
                         upcoming_deadlines=upcoming_deadlines,
                         notifications=notifications,
                         current_date=datetime.now().strftime("%d %B, %Y"))

@notification_bp.route("/api/notifications/<int:user_id>")
@login_required
def api_user_notifications(user_id):
    """API endpoint to get user notifications"""
    if current_user.id != user_id:
        return jsonify({"error": "Unauthorized"}), 403
    
    notifications = Notification.query.filter_by(
        user_id=user_id,
        is_read=False
    ).order_by(Notification.created_at.desc()).limit(20).all()
    
    return jsonify([n.to_dict() for n in notifications])

@notification_bp.route("/api/notifications/<int:notification_id>/read", methods=["POST"])
@login_required
def api_mark_notification_read(notification_id):
    """Mark notification as read"""
    notification = Notification.query.get_or_404(notification_id)
    
    if notification.user_id != current_user.id:
        return jsonify({"error": "Unauthorized"}), 403
    
    notification.is_read = True
    db.session.commit()
    
    return jsonify({"success": True})

@notification_bp.route("/api/assignments/<int:assignment_id>/submit", methods=["POST"])
@login_required
def api_submit_assignment(assignment_id):
    """Submit assignment"""
    assignment = Assignment.query.get_or_404(assignment_id)
    
    # Check if user is enrolled in the subject
    enrollment = UserEnrollment.query.filter_by(
        user_id=current_user.id,
        subject_id=assignment.subject_id,
        is_active=True
    ).first()
    
    if not enrollment:
        return jsonify({"error": "Not enrolled in this subject"}), 403
    
    # Check if already submitted
    existing_submission = AssignmentSubmission.query.filter_by(
        assignment_id=assignment_id,
        student_id=current_user.id
    ).first()
    
    if existing_submission:
        return jsonify({"error": "Already submitted"}), 400
    
    data = request.get_json()
    submission_content = data.get("content", "").strip()
    
    if not submission_content:
        return jsonify({"error": "Submission content required"}), 400
    
    # Check if submission is late
    is_late = datetime.now() > assignment.deadline
    
    submission = AssignmentSubmission(
        assignment_id=assignment_id,
        student_id=current_user.id,
        submission_content=submission_content,
        submitted_at=datetime.now(),
        is_late=is_late
    )
    
    db.session.add(submission)
    db.session.commit()
    
    return jsonify({"success": True, "submission_id": submission.id})

@notification_bp.route("/teacher/<int:teacher_id>/assignments/<int:assignment_id>/submissions")
@login_required
def teacher_assignment_submissions(teacher_id, assignment_id):
    """Teacher view of assignment submissions"""
    teacher = User_Info.query.get_or_404(teacher_id)
    assignment = Assignment.query.get_or_404(assignment_id)
    
    # Check if current user is the teacher
    if current_user.id != teacher_id or current_user.role != 2:
        return redirect(url_for("main.signin"))
    
    # Check if assignment belongs to teacher
    if assignment.teacher_id != teacher_id:
        return redirect(url_for("main.signin"))
    
    # Get submissions
    submissions = AssignmentSubmission.query.filter_by(
        assignment_id=assignment_id
    ).order_by(AssignmentSubmission.submitted_at.desc()).all()
    
    return render_template("teacher_assignment_submissions.html",
                         teacher=teacher,
                         assignment=assignment,
                         submissions=submissions,
                         current_date=datetime.now().strftime("%d %B, %Y"))
