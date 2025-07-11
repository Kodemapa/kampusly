"""
Exam Blueprint Routes - Exam taking and management
"""

from flask import render_template, request, jsonify, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from app.exam import bp
from app.models import db, Subject, Topic, Question, Exam, ExamSession
import random
from datetime import datetime
import time
from sqlalchemy.orm import sessionmaker

@bp.route('/dashboard')
@login_required
def dashboard():
    """Exam dashboard showing user's progress and available exams"""
    recent_sessions = ExamSession.query.filter_by(user_id=current_user.id)\
                                      .order_by(ExamSession.start_time.desc())\
                                      .limit(5).all()
    
    total_sessions = ExamSession.query.filter_by(user_id=current_user.id).count()
    avg_score = db.session.query(db.func.avg(ExamSession.percentage))\
                         .filter_by(user_id=current_user.id).scalar() or 0
    
    return render_template('exam/dashboard.html',
                         recent_sessions=recent_sessions,
                         total_sessions=total_sessions,
                         avg_score=round(avg_score, 1))

@bp.route('/practice')
def practice():
    """Practice page showing all subjects and topics"""
    subjects = Subject.query.all()
    return render_template('exam/practice.html', subjects=subjects)

@bp.route('/practice/topic/<int:topic_id>')
def practice_topic(topic_id):
    """Practice questions from a specific topic"""
    topic = Topic.query.get_or_404(topic_id)
    return render_template('exam/practice_topic.html', topic=topic)

@bp.route('/test/topic/<int:topic_id>')
@login_required
def topic_test(topic_id):
    """Create a timed test for a specific topic"""
    topic = Topic.query.get_or_404(topic_id)
    return render_template('exam/topic_test.html', topic=topic)

@bp.route('/test/subject/<int:subject_id>')
@login_required
def subject_test(subject_id):
    """Create a comprehensive test for a subject"""
    subject = Subject.query.get_or_404(subject_id)
    return render_template('exam/subject_test.html', subject=subject)

@bp.route('/test/custom')
@login_required
def custom_test():
    """Create a custom test"""
    subjects = Subject.query.all()
    return render_template('exam/custom_test.html', subjects=subjects)

@bp.route('/results')
@login_required
def results():
    """Show user's exam results and analytics"""
    from sqlalchemy import func
    
    # Get all user sessions
    try:
        # Force database query to refresh completely
        db.session.remove()
        
        # Get a fresh session count first to verify data freshness
        fresh_count = ExamSession.query.filter_by(user_id=current_user.id).count()
        current_app.logger.info(f"Fresh session count for user {current_user.id}: {fresh_count}")
        
        # Small delay to ensure any concurrent transactions complete
        time.sleep(0.5)
        
        # Create a new session to ensure fresh data
        Session = sessionmaker(bind=db.engine)
        fresh_session = Session()
        
        # Get all sessions for the current user, ordered by most recent first
        sessions = fresh_session.query(ExamSession).filter_by(user_id=current_user.id)\
                                .order_by(ExamSession.start_time.desc()).all()
        
        # Calculate analytics
        total_sessions = len(sessions)
        
        # Calculate average score safely
        if total_sessions > 0:
            valid_scores = [session.percentage for session in sessions if session.percentage is not None]
            avg_score = sum(valid_scores) / len(valid_scores) if valid_scores else 0
        else:
            avg_score = 0
        
        # Print debug info
        current_app.logger.info(f"User ID: {current_user.id}")
        current_app.logger.info(f"Total sessions: {total_sessions}")
        current_app.logger.info(f"Average score: {avg_score}")
        if sessions:
            for session in sessions[:3]:  # First 3 sessions
                current_app.logger.info(f"Session {session.id}: {session.percentage}% score, {session.duration_seconds} seconds, Time: {session.start_time}")
        
        # Close the fresh session
        fresh_session.close()
    except Exception as e:
        current_app.logger.error(f"Error retrieving sessions: {str(e)}")
        import traceback
        traceback.print_exc()
        sessions = []
        total_sessions = 0
        avg_score = 0
    
    # Get best and worst performances
    try:
        best_session = max([s for s in sessions if s.percentage is not None], 
                          key=lambda x: x.percentage) if sessions else None
    except (ValueError, AttributeError) as e:
        print(f"Error getting best session: {str(e)}")
        best_session = None
        
    try:
        worst_session = min([s for s in sessions if s.percentage is not None], 
                           key=lambda x: x.percentage) if sessions else None
    except (ValueError, AttributeError) as e:
        print(f"Error getting worst session: {str(e)}")
        worst_session = None
    
    # Calculate subject-wise performance
    try:
        subject_stats = {}
        topic_stats = {}
        difficulty_stats = {'easy': {'total': 0, 'correct': 0}, 
                          'moderate': {'total': 0, 'correct': 0}, 
                          'difficult': {'total': 0, 'correct': 0}}
    except Exception as e:
        print(f"Error initializing stats: {str(e)}")
        subject_stats = {}
        topic_stats = {}
        difficulty_stats = {'easy': {'total': 0, 'correct': 0}, 
                          'moderate': {'total': 0, 'correct': 0}, 
                          'difficult': {'total': 0, 'correct': 0}}
    
    for session in sessions:
        questions_data = session.get_questions_data()
        questions = questions_data.get('questions', [])
        
        for question in questions:
            # Get question details for analysis
            try:
                question_id = question.get('question_id')
                if not question_id:
                    print(f"Warning: Question missing question_id in session {session.id}")
                    continue
                    
                q = Question.query.get(question_id)
                if q and q.topic:
                    # Subject stats
                    subject_name = q.topic.subject.name
                    if subject_name not in subject_stats:
                        subject_stats[subject_name] = {'total': 0, 'correct': 0, 'percentage': 0}
                    
                    subject_stats[subject_name]['total'] += 1
                    if question.get('is_correct'):
                        subject_stats[subject_name]['correct'] += 1
                    
                    # Topic stats
                    topic_name = q.topic.name
                    if topic_name not in topic_stats:
                        topic_stats[topic_name] = {'total': 0, 'correct': 0, 'percentage': 0, 'subject': subject_name}
                    
                    topic_stats[topic_name]['total'] += 1
                    if question.get('is_correct'):
                        topic_stats[topic_name]['correct'] += 1
                    
                    # Difficulty stats
                    difficulty = q.difficulty_level.lower() if q.difficulty_level else 'moderate'
                    if difficulty in difficulty_stats:
                        difficulty_stats[difficulty]['total'] += 1
                        if question.get('is_correct'):
                            difficulty_stats[difficulty]['correct'] += 1
                elif q:
                    print(f"Warning: Question {q.id} has no topic")
                else:
                    print(f"Warning: Question with ID {question_id} not found")
            except Exception as e:
                print(f"Error processing question in session {session.id}: {str(e)}")
    
    # Calculate percentages
    for subject in subject_stats.values():
        subject['percentage'] = (subject['correct'] / subject['total'] * 100) if subject['total'] > 0 else 0
    
    for topic in topic_stats.values():
        topic['percentage'] = (topic['correct'] / topic['total'] * 100) if topic['total'] > 0 else 0
    
    for difficulty in difficulty_stats.values():
        difficulty['percentage'] = (difficulty['correct'] / difficulty['total'] * 100) if difficulty['total'] > 0 else 0
    
    # Get recent sessions (last 5)
    recent_sessions = sessions[:5] if sessions else []
    
    # Performance trend (last 10 sessions)
    trend_sessions = sessions[:10] if sessions else []
    performance_trend = [{'date': session.start_time.strftime('%m/%d'), 
                         'percentage': session.percentage} for session in reversed(trend_sessions)]
    
    # Use results.html template for all cases - we've improved the AJAX refresh functionality
    current_app.logger.info(f"Using results.html template for all cases")
    
    return render_template('exam/results.html', 
                         sessions=sessions,
                         recent_sessions=recent_sessions,
                         total_sessions=total_sessions,
                         avg_score=round(avg_score, 1),
                         best_session=best_session,
                         worst_session=worst_session,
                         subject_stats=subject_stats,
                         topic_stats=topic_stats,
                         difficulty_stats=difficulty_stats,
                         performance_trend=performance_trend)


@bp.route('/results/data', methods=['GET'])
@login_required
def results_data():
    """API endpoint to get user's analytics data for AJAX refresh"""
    from sqlalchemy import func
    
    try:
        current_app.logger.info(f"Results data API called by user {current_user.id}")
        
        # Force database query to refresh completely
        db.session.remove()
        
        # Create a new session to ensure fresh data
        Session = sessionmaker(bind=db.engine)
        fresh_session = Session()
        current_app.logger.info(f"Fresh database session created")
        
        # Get all sessions for the current user, ordered by most recent first
        sessions = fresh_session.query(ExamSession).filter_by(user_id=current_user.id)\
                              .order_by(ExamSession.start_time.desc()).all()
        
        # Calculate analytics
        total_sessions = len(sessions)
        
        # Calculate average score safely
        if total_sessions > 0:
            valid_scores = [session.percentage for session in sessions if session.percentage is not None]
            avg_score = sum(valid_scores) / len(valid_scores) if valid_scores else 0
        else:
            avg_score = 0
            
        # Get best session
        best_session = None
        if sessions:
            try:
                best_session = max([s for s in sessions if s.percentage is not None], 
                                  key=lambda x: x.percentage)
                best_session = {
                    'id': best_session.id,
                    'percentage': best_session.percentage,
                    'score': float(best_session.score) if best_session.score else 0,
                    'max_score': float(best_session.max_score) if best_session.max_score else 0
                }
                current_app.logger.info(f"Best session found: {best_session}")
            except (ValueError, AttributeError) as e:
                current_app.logger.error(f"Error getting best session: {str(e)}")
                
        # Calculate subject and topic stats
        subject_stats = {}
        topic_stats = {}
        difficulty_stats = {'easy': {'total': 0, 'correct': 0}, 
                          'moderate': {'total': 0, 'correct': 0}, 
                          'difficult': {'total': 0, 'correct': 0}}
        
        # Process each session
        for session in sessions:
            questions_data = session.get_questions_data()
            questions = questions_data.get('questions', [])
            current_app.logger.debug(f"Session {session.id} has {len(questions)} questions")
            
            for question in questions:
                try:
                    question_id = question.get('question_id')
                    if not question_id:
                        continue
                        
                    q = fresh_session.query(Question).get(question_id)
                    if q and q.topic:
                        # Subject stats
                        subject_name = q.topic.subject.name
                        if subject_name not in subject_stats:
                            subject_stats[subject_name] = {'total': 0, 'correct': 0, 'percentage': 0}
                        
                        subject_stats[subject_name]['total'] += 1
                        if question.get('is_correct'):
                            subject_stats[subject_name]['correct'] += 1
                        
                        # Topic stats
                        topic_name = q.topic.name
                        if topic_name not in topic_stats:
                            topic_stats[topic_name] = {'total': 0, 'correct': 0, 'percentage': 0, 'subject': subject_name}
                        
                        topic_stats[topic_name]['total'] += 1
                        if question.get('is_correct'):
                            topic_stats[topic_name]['correct'] += 1
                        
                        # Difficulty stats
                        difficulty = q.difficulty_level.lower() if q.difficulty_level else 'moderate'
                        if difficulty in difficulty_stats:
                            difficulty_stats[difficulty]['total'] += 1
                            if question.get('is_correct'):
                                difficulty_stats[difficulty]['correct'] += 1
                except Exception as e:
                    current_app.logger.error(f"Error processing question in session {session.id}: {str(e)}")
        
        # Calculate percentages
        for subject in subject_stats.values():
            subject['percentage'] = (subject['correct'] / subject['total'] * 100) if subject['total'] > 0 else 0
        
        for topic in topic_stats.values():
            topic['percentage'] = (topic['correct'] / topic['total'] * 100) if topic['total'] > 0 else 0
        
        for difficulty in difficulty_stats.values():
            difficulty['percentage'] = (difficulty['correct'] / difficulty['total'] * 100) if difficulty['total'] > 0 else 0
        
        # Performance trend (last 10 sessions)
        trend_sessions = sessions[:10] if sessions else []
        performance_trend = [{'date': session.start_time.strftime('%m/%d'), 
                             'percentage': session.percentage} for session in reversed(trend_sessions)]
        
        # Get recent sessions
        recent_sessions_data = []
        session_list_data = []
        
        for session in sessions:
            session_data = {
                'id': session.id,
                'start_time': session.start_time.strftime('%B %d, %Y at %I:%M %p'),
                'start_time_short': session.start_time.strftime('%b %d, %Y'),
                'percentage': float(session.percentage) if session.percentage is not None else 0.0,
                'score': int(session.score) if session.score else 0,
                'max_score': int(session.max_score) if session.max_score else 0,
                'duration_seconds': session.duration_seconds,
                'minutes': int(session.duration_seconds // 60) if session.duration_seconds else 0,
                'seconds': int(session.duration_seconds % 60) if session.duration_seconds else 0,
                'exam_title': session.exam.title if session.exam else 'Practice Test'
            }
            
            # Add to the list of all sessions
            session_list_data.append(session_data)
            
            # Also add to recent sessions if it's in the first 5
            if len(recent_sessions_data) < 5:
                recent_sessions_data.append(session_data)
        
        # Close the fresh session
        fresh_session.close()
        
        # Prepare response data
        response_data = {
            'total_sessions': total_sessions,
            'avg_score': round(avg_score, 1),
            'best_session': best_session,
            'subject_stats': subject_stats,
            'topic_stats': topic_stats,
            'difficulty_stats': difficulty_stats,
            'performance_trend': performance_trend,
            'recent_sessions': recent_sessions_data,
            'sessions': session_list_data,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        current_app.logger.info(f"Returning analytics data: total_sessions={total_sessions}, avg_score={avg_score}")
        
        # Return JSON data with appropriate headers
        response = jsonify(response_data)
        response.headers.add('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
        return response
        
    except Exception as e:
        current_app.logger.error(f"Error getting analytics data: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'error': str(e),
            'total_sessions': 0,
            'avg_score': 0,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }), 500

@bp.route('/api/questions/random', methods=['POST'])
def api_get_random_questions():
    """API endpoint to get random questions for practice/test"""
    data = request.get_json()
    topic_id = data.get('topic_id')
    subject_id = data.get('subject_id')
    count = data.get('count', 10)
    difficulty = data.get('difficulty')
    
    query = Question.query
    
    if topic_id:
        query = query.filter_by(topic_id=topic_id)
    elif subject_id:
        # Get questions from all topics in the subject
        topic_ids = [t.id for t in Topic.query.filter_by(subject_id=subject_id).all()]
        query = query.filter(Question.topic_id.in_(topic_ids))
    
    if difficulty:
        query = query.filter_by(difficulty_level=difficulty)
    
    # Get random questions
    total = query.count()
    if total == 0:
        return jsonify({'error': 'No questions found'}), 404
    
    # Use random sampling
    if total <= count:
        questions = query.all()
    else:
        # Get random offset
        random_offset = random.randint(0, max(0, total - count))
        questions = query.offset(random_offset).limit(count).all()
        
        # If we didn't get enough, get more from the beginning
        if len(questions) < count:
            remaining = count - len(questions)
            additional = query.limit(remaining).all()
            questions.extend(additional)
    
    # Format questions for response
    questions_data = []
    for q in questions:
        topic = Topic.query.get(q.topic_id)
        subject = Subject.query.get(topic.subject_id) if topic else None
        
        question_data = {
            'id': q.id,
            'qid': q.qid,
            'question': q.question_text,
            'options': q.get_options(),
            'correct_answer': q.correct_answer,
            'explanation': q.explanation,
            'difficulty_level': q.difficulty_level,
            'max_marks': q.max_marks,
            'topic': {
                'id': topic.id,
                'name': topic.name
            } if topic else None,
            'subject': {
                'id': subject.id,
                'name': subject.name,
                'class_level': subject.class_level
            } if subject else None
        }
        questions_data.append(question_data)
    
    return jsonify({
        'questions': questions_data,
        'total': len(questions_data)
    })

@bp.route('/api/submit-test', methods=['POST'])
@login_required
def api_submit_test():
    """API endpoint to submit test answers and get results"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        answers = data.get('answers', [])
        if not answers:
            return jsonify({'error': 'No answers provided'}), 400
            
        test_info = data.get('test_info', {})
        
        print(f"Processing test submission with {len(answers)} answers")
        
        # Calculate score
        total_questions = len(answers)
        correct_answers = 0
        detailed_results = []
        
        for i, answer_data in enumerate(answers):
            question_id = answer_data.get('question_id')
            user_answer = answer_data.get('answer', '')  # Default to empty string if no answer
            
            if not question_id:
                print(f"Warning: Answer at index {i} has no question_id")
                continue
                
            question = Question.query.get(question_id)
            if not question:
                print(f"Warning: Question with ID {question_id} not found")
                continue
                
            # Compare answers, handling case sensitivity and trimming whitespace
            is_correct = (question.correct_answer.strip().upper() == user_answer.strip().upper())
            if is_correct:
                correct_answers += 1
            
            # Create detailed result for analytics
            detailed_results.append({
                'question_id': question_id,
                'question': question.question_text,
                'options': question.get_options(),
                'user_answer': user_answer,
                'correct_answer': question.correct_answer,
                'is_correct': is_correct,
                'explanation': question.explanation,
                'difficulty_level': question.difficulty_level,
                'topic_id': question.topic_id
            })
        
        # Calculate percentage
        percentage = (correct_answers / total_questions * 100) if total_questions > 0 else 0
        print(f"Score calculation: {correct_answers}/{total_questions} = {percentage}%")
        
        # Add end time if not present
        end_time = datetime.utcnow()
        duration_seconds = data.get('duration_seconds', 0)
        
        # Create exam session record
        session = ExamSession(
            user_id=current_user.id,
            exam_id=None,  # Practice tests don't have exam_id
            score=correct_answers,
            max_score=total_questions,
            percentage=percentage,
            status='completed',
            start_time=end_time - datetime.timedelta(seconds=duration_seconds) if duration_seconds else datetime.utcnow(),
            end_time=end_time,
            duration_seconds=duration_seconds
        )
        
        # Store questions data including test info
        session.set_questions_data({
            'questions': detailed_results,
            'test_info': test_info
        })
        
        # Save to database with retry logic
        max_retries = 3
        retry_count = 0
        success = False
        
        while retry_count < max_retries and not success:
            try:
                db.session.add(session)
                db.session.commit()
                print(f"Session saved with ID: {session.id}")
                
                # Ensure the database is refreshed with the new session
                db.session.refresh(session)
                success = True
            except Exception as db_error:
                retry_count += 1
                print(f"Database save attempt {retry_count} failed: {str(db_error)}")
                db.session.rollback()
                if retry_count >= max_retries:
                    raise db_error
                import time
                time.sleep(0.5)  # Wait before retrying
        
        return jsonify({
            'session_id': session.id,
            'score': correct_answers,
            'total': total_questions,
            'percentage': round(percentage, 1),
            'results': detailed_results
        })
    except Exception as e:
        print(f"Error submitting test: {str(e)}")
        import traceback
        traceback.print_exc()  # Print full stack trace for debugging
        db.session.rollback()  # Roll back any failed transaction
        
        # Provide more specific error messages
        if 'SQLite' in str(e) or 'database' in str(e).lower():
            return jsonify({'error': 'Database error occurred while saving. Please try again.'}), 500
        elif 'JSON' in str(e):
            return jsonify({'error': 'Invalid data format. Please try again.'}), 400
        else:
            return jsonify({'error': f'An error occurred: {str(e)}'}), 500

@bp.route('/session/<int:session_id>/details')
@login_required
def session_details(session_id):
    """Show detailed session results with questions, answers, and explanations"""
    try:
        # Ensure we get fresh data
        db.session.close()
        session = ExamSession.query.filter_by(id=session_id, user_id=current_user.id).first_or_404()
        
        print(f"Retrieving details for session ID: {session_id}")
        
        # Get questions data from session
        questions_data = session.get_questions_data()
        questions = questions_data.get('questions', [])
        test_info = questions_data.get('test_info', {})
        
        if not questions:
            print(f"Warning: No questions found in session {session_id}")
        
        # Fetch full question details with explanations
        detailed_questions = []
        for i, q_data in enumerate(questions):
            try:
                question_id = q_data.get('question_id')
                if not question_id:
                    print(f"Warning: Question {i} in session {session_id} has no question_id")
                    continue
                    
                question = Question.query.get(question_id)
                if question:
                    detailed_questions.append({
                        'question': question,
                        'user_answer': q_data.get('user_answer'),
                        'correct_answer': q_data.get('correct_answer', question.correct_answer),
                        'is_correct': q_data.get('is_correct', False),
                        'explanation': q_data.get('explanation') or question.explanation or "No explanation available."
                    })
                else:
                    print(f"Warning: Question with ID {question_id} not found")
            except Exception as e:
                print(f"Error processing question {i} in session {session_id}: {str(e)}")
        
        # Calculate correct answers
        correct_answers = sum(1 for q in detailed_questions if q.get('is_correct'))
        
        # If session doesn't have a time, try to get it from test_info
        if not session.duration_seconds and test_info and 'duration_seconds' in test_info:
            session.duration_seconds = test_info['duration_seconds']
            # Save it to the database for future reference
            db.session.commit()
        
        return render_template('exam/session_details.html',
                             session=session,
                             questions=detailed_questions,
                             total_questions=len(detailed_questions),
                             correct_answers=correct_answers,
                             test_info=test_info)
    except Exception as e:
        print(f"Error retrieving session details for session {session_id}: {str(e)}")
        import traceback
        traceback.print_exc()
        flash(f"Error retrieving session details: {str(e)}", "danger")
        return redirect(url_for('exam.results'))
