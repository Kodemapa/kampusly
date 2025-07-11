"""
Database Initialization Script
Migrates JSON data to SQLAlchemy database
"""

import os
import sys
import json
from datetime import datetime

# Add parent directory to path to import app modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.models import db, User, Subject, Topic, Question
from enhanced_solutions_loader import load_comprehensive_solutions

def init_database():
    """Initialize database with sample data"""
    print("🔄 Initializing database...")
    
    # Create all tables
    db.create_all()
    print("✅ Database tables created")
    
    # Create admin user
    admin = User.query.filter_by(username='admin').first()
    if not admin:
        admin = User(
            username='admin',
            email='admin@kodemapa.com',
            role='admin'
        )
        admin.set_password('admin123')
        db.session.add(admin)
        print("✅ Admin user created (username: admin, password: admin123)")
    
    # Create sample student
    student = User.query.filter_by(username='student').first()
    if not student:
        student = User(
            username='student',
            email='student@example.com',
            role='student'
        )
        student.set_password('student123')
        db.session.add(student)
        print("✅ Sample student created (username: student, password: student123)")
    
    db.session.commit()
    
    # Load subjects and topics from JSON files
    load_subjects_from_json()
    
    print("🎉 Database initialization complete!")
    print("\n📊 Database Summary:")
    print(f"   Users: {User.query.count()}")
    print(f"   Subjects: {Subject.query.count()}")
    print(f"   Topics: {Topic.query.count()}")
    
    total_questions = Question.query.count()
    questions_with_answers = Question.query.filter(Question.correct_answer.isnot(None)).filter(Question.correct_answer != '').count()
    questions_with_explanations = Question.query.filter(Question.explanation.isnot(None)).filter(Question.explanation != '').count()
    
    print(f"   Questions: {total_questions}")
    print(f"   Questions with answers: {questions_with_answers} ({(questions_with_answers/total_questions*100):.1f}%)")
    print(f"   Questions with explanations: {questions_with_explanations} ({(questions_with_explanations/total_questions*100):.1f}%)")
    
    # Additional statistics
    questions_without_solutions = total_questions - questions_with_answers
    print(f"   Questions without solutions: {questions_without_solutions}")
    
    # Sample coverage by difficulty
    easy_total = Question.query.filter_by(difficulty_level='easy').count()
    easy_with_answers = Question.query.filter_by(difficulty_level='easy').filter(Question.correct_answer.isnot(None)).filter(Question.correct_answer != '').count()
    
    moderate_total = Question.query.filter_by(difficulty_level='moderate').count()
    moderate_with_answers = Question.query.filter_by(difficulty_level='moderate').filter(Question.correct_answer.isnot(None)).filter(Question.correct_answer != '').count()
    
    difficult_total = Question.query.filter_by(difficulty_level='difficult').count()
    difficult_with_answers = Question.query.filter_by(difficulty_level='difficult').filter(Question.correct_answer.isnot(None)).filter(Question.correct_answer != '').count()
    
    print(f"\n📈 Solution Coverage by Difficulty:")
    if easy_total > 0:
        print(f"   Easy: {easy_with_answers}/{easy_total} ({(easy_with_answers/easy_total*100):.1f}%)")
    if moderate_total > 0:
        print(f"   Moderate: {moderate_with_answers}/{moderate_total} ({(moderate_with_answers/moderate_total*100):.1f}%)")
    if difficult_total > 0:
        print(f"   Difficult: {difficult_with_answers}/{difficult_total} ({(difficult_with_answers/difficult_total*100):.1f}%)")

def load_subjects_from_json():
    """Load subjects and topics from JSON files"""
    print("🔄 Loading subjects from JSON files...")
    
    # Load comprehensive solutions from all available files
    print("📖 Loading comprehensive solutions from all available files...")
    solutions_map = load_comprehensive_solutions()
    print(f"✅ Loaded {len(solutions_map)} comprehensive solutions")
    
    for class_level in ['XI', 'XII']:
        json_file = f'CBSE_{class_level}.json'
        if not os.path.exists(json_file):
            print(f"⚠️  File {json_file} not found, skipping...")
            continue
            
        print(f"📖 Processing {json_file}...")
        
        with open(json_file, 'r') as f:
            data = json.load(f)['result']['data']
        
        for l3_data in data.get('L3', []):
            # Create or get subject
            subject = Subject.query.filter_by(
                name=l3_data['name'], 
                class_level=class_level
            ).first()
            
            if not subject:
                subject = Subject(
                    name=l3_data['name'],
                    class_level=class_level,
                    description=f"CBSE Class {class_level} {l3_data['name']}"
                )
                db.session.add(subject)
                print(f"  ➕ Added subject: {subject.name}")
            
            # Create topics (L4)
            for l4_data in l3_data.get('L4', []):
                topic = Topic.query.filter_by(
                    name=l4_data['name'],
                    subject=subject
                ).first()
                
                if not topic:
                    topic = Topic(
                        name=l4_data['name'],
                        subject=subject,
                        description=f"Topic in {subject.name}"
                    )
                    db.session.add(topic)
                    print(f"    ➕ Added topic: {topic.name}")
                
                # Load questions from this topic's test files
                question_count = load_questions_from_topic(l4_data, topic, solutions_map)
                topic.question_count = question_count
                print(f"    📊 {topic.name}: {question_count} questions loaded")
    
    db.session.commit()
    print("✅ Subjects, topics, and questions loaded from JSON")

def load_questions_from_topic(l4_data, topic, solutions_map=None):
    """Load questions from topic test files into database"""
    question_count = 0
    seen_qids = set()
    questions_with_solutions = 0
    questions_without_solutions = 0
    
    for test in l4_data.get('L5', []):
        if len(test) > 11:
            file_path_data = test[11]
            
            # Extract file path
            if isinstance(file_path_data, dict) and 'file_path' in file_path_data:
                file_path = file_path_data['file_path'].replace('\\', '/')
            elif isinstance(file_path_data, str):
                file_path = file_path_data.replace('\\', '/')
            else:
                continue
            
            if os.path.exists(file_path):
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        test_data = json.load(f)['result']['data']
                    
                    for test_info in test_data:
                        if isinstance(test_info, dict):
                            for sec in test_info.get('sec_details', []):
                                for q_data in sec.get('sec_questions', []):
                                    qid = q_data.get("qid")
                                    if qid and qid not in seen_qids:
                                        # Check if question already exists in database
                                        existing_question = Question.query.filter_by(qid=qid).first()
                                        if existing_question:
                                            continue
                                        
                                        seen_qids.add(qid)
                                        
                                        # Extract question details
                                        que_data = q_data.get('que', {}).get('1', {})
                                        question_text = que_data.get('q_string', '')
                                        options = que_data.get('q_option', [])
                                        
                                        # Determine difficulty
                                        if 'difficulty_level' in q_data:
                                            difficulty = q_data['difficulty_level'].lower()
                                        else:
                                            difficulty = determine_difficulty_from_text(question_text)
                                        
                                        # Get correct answer and explanation from solutions
                                        solution_data = solutions_map.get(qid) if solutions_map else None
                                        correct_answer = None
                                        explanation = None
                                        
                                        if solution_data:
                                            correct_answer = solution_data.get('correct_answer')
                                            explanation = solution_data.get('explanation')
                                            questions_with_solutions += 1
                                        else:
                                            questions_without_solutions += 1
                                        
                                        # Create question object
                                        question = Question(
                                            qid=qid,
                                            question_text=question_text,
                                            correct_answer=correct_answer,
                                            explanation=explanation,
                                            difficulty_level=difficulty,
                                            max_marks=q_data.get('max_marks', 1),
                                            topic=topic
                                        )
                                        
                                        # Set options as JSON
                                        if options:
                                            question.set_options(options)
                                        
                                        try:
                                            db.session.add(question)
                                            question_count += 1
                                        except Exception as e:
                                            print(f"      ⚠️  Error adding question {qid}: {e}")
                                            db.session.rollback()
                                        
                except Exception as e:
                    print(f"    ⚠️  Error reading {file_path}: {e}")
    
    if question_count > 0:
        solution_coverage = (questions_with_solutions / question_count) * 100
        print(f"    📈 Solution coverage: {questions_with_solutions}/{question_count} ({solution_coverage:.1f}%)")
    
    return question_count

def determine_difficulty_from_text(question_text):
    """Determine difficulty level from question text"""
    if not question_text:
        return 'moderate'
    
    question_lower = question_text.lower()
    if 'easy' in question_lower:
        return 'easy'
    elif 'moderate' in question_lower:
        return 'moderate'
    elif any(word in question_lower for word in ['difficult', 'hard', 'complex']):
        return 'difficult'
    else:
        return 'moderate'  # Default to moderate

def load_solutions():
    """Legacy function - now replaced by load_comprehensive_solutions()"""
    print("⚠️  load_solutions() is deprecated, using load_comprehensive_solutions() instead")
    return load_comprehensive_solutions()

def update_questions_with_solutions():
    """Update existing questions with solutions from comprehensive loader"""
    print("🔄 Updating existing questions with solutions...")
    
    # Load comprehensive solutions
    solutions_map = load_comprehensive_solutions()
    print(f"✅ Loaded {len(solutions_map)} comprehensive solutions")
    
    # Get questions without answers or explanations
    questions_to_update = Question.query.filter(
        db.or_(
            Question.correct_answer.is_(None),
            Question.correct_answer == '',
            Question.explanation.is_(None),
            Question.explanation == ''
        )
    ).all()
    
    print(f"📝 Found {len(questions_to_update)} questions that might need solutions")
    
    updated_count = 0
    answers_added = 0
    explanations_added = 0
    
    for question in questions_to_update:
        if question.qid in solutions_map:
            solution = solutions_map[question.qid]
            updated = False
            
            # Update answer if missing or empty
            if not question.correct_answer or question.correct_answer.strip() == '':
                if solution.get('correct_answer'):
                    question.correct_answer = solution['correct_answer']
                    answers_added += 1
                    updated = True
            
            # Update explanation if missing or empty
            if not question.explanation or question.explanation.strip() == '':
                if solution.get('explanation'):
                    question.explanation = solution['explanation']
                    explanations_added += 1
                    updated = True
            
            if updated:
                updated_count += 1
    
    # Commit updates
    try:
        db.session.commit()
        print(f"✅ Updated {updated_count} questions")
        print(f"   📝 Added {answers_added} answers")
        print(f"   📖 Added {explanations_added} explanations")
    except Exception as e:
        print(f"⚠️  Error updating questions: {e}")
        db.session.rollback()

if __name__ == '__main__':
    # Create Flask app context
    app = create_app('development')
    
    with app.app_context():
        print("🚀 KODEMAPA-EXAMPAD Database Initialization")
        print("=" * 50)
        
        # Check if user wants to reset database
        if '--reset' in sys.argv:
            print("⚠️  Resetting database (all data will be lost)...")
            db.drop_all()
            print("✅ Database reset complete")
            init_database()
        elif '--update-solutions' in sys.argv:
            print("🔄 Updating existing questions with solutions...")
            update_questions_with_solutions()
        else:
            init_database()
        
        print("\n🎯 Next Steps:")
        print("1. Install full requirements: pip install -r requirements_full.txt")
        print("2. Run the application: python run_new.py")
        print("3. Access the platform at: http://127.0.0.1:5001")
        print("4. Login with admin/admin123 or student/student123")
        print("\n💡 Available options:")
        print("   python3 scripts/init_db.py --reset          # Reset and reinitialize database")
        print("   python3 scripts/init_db.py --update-solutions # Update existing questions with solutions")
