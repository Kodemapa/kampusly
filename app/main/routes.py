"""
Main Blueprint Routes - Dashboard and home pages
"""

from flask import render_template, request, jsonify, redirect, url_for
from flask_login import login_required, current_user
from app.main import bp
from app.models import Subject, Topic, Question

@bp.route('/')
def index():
    """Landing page - redirects based on authentication status"""
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    else:
        return redirect(url_for('auth.login'))

@bp.route('/dashboard')
@login_required
def dashboard():
    """Main dashboard for authenticated users"""
    # Get some statistics
    total_subjects = Subject.query.count()
    total_topics = Topic.query.count()
    total_questions = Question.query.count()
    
    # Get subjects by class
    class_xi_subjects = Subject.query.filter_by(class_level='XI').limit(6).all()
    class_xii_subjects = Subject.query.filter_by(class_level='XII').limit(6).all()
    
    return render_template('main/dashboard.html',
                         total_subjects=total_subjects,
                         total_topics=total_topics,
                         total_questions=total_questions,
                         class_xi_subjects=class_xi_subjects,
                         class_xii_subjects=class_xii_subjects)

@bp.route('/subjects/<class_level>')
def subjects(class_level):
    """Show subjects for a specific class"""
    if class_level not in ['XI', 'XII']:
        return "Invalid class level", 404
    
    subjects = Subject.query.filter_by(class_level=class_level).all()
    return render_template('main/subjects.html', 
                         subjects=subjects, 
                         class_level=class_level)

@bp.route('/topics/<int:subject_id>')
def topics(subject_id):
    """Show topics for a specific subject"""
    subject = Subject.query.get_or_404(subject_id)
    topics = Topic.query.filter_by(subject_id=subject_id).all()
    
    # Add question count for each topic
    for topic in topics:
        topic.question_count = Question.query.filter_by(topic_id=topic.id).count()
    
    return render_template('main/topics.html', 
                         subject=subject, 
                         topics=topics)

@bp.route('/about')
def about():
    """About page"""
    return render_template('main/about.html')

@bp.route('/help')
def help():
    """Help and FAQ page"""
    return render_template('main/help.html')
