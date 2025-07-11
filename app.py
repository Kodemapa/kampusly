import random
import re
from flask import Flask, jsonify, request, send_file
import json
import pypandoc
pypandoc.download_pandoc()
from html import unescape
import os

app = Flask(__name__)

# API Routes
@app.route('/api/classes', methods=['GET'])
def get_classes():
    """Return list of available classes."""
    return jsonify({'classes': ['XI', 'XII']})


@app.route('/api/subjects/<class_selection>', methods=['GET'])
def get_subjects(class_selection):
    """Return list of subjects (L3) for the selected class."""
    json_file = f'CBSE_{class_selection}.json'
    if not os.path.exists(json_file):
        return jsonify({'error': f'Class {class_selection} not found'}), 404

    with open(json_file) as file:
        try:
            data = json.load(file)['result']['data']
        except Exception as e:
            return jsonify({'error': f'Invalid JSON: {str(e)}'}), 500

    subjects = [{'id': l3['id'], 'name': l3['name']} for l3 in data.get('L3', [])]
    return jsonify({'subjects': subjects})


@app.route('/api/topics/<class_selection>/<int:subject_id>', methods=['GET'])
def get_topics(class_selection, subject_id):
    """Return L4 topics and L5 tests for a subject."""
    json_file = f'CBSE_{class_selection}.json'
    if not os.path.exists(json_file):
        return jsonify({'error': f'Class {class_selection} not found'}), 404

    with open(json_file) as file:
        try:
            data = json.load(file)['result']['data']
        except Exception as e:
            return jsonify({'error': f'Invalid JSON: {str(e)}'}), 500

    subject = next((l3 for l3 in data.get('L3', []) if l3['id'] == subject_id), None)
    if not subject:
        return jsonify({'error': f'Subject ID {subject_id} not found'}), 404

    topics = []
    for l4 in subject.get('L4', []):
        tests = []
        for t in l4.get('L5', []):
            if len(t) > 11:
                file_path_data = t[11]
                test_id = t[10] if len(t) > 10 else None
                
                # Extract file path properly
                if isinstance(file_path_data, dict) and 'file_path' in file_path_data:
                    file_path = file_path_data['file_path']
                elif isinstance(file_path_data, str):
                    file_path = file_path_data
                else:
                    file_path = str(file_path_data)
                
                # Extract test ID properly
                if isinstance(test_id, dict) and 'file_path' in test_id:
                    test_id = test_id['file_path']
                elif not isinstance(test_id, (str, int)):
                    test_id = str(test_id)
                
                tests.append({
                    'id': test_id,
                    'label': t[0],
                    'file_path': file_path
                })
        
        topic = {
            'name': l4['name'],
            'tests': tests
        }
        topics.append(topic)

    return jsonify({'topics': topics})


@app.route('/api/questions/sample', methods=['POST'])
def get_random_questions():
    """
    Get random sample questions from a specific topic.
    Request JSON:
    {
        "class": "XI",
        "subjectId": 10422,
        "topicName": "Sets",
        "count": 10
    }
    """
    try:
        data = request.get_json()
        class_selection = data.get("class")
        subject_id = data.get("subjectId")
        topic_name = data.get("topicName")
        count = int(data.get("count", 0))

        if not (class_selection and subject_id and topic_name and count > 0):
            return jsonify({'error': 'Missing or invalid fields: class, subjectId, topicName, count'}), 400

        json_file = f'CBSE_{class_selection}.json'
        if not os.path.exists(json_file):
            return jsonify({'error': f'Class "{class_selection}" not found'}), 404

        with open(json_file) as file:
            full_data = json.load(file)['result']['data']
        
        subject = next((l3 for l3 in full_data.get('L3', []) if l3['id'] == subject_id), None)
        if not subject:
            return jsonify({'error': f'Subject ID "{subject_id}" not found'}), 404

        topic = next((l4 for l4 in subject.get('L4', []) if l4['name'].lower() == topic_name.lower()), None)
        if not topic:
            return jsonify({'error': f'Topic "{topic_name}" not found in subject {subject["name"]}'}), 404

        test_file_paths = []
        for test in topic.get('L5', []):
            if len(test) > 11:
                file_path_data = test[11]
                if isinstance(file_path_data, dict) and 'file_path' in file_path_data:
                    test_file_paths.append(file_path_data['file_path'].replace('\\', '/'))
                elif isinstance(file_path_data, str):
                    test_file_paths.append(file_path_data.replace('\\', '/'))

        seen_qids = set()
        all_questions = []

        for path in test_file_paths:
            if not os.path.exists(path):
                continue
            with open(path, 'r') as f:
                try:
                    test_data = json.load(f)['result']['data']
                except Exception:
                    continue

                for test_info in test_data:
                    # Skip if test_info is not a dictionary
                    if not isinstance(test_info, dict):
                        continue
                    for sec in test_info.get('sec_details', []):
                        for q in sec.get('sec_questions', []):
                            qid = q.get("qid")
                            if qid and qid not in seen_qids:
                                seen_qids.add(qid)
                                if 'difficulty_level' not in q:
                                    q['difficulty_level'] = determine_difficulty(q.get('que', {}).get('1', {}).get('q_string', ''))
                                else:
                                    q['difficulty_level'] = q['difficulty_level'].lower()
                                all_questions.append(q)

        if not all_questions:
            return jsonify({'error': 'No questions found'}), 404

        if count > len(all_questions):
            return jsonify({
                'error': f'Only {len(all_questions)} questions available, but {count} requested'
            }), 400

        sample_questions = random.sample(all_questions, count)

        difficulty_count = {'easy': 0, 'moderate': 0, 'difficult': 0}
        for q in sample_questions:
            level = q['difficulty_level']
            difficulty_count[level] = difficulty_count.get(level, 0) + 1

        return jsonify({
            'class': class_selection,
            'subjectId': subject_id,
            'topic': topic_name,
            'total_questions_available': len(all_questions),
            'sample_size': count,
            'difficulty_breakdown': difficulty_count,
            'questions': sample_questions
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/export/docx', methods=['POST'])
def export_to_docx():
    """
    Export selected questions to DOCX format.
    Request JSON:
    {
        "test_name": "Sample Test",
        "test_time": "90",
        "selected_questions": [...]
    }
    """
    try:
        data = request.get_json()
        test_name = data.get('test_name', 'Question Paper')
        selected_questions = data.get('selected_questions', [])
        
        if not selected_questions:
            return jsonify({'error': 'No questions provided'}), 400
        
        template_filename = f"{test_name}.tex"
        docx_filename = f"{test_name}.docx"

        # Generate LaTeX content from selected_questions
        latex_content = generate_latex_content(selected_questions, test_name)

        # Write LaTeX content to file
        with open(template_filename, 'w', encoding='utf-8') as f:
            f.write(latex_content)

        # Convert LaTeX to DOCX
        convert_latex_to_docx(template_filename, docx_filename)
        
        return send_file(docx_filename, as_attachment=True, download_name=f"{test_name}.docx")

    except Exception as e:
        return jsonify({'error': f'Export failed: {str(e)}'}), 500


# Utility Functions
def determine_difficulty(question):
    """Determine difficulty level of a question based on content."""
    if not question:
        return 'Difficult'
    
    question_lower = question.lower()
    if 'easy' in question_lower:
        return 'Easy'
    elif 'moderate' in question_lower:
        return 'Moderate'
    else:
        return 'Difficult'


def html_to_latex(html):
    """Convert HTML content to LaTeX format."""
    if not html:
        return ""
    
    # Unescape HTML entities
    html = unescape(html)

    # Replace HTML tags with LaTeX equivalents
    replacements = [
        (r"<p>", r""),
        (r"</p>", r""),
        (r"<sup>", r"$^{"),
        (r"</sup>", r"}$"),
        (r"<sub>", r"$_{"),
        (r"</sub>", r"}$"),
        (r"<b>", r"\\textbf{"),
        (r"</b>", r"}"),
        (r"<i>", r"\\textit{"),
        (r"</i>", r"}"),
        (r"&nbsp;", r"~"),
        (r"&gt;", r">"),
        (r"&lt;", r"<"),
        (r"&amp;", r"&"),
        (r'<br\s*/?>', r"\\newline"),
        (r'<span[^>]*>', r""),
        (r'</span>', r""),
        (r'<div[^>]*>', r""),
        (r'</div>', r"")
    ]
    
    for old, new in replacements:
        html = re.sub(old, new, html, flags=re.IGNORECASE)

    return html


def generate_latex_content(selected_questions, test_name):
    """Generate LaTeX document content from questions."""
    latex_content = r'''\documentclass{article}
\usepackage{amsmath}
\usepackage{amssymb}
\usepackage{graphicx}
\usepackage{enumitem}
\usepackage{longtable}
\title{%s}
\begin{document}
\maketitle
''' % test_name

    # Generate LaTeX content from selected_questions
    for index, question in enumerate(selected_questions, start=1):
        q_string = html_to_latex(question.get('que', {}).get('1', {}).get('q_string', ''))
        q_options = [html_to_latex(opt) for opt in question.get('que', {}).get('1', {}).get('q_option', [])]

        latex_content += r'\section*{Question %d}' % index + '\n'
        latex_content += q_string + '\n'
        latex_content += r'\begin{enumerate}[label=(\alph*)]' + '\n'
        for option in q_options:
            latex_content += r'\item ' + option + '\n'
        latex_content += r'\end{enumerate}' + '\n'
        latex_content += r'\newpage' + '\n'

    # End the LaTeX document
    latex_content += r'\end{document}'
    return latex_content


def convert_latex_to_docx(latex_filename, docx_filename):
    """Convert LaTeX file to DOCX using pypandoc."""
    pypandoc.convert_file(latex_filename, 'docx', outputfile=docx_filename)


if __name__ == "__main__":
    app.run(debug=True, port=5001)