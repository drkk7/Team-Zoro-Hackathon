from celery import shared_task
from .models import User_Info, Score, Quiz
from datetime import datetime, timedelta
from flask import current_app
from flask_mail import Message

@shared_task
def daily_reminder_task():
    """Send daily reminders to users who haven't taken quizzes today"""
    from app import mail  # Import here to avoid circular import
    
    users = User_Info.query.filter_by(role=1).all()  # Only regular users
    for user in users:
        # Check if user hasn't taken a quiz today
        today = datetime.now().date()
        recent_score = Score.query.filter(
            Score.user_id == user.id,
            Score.time_stamp_of_attempt >= today
        ).first()
        
        if not recent_score:
            try:
                msg = Message(
                    'Daily Quiz Reminder',
                    sender='your-email@gmail.com',
                    recipients=[user.email]
                )
                msg.body = f"Hello {user.full_name}! Don't forget to take your daily quiz to improve your knowledge."
                mail.send(msg)
                print(f"Daily reminder sent to {user.email}")
            except Exception as e:
                print(f"Error sending daily reminder to {user.email}: {e}")
    
    return f"Daily reminders sent to {len(users)} users"

@shared_task
def monthly_report_task():
    """Generate and send monthly reports to all users"""
    from app import mail  # Import here to avoid circular import
    
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
            
            try:
                msg = Message(
                    'Monthly Activity Report',
                    sender='your-email@gmail.com',
                    recipients=[user.email]
                )
                msg.html = f"""
                <h2>Monthly Activity Report for {user.full_name}</h2>
                <p>Quizzes taken: {len(scores)}</p>
                <p>Average score: {round(average_score, 2)}%</p>
                <p>Total score: {total_score}</p>
                <p>Keep up the great work!</p>
                """
                mail.send(msg)
                print(f"Monthly report sent to {user.email}")
            except Exception as e:
                print(f"Error sending monthly report to {user.email}: {e}")
    
    return f"Monthly reports sent to {len(users)} users"

@shared_task
def export_csv_task(user_id):
    """Export user quiz data as CSV"""
    try:
        user = User_Info.query.get(user_id)
        if not user:
            return "User not found"
        
        scores = Score.query.filter_by(user_id=user_id).all()
        
        # Generate CSV content
        csv_content = "quiz_id,chapter_id,date_of_quiz,score,remarks\n"
        for score in scores:
            quiz = Quiz.query.get(score.quiz_id)
            if quiz:
                csv_content += f"{score.quiz_id},{quiz.chapter_id},{quiz.date_of_quiz},{score.total_scored},{quiz.remarks or ''}\n"
        
        # Save to file
        filename = f"quiz_data_user_{user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        with open(filename, 'w') as f:
            f.write(csv_content)
        
        print(f"CSV exported for user {user_id}: {filename}")
        return filename
        
    except Exception as e:
        print(f"Error exporting CSV for user {user_id}: {e}")
        return None

@shared_task
def send_daily_reminder(user_email, user_name):
    """Send daily reminder to specific user"""
    from app import mail  # Import here to avoid circular import
    
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

@shared_task
def send_monthly_report(user_email, user_name, report_data):
    """Send monthly activity report to specific user"""
    from app import mail  # Import here to avoid circular import
    
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