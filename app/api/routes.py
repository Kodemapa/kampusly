"""
API Blueprint - RESTful API endpoints (database-backed)
"""

import random
import re
import json
import os
from flask import Blueprint, jsonify, request, send_file
from html import unescape
from app.models import db, Subject, Topic, Question

bp = Blueprint('api', __name__)

# API Routes (database-backed)
@bp.route('/classes', methods=['GET'])
def get_classes():
    """Return list of available classes."""
    return jsonify({'classes': ['XI', 'XII']})

@bp.route('/subjects/<class_selection>', methods=['GET'])
def get_subjects(class_selection):
    """Return list of subjects for the selected class."""
    if class_selection not in ['XI', 'XII']:
        return jsonify({'error': f'Class {class_selection} not found'}), 404
    
    # Get subjects for the specified class
    subjects = Subject.query.filter_by(class_level=class_selection).all()
    
    if not subjects:
        return jsonify({'error': f'No subjects found for class {class_selection}'}), 404
    
    subjects_data = [{'id': subject.id, 'name': subject.name} for subject in subjects]
    return jsonify({'subjects': subjects_data})

@bp.route('/topics/<class_selection>/<int:subject_id>', methods=['GET'])
def get_topics(class_selection, subject_id):
    """Return topics for a subject."""
    if class_selection not in ['XI', 'XII']:
        return jsonify({'error': f'Class {class_selection} not found'}), 404
    
    # Verify subject exists and belongs to the class
    subject = Subject.query.filter_by(id=subject_id, class_level=class_selection).first()
    if not subject:
        return jsonify({'error': f'Subject ID {subject_id} not found for class {class_selection}'}), 404
    
    # Get topics for this subject
    topics = Topic.query.filter_by(subject_id=subject_id).all()
    
    topics_data = []
    for topic in topics:
        # Count questions for this topic
        question_count = Question.query.filter_by(topic_id=topic.id).count()
        
        topics_data.append({
            'id': topic.id,
            'name': topic.name,
            'description': topic.description,
            'question_count': question_count
        })
    
    return jsonify({
        'subject': {'id': subject.id, 'name': subject.name},
        'topics': topics_data
    })

@bp.route('/questions/sample', methods=['GET'])
def get_sample_questions():
    """Get sample questions with optional filtering."""
    try:
        # Get parameters
        topic_id = request.args.get('topic_id', type=int)
        difficulty = request.args.get('difficulty')
        limit = request.args.get('limit', default=10, type=int)
        
        # Start with base query
        query = Question.query
        
        # Apply filters
        if topic_id:
            query = query.filter_by(topic_id=topic_id)
        if difficulty:
            # Filter by question difficulty level
            query = query.filter(Question.difficulty_level == difficulty)
        
        # Get questions
        questions = query.limit(limit).all()
        
        if not questions:
            return jsonify({'error': 'No questions found with the specified criteria'}), 404
        
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
                'answer': q.correct_answer,
                'explanation': q.explanation,
                'difficulty_level': q.difficulty_level,
                'max_marks': q.max_marks,
                'topic': {
                    'id': topic.id,
                    'name': topic.name,
                    'description': topic.description
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
            'total': len(questions_data),
            'filters': {
                'topic_id': topic_id,
                'difficulty': difficulty,
                'limit': limit
            }
        })
        
    except Exception as e:
        return jsonify({'error': f'An error occurred: {str(e)}'}), 500

@bp.route('/questions/random', methods=['POST'])
def get_random_questions():
    """
    Get random sample questions from a specific topic.
    Request JSON:
    {
        "topic_id": 1,
        "count": 10,
        "difficulty": "Easy" (optional)
    }
    """
    try:
        data = request.get_json()
        topic_id = data.get("topic_id")
        count = int(data.get("count", 10))
        difficulty = data.get("difficulty")

        if not topic_id or count <= 0:
            return jsonify({'error': 'Missing or invalid fields: topic_id, count'}), 400

        # Verify topic exists
        topic = Topic.query.get(topic_id)
        if not topic:
            return jsonify({'error': f'Topic ID {topic_id} not found'}), 404

        # Build query
        query = Question.query.filter_by(topic_id=topic_id)
        if difficulty:
            query = query.filter(Question.difficulty_level == difficulty)

        # Get all questions for this topic
        all_questions = query.all()

        if not all_questions:
            return jsonify({'error': 'No questions found for the specified criteria'}), 404

        if count > len(all_questions):
            return jsonify({
                'error': f'Only {len(all_questions)} questions available, but {count} requested'
            }), 400

        # Get random sample
        sample_questions = random.sample(all_questions, count)

        # Format questions for response
        questions_data = []
        for q in sample_questions:
            subject = Subject.query.get(topic.subject_id)
            question_data = {
                'id': q.id,
                'qid': q.qid,
                'question': q.question_text,
                'options': q.get_options(),
                'answer': q.correct_answer,
                'explanation': q.explanation,
                'difficulty_level': q.difficulty_level,
                'max_marks': q.max_marks,
                'topic': {
                    'id': topic.id,
                    'name': topic.name,
                    'description': topic.description
                },
                'subject': {
                    'id': subject.id,
                    'name': subject.name,
                    'class_level': subject.class_level
                } if subject else None
            }
            questions_data.append(question_data)

        return jsonify({
            'topic_id': topic_id,
            'topic_name': topic.name,
            'total_questions_available': len(all_questions),
            'sample_size': count,
            'difficulty_filter': difficulty,
            'questions': questions_data
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.route('/questions/evaluate', methods=['POST'])
def evaluate_answers():
    """
    Evaluate submitted answers and return results.
    Request JSON:
    {
        "submissions": [
            {
                "question_id": 1,
                "submitted_answer": "A",
                "time_taken": 30
            },
            {
                "question_id": 2,
                "submitted_answer": "B",
                "time_taken": 45
            }
        ]
    }
    """
    try:
        data = request.get_json()
        submissions = data.get("submissions", [])
        
        if not submissions:
            return jsonify({'error': 'No submissions provided'}), 400
        
        results = []
        total_score = 0
        total_possible = 0
        total_time_taken = 0
        correct_count = 0
        incorrect_count = 0
        
        for submission in submissions:
            question_id = submission.get("question_id")
            submitted_answer = submission.get("submitted_answer", "").strip()
            time_taken = submission.get("time_taken", 0)
            
            if not question_id:
                continue
                
            # Get the question from database
            question = Question.query.get(question_id)
            if not question:
                results.append({
                    'question_id': question_id,
                    'error': 'Question not found',
                    'is_correct': False,
                    'score': 0,
                    'max_marks': 0
                })
                continue
            
            # Get correct answer
            correct_answer = question.correct_answer
            max_marks = question.max_marks or 1
            
            # Evaluate the answer
            is_correct = False
            score = 0
            
            if submitted_answer and correct_answer:
                # Handle different answer formats (A, B, C, D or 0, 1, 2, 3)
                submitted_normalized = normalize_answer(submitted_answer)
                correct_normalized = normalize_answer(correct_answer)
                
                is_correct = submitted_normalized == correct_normalized
                score = max_marks if is_correct else 0
            
            # Update counters
            total_score += score
            total_possible += max_marks
            total_time_taken += time_taken
            
            if is_correct:
                correct_count += 1
            else:
                incorrect_count += 1
            
            # Get topic and subject info
            topic = Topic.query.get(question.topic_id)
            subject = Subject.query.get(topic.subject_id) if topic else None
            
            result_item = {
                'question_id': question_id,
                'qid': question.qid,
                'submitted_answer': submitted_answer,
                'correct_answer': correct_answer,
                'is_correct': is_correct,
                'score': score,
                'max_marks': max_marks,
                'time_taken': time_taken,
                'difficulty_level': question.difficulty_level,
                'question_text': question.question_text,
                'options': question.get_options(),
                'explanation': question.explanation,
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
            
            results.append(result_item)
        
        # Calculate statistics
        total_questions = len(submissions)
        percentage = (total_score / total_possible * 100) if total_possible > 0 else 0
        accuracy = (correct_count / total_questions * 100) if total_questions > 0 else 0
        average_time_per_question = total_time_taken / total_questions if total_questions > 0 else 0
        
        # Determine grade/performance level
        if percentage >= 90:
            grade = 'A+'
            performance = 'Excellent'
        elif percentage >= 80:
            grade = 'A'
            performance = 'Very Good'
        elif percentage >= 70:
            grade = 'B+'
            performance = 'Good'
        elif percentage >= 60:
            grade = 'B'
            performance = 'Above Average'
        elif percentage >= 50:
            grade = 'C'
            performance = 'Average'
        elif percentage >= 40:
            grade = 'D'
            performance = 'Below Average'
        else:
            grade = 'F'
            performance = 'Poor'
        
        return jsonify({
            'evaluation_summary': {
                'total_questions': total_questions,
                'correct_answers': correct_count,
                'incorrect_answers': incorrect_count,
                'total_score': total_score,
                'total_possible': total_possible,
                'percentage': round(percentage, 2),
                'accuracy': round(accuracy, 2),
                'grade': grade,
                'performance_level': performance,
                'total_time_taken': total_time_taken,
                'average_time_per_question': round(average_time_per_question, 2)
            },
            'detailed_results': results,
            'breakdown_by_difficulty': get_difficulty_breakdown(results),
            'breakdown_by_subject': get_subject_breakdown(results)
        })
        
    except Exception as e:
        return jsonify({'error': f'Evaluation failed: {str(e)}'}), 500

def normalize_answer(answer):
    """Normalize answer format for comparison."""
    if not answer:
        return ""
    
    answer_str = str(answer).strip().upper()
    
    # Handle different formats: A, B, C, D or 0, 1, 2, 3
    if answer_str in ['0', 'A']:
        return 'A'
    elif answer_str in ['1', 'B']:
        return 'B'
    elif answer_str in ['2', 'C']:
        return 'C'
    elif answer_str in ['3', 'D']:
        return 'D'
    
    return answer_str

def get_difficulty_breakdown(results):
    """Get performance breakdown by difficulty level."""
    breakdown = {}
    
    for result in results:
        difficulty = result.get('difficulty_level', 'unknown')
        if difficulty not in breakdown:
            breakdown[difficulty] = {
                'total': 0,
                'correct': 0,
                'total_score': 0,
                'total_possible': 0
            }
        
        breakdown[difficulty]['total'] += 1
        if result['is_correct']:
            breakdown[difficulty]['correct'] += 1
        breakdown[difficulty]['total_score'] += result['score']
        breakdown[difficulty]['total_possible'] += result['max_marks']
    
    # Calculate percentages
    for difficulty in breakdown:
        stats = breakdown[difficulty]
        if stats['total'] > 0:
            stats['accuracy'] = round(stats['correct'] / stats['total'] * 100, 2)
        if stats['total_possible'] > 0:
            stats['percentage'] = round(stats['total_score'] / stats['total_possible'] * 100, 2)
    
    return breakdown

def get_subject_breakdown(results):
    """Get performance breakdown by subject."""
    breakdown = {}
    
    for result in results:
        subject_info = result.get('subject')
        if not subject_info:
            continue
            
        subject_name = subject_info['name']
        if subject_name not in breakdown:
            breakdown[subject_name] = {
                'total': 0,
                'correct': 0,
                'total_score': 0,
                'total_possible': 0
            }
        
        breakdown[subject_name]['total'] += 1
        if result['is_correct']:
            breakdown[subject_name]['correct'] += 1
        breakdown[subject_name]['total_score'] += result['score']
        breakdown[subject_name]['total_possible'] += result['max_marks']
    
    # Calculate percentages
    for subject in breakdown:
        stats = breakdown[subject]
        if stats['total'] > 0:
            stats['accuracy'] = round(stats['correct'] / stats['total'] * 100, 2)
        if stats['total_possible'] > 0:
            stats['percentage'] = round(stats['total_score'] / stats['total_possible'] * 100, 2)
    
    return breakdown

# Additional API endpoints for database statistics
@bp.route('/stats', methods=['GET'])
def get_stats():
    """Get database statistics."""
    try:
        stats = {
            'subjects': Subject.query.count(),
            'topics': Topic.query.count(),
            'questions': Question.query.count(),
            'subjects_by_class': {
                'XI': Subject.query.filter_by(class_level='XI').count(),
                'XII': Subject.query.filter_by(class_level='XII').count()
            },
            'questions_by_difficulty': {}
        }
        
        # Count questions by difficulty level
        for difficulty in ['easy', 'moderate', 'difficult']:
            count = Question.query.filter(Question.difficulty_level == difficulty).count()
            stats['questions_by_difficulty'][difficulty] = count
        
        return jsonify(stats)
        
    except Exception as e:
        return jsonify({'error': f'An error occurred: {str(e)}'}), 500

@bp.route('/questions/practice', methods=['POST'])
def get_practice_questions():
    """API endpoint to get random questions for practice/test"""
    try:
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
        
    except Exception as e:
        return jsonify({'error': f'An error occurred: {str(e)}'}), 500

@bp.route('/submit-practice', methods=['POST'])
def submit_practice_test():
    """API endpoint to submit practice test answers and get results"""
    try:
        data = request.get_json()
        answers = data.get('answers', [])
        test_info = data.get('test_info', {})
        
        # Calculate score
        total_questions = len(answers)
        correct_answers = 0
        detailed_results = []
        
        for answer_data in answers:
            question_id = answer_data.get('question_id')
            user_answer = answer_data.get('answer')
            
            question = Question.query.get(question_id)
            if question:
                is_correct = question.correct_answer == user_answer
                if is_correct:
                    correct_answers += 1
                
                detailed_results.append({
                    'question_id': question_id,
                    'question': question.question_text,
                    'options': question.get_options(),
                    'user_answer': user_answer,
                    'correct_answer': question.correct_answer,
                    'is_correct': is_correct,
                    'explanation': question.explanation
                })
        
        # Calculate percentage
        percentage = (correct_answers / total_questions * 100) if total_questions > 0 else 0
        
        return jsonify({
            'score': correct_answers,
            'total': total_questions,
            'percentage': round(percentage, 1),
            'results': detailed_results
        })
        
    except Exception as e:
        return jsonify({'error': f'An error occurred: {str(e)}'}), 500
