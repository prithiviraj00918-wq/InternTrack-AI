import os
import json
import io
import csv
import sqlite3
from datetime import datetime
from functools import wraps
from flask import (Flask, request, jsonify, session,
                   send_from_directory, send_file, abort)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from db import get_db, init_db

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, static_folder=os.path.join(BASE_DIR, 'public'), static_url_path='')
app.secret_key = 'intersip-secret-key-2026-antigravity'
app.config['UPLOAD_FOLDER'] = os.path.join(BASE_DIR, 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024
ALLOWED_EXTENSIONS = {'pdf'}

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'admin':
            return jsonify({'error': 'Forbidden'}), 403
        return f(*args, **kwargs)
    return decorated

def student_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'student':
            return jsonify({'error': 'Forbidden'}), 403
        return f(*args, **kwargs)
    return decorated

def compute_match_score(student_skills, internship_skills_str):
    if not internship_skills_str:
        return 0
    req = set(s.strip().lower() for s in internship_skills_str.split(',') if s.strip())
    student = set(s.strip().lower() for s in student_skills if s.strip())
    if not req:
        return 0
    matched = len(req & student)
    return round((matched / len(req)) * 100)

def get_recommendation_level(score):
    if score >= 80:
        return 'Excellent Match'
    elif score >= 60:
        return 'Strong Match'
    elif score >= 40:
        return 'Moderate Match'
    else:
        return 'Low Match'

def get_student_skills(student_id, db):
    rows = db.execute("SELECT skill_name FROM student_skills WHERE student_id=?", (student_id,)).fetchall()
    return [r['skill_name'] for r in rows]

@app.route('/')
def index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/uploads/<filename>')
def serve_upload(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/api/auth/register', methods=['POST'])
def register():
    data = request.get_json()
    username = (data.get('username') or '').strip()
    password = (data.get('password') or '').strip()
    full_name = (data.get('full_name') or '').strip()
    email = (data.get('email') or '').strip()

    if not username or not password or not full_name or not email:
        return jsonify({'error': 'All fields are required'}), 400
    if len(password) < 6:
        return jsonify({'error': 'Password must be at least 6 characters'}), 400

    db = get_db()
    try:
        pw_hash = generate_password_hash(password)
        db.execute("INSERT INTO users(username,password_hash,role) VALUES(?,?,?)",
                   (username, pw_hash, 'student'))
        db.commit()
        user = db.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
        db.execute("INSERT INTO students(id,full_name,email) VALUES(?,?,?)",
                   (user['id'], full_name, email))
        db.commit()
        session['user_id'] = user['id']
        session['username'] = username
        session['role'] = 'student'
        return jsonify({'message': 'Registered successfully', 'role': 'student', 'user_id': user['id']}), 201
    except sqlite3.IntegrityError as e:
        return jsonify({'error': 'Username or email already exists'}), 409
    finally:
        db.close()

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.get_json()
    username = (data.get('username') or '').strip()
    password = (data.get('password') or '').strip()
    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400

    db = get_db()
    try:
        user = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        if not user or not check_password_hash(user['password_hash'], password):
            return jsonify({'error': 'Invalid credentials'}), 401
        session['user_id'] = user['id']
        session['username'] = user['username']
        session['role'] = user['role']
        return jsonify({'message': 'Login successful', 'role': user['role'], 'user_id': user['id']})
    finally:
        db.close()

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'message': 'Logged out'})

@app.route('/api/auth/me', methods=['GET'])
def me():
    if 'user_id' not in session:
        return jsonify({'logged_in': False})
    
    db = get_db()
    try:
        full_name = None
        if session['role'] == 'student':
            student = db.execute("SELECT full_name FROM students WHERE id=?", (session['user_id'],)).fetchone()
            if student:
                full_name = student['full_name']
        elif session['role'] == 'admin':
            full_name = session.get('username', 'Admin')
        return jsonify({
            'logged_in': True,
            'user_id': session['user_id'],
            'username': session['username'],
            'role': session['role'],
            'full_name': full_name
        })
    finally:
        db.close()

@app.route('/api/auth/change-password', methods=['PUT'])
def change_own_password():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.get_json() or {}
    current_pw = (data.get('current_password') or '').strip()
    new_pw = (data.get('new_password') or '').strip()
    
    if not current_pw or not new_pw:
        return jsonify({'error': 'Current and new password are required'}), 400
    if len(new_pw) < 6:
        return jsonify({'error': 'Password must be at least 6 characters'}), 400
        
    db = get_db()
    try:
        user = db.execute("SELECT password_hash FROM users WHERE id=?", (session['user_id'],)).fetchone()
        if not user or not check_password_hash(user['password_hash'], current_pw):
            return jsonify({'error': 'Invalid current password'}), 400
            
        new_hash = generate_password_hash(new_pw)
        db.execute("UPDATE users SET password_hash=? WHERE id=?", (new_hash, session['user_id']))
        db.commit()
        return jsonify({'message': 'Password changed successfully'})
    finally:
        db.close()

@app.route('/api/student/profile', methods=['GET'])
@student_required
def get_profile():
    db = get_db()
    try:
        student = db.execute("SELECT * FROM students WHERE id=?", (session['user_id'],)).fetchone()
        if not student:
            return jsonify({'error': 'Profile not found'}), 404
        skills = get_student_skills(session['user_id'], db)
        return jsonify({**dict(student), 'skills': skills})
    finally:
        db.close()

@app.route('/api/student/profile', methods=['PUT'])
@student_required
def update_profile():
    data = request.get_json()
    db = get_db()
    try:
        db.execute("""UPDATE students SET full_name=?,email=?,phone=?,college=?,
            department=?,cgpa=?,grad_year=? WHERE id=?""",
            (data.get('full_name',''), data.get('email',''), data.get('phone',''),
             data.get('college',''), data.get('department',''),
             data.get('cgpa', 0), data.get('grad_year', 0), session['user_id']))
        db.commit()
        return jsonify({'message': 'Profile updated'})
    finally:
        db.close()

@app.route('/api/student/resume', methods=['POST'])
@student_required
def upload_resume():
    if 'resume' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    file = request.files['resume']
    if file.filename == '' or not allowed_file(file.filename):
        return jsonify({'error': 'Invalid file. Only PDF allowed'}), 400
    filename = f"resume_{session['user_id']}_{secure_filename(file.filename)}"
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    db = get_db()
    try:
        db.execute("UPDATE students SET resume_path=? WHERE id=?", (filename, session['user_id']))
        db.commit()
        return jsonify({'message': 'Resume uploaded', 'resume_path': filename})
    finally:
        db.close()

@app.route('/api/student/skills', methods=['GET'])
@student_required
def get_skills():
    db = get_db()
    try:
        skills = get_student_skills(session['user_id'], db)
        return jsonify(skills)
    finally:
        db.close()

@app.route('/api/student/skills', methods=['POST'])
@student_required
def add_skill():
    data = request.get_json()
    skill = (data.get('skill') or '').strip()
    if not skill:
        return jsonify({'error': 'Skill name required'}), 400
    db = get_db()
    try:
        db.execute("INSERT OR IGNORE INTO student_skills(student_id,skill_name) VALUES(?,?)",
                   (session['user_id'], skill))
        db.commit()
        return jsonify({'message': 'Skill added'})
    finally:
        db.close()

@app.route('/api/student/skills/<skill_name>', methods=['DELETE'])
@student_required
def delete_skill(skill_name):
    db = get_db()
    try:
        db.execute("DELETE FROM student_skills WHERE student_id=? AND skill_name=?",
                   (session['user_id'], skill_name))
        db.commit()
        return jsonify({'message': 'Skill removed'})
    finally:
        db.close()

@app.route('/api/internships', methods=['GET'])
def get_internships():
    db = get_db()
    try:
        q = "SELECT i.*, c.name as company_name, c.location as company_location FROM internships i LEFT JOIN companies c ON i.company_id=c.id WHERE 1=1"
        params = []
        skill_filter = request.args.get('skill', '').strip()
        location_filter = request.args.get('location', '').strip()
        company_filter = request.args.get('company', '').strip()
        mode_filter = request.args.get('work_mode', '').strip()
        if skill_filter:
            q += " AND i.skills_required LIKE ?"
            params.append(f'%{skill_filter}%')
        if location_filter:
            q += " AND (i.location LIKE ? OR c.location LIKE ?)"
            params.extend([f'%{location_filter}%', f'%{location_filter}%'])
        if company_filter:
            q += " AND c.name LIKE ?"
            params.append(f'%{company_filter}%')
        if mode_filter:
            q += " AND i.work_mode=?"
            params.append(mode_filter)
        rows = db.execute(q, params).fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        db.close()

@app.route('/api/internships/<int:iid>', methods=['GET'])
def get_internship(iid):
    db = get_db()
    try:
        row = db.execute("SELECT i.*, c.name as company_name FROM internships i LEFT JOIN companies c ON i.company_id=c.id WHERE i.id=?", (iid,)).fetchone()
        if not row:
            return jsonify({'error': 'Not found'}), 404
        return jsonify(dict(row))
    finally:
        db.close()

@app.route('/api/student/applications', methods=['GET'])
@student_required
def get_my_applications():
    db = get_db()
    try:
        rows = db.execute("""SELECT a.*, i.title, i.skills_required, i.location,
            i.work_mode, i.stipend, i.deadline, c.name as company_name
            FROM applications a
            JOIN internships i ON a.internship_id=i.id
            LEFT JOIN companies c ON i.company_id=c.id
            WHERE a.student_id=?
            ORDER BY a.applied_date DESC""", (session['user_id'],)).fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        db.close()

@app.route('/api/student/apply/<int:internship_id>', methods=['POST'])
@student_required
def apply_internship(internship_id):
    data = request.get_json() or {}
    status = data.get('status', 'applied')
    if status not in ('saved', 'applied'):
        status = 'applied'
    db = get_db()
    try:
        existing = db.execute("SELECT id, status FROM applications WHERE student_id=? AND internship_id=?",
                              (session['user_id'], internship_id)).fetchone()
        if existing:
            return jsonify({'message': 'Already applied', 'status': existing['status']}), 200
        db.execute("INSERT INTO applications(student_id,internship_id,status) VALUES(?,?,?)",
                   (session['user_id'], internship_id, status))
        db.commit()
        return jsonify({'message': f'Internship {status}'}), 201
    finally:
        db.close()

@app.route('/api/student/recommendations', methods=['GET'])
@student_required
def get_recommendations():
    db = get_db()
    try:
        skills = get_student_skills(session['user_id'], db)
        internships = db.execute("""SELECT i.*, c.name as company_name
            FROM internships i LEFT JOIN companies c ON i.company_id=c.id""").fetchall()
        results = []
        for intern in internships:
            score = compute_match_score(skills, intern['skills_required'])
            level = get_recommendation_level(score)
            req_skills = [s.strip() for s in intern['skills_required'].split(',') if s.strip()]
            student_set = set(s.lower() for s in skills)
            matched = [s for s in req_skills if s.lower() in student_set]
            missing = [s for s in req_skills if s.lower() not in student_set]
            results.append({**dict(intern), 'match_score': score, 'match_level': level,
                            'matched_skills': matched, 'missing_skills': missing})
        results.sort(key=lambda x: x['match_score'], reverse=True)
        return jsonify(results)
    finally:
        db.close()

@app.route('/api/student/career-analysis', methods=['GET'])
@student_required
def career_analysis():
    db = get_db()
    try:
        skills = get_student_skills(session['user_id'], db)
        student_set = set(s.lower() for s in skills)
        paths = db.execute("SELECT * FROM career_paths").fetchall()
        results = []
        for path in paths:
            req = [s.strip() for s in path['skills_required'].split(',') if s.strip()]
            req_lower = set(s.lower() for s in req)
            matched = [s for s in req if s.lower() in student_set]
            missing = [s for s in req if s.lower() not in student_set]
            score = round((len(matched) / len(req)) * 100) if req else 0
            certs = db.execute("SELECT * FROM certifications WHERE career_path_id=?",
                               (path['id'],)).fetchall()
            relevant_certs = []
            for cert in certs:
                relevant_certs.append(dict(cert))
            results.append({
                'id': path['id'],
                'title': path['title'],
                'description': path['description'],
                'skills_required': req,
                'matched_skills': matched,
                'missing_skills': missing,
                'readiness_score': score,
                'certifications': relevant_certs
            })
        results.sort(key=lambda x: x['readiness_score'], reverse=True)
        return jsonify(results)
    finally:
        db.close()

@app.route('/api/student/dashboard', methods=['GET'])
@student_required
def student_dashboard():
    db = get_db()
    try:
        uid = session['user_id']
        total_apps = db.execute("SELECT COUNT(*) as cnt FROM applications WHERE student_id=?", (uid,)).fetchone()['cnt']
        selected = db.execute("SELECT COUNT(*) as cnt FROM applications WHERE student_id=? AND status='selected'", (uid,)).fetchone()['cnt']
        interviews = db.execute("SELECT COUNT(*) as cnt FROM applications WHERE student_id=? AND status='interview_scheduled'", (uid,)).fetchone()['cnt']
        saved = db.execute("SELECT COUNT(*) as cnt FROM applications WHERE student_id=? AND status='saved'", (uid,)).fetchone()['cnt']
        skills_count = db.execute("SELECT COUNT(*) as cnt FROM student_skills WHERE student_id=?", (uid,)).fetchone()['cnt']
        return jsonify({
            'total_applications': total_apps,
            'selected': selected,
            'interviews': interviews,
            'saved': saved,
            'skills_count': skills_count
        })
    finally:
        db.close()

@app.route('/api/admin/dashboard', methods=['GET'])
@admin_required
def admin_dashboard():
    db = get_db()
    try:
        total_students = db.execute("SELECT COUNT(*) as cnt FROM students").fetchone()['cnt']
        total_companies = db.execute("SELECT COUNT(*) as cnt FROM companies").fetchone()['cnt']
        total_internships = db.execute("SELECT COUNT(*) as cnt FROM internships").fetchone()['cnt']
        total_applications = db.execute("SELECT COUNT(*) as cnt FROM applications").fetchone()['cnt']
        selected_count = db.execute("SELECT COUNT(*) as cnt FROM applications WHERE status='selected'").fetchone()['cnt']
        active_internships = db.execute("SELECT COUNT(*) as cnt FROM internships WHERE deadline >= date('now')").fetchone()['cnt']
        status_rows = db.execute("SELECT status, COUNT(*) as cnt FROM applications GROUP BY status").fetchall()
        status_data = {r['status']: r['cnt'] for r in status_rows}
        recent_students = db.execute("""SELECT s.full_name, s.email, s.college, s.department, s.created_at
            FROM students s ORDER BY s.created_at DESC LIMIT 5""").fetchall()
        return jsonify({
            'total_students': total_students,
            'total_companies': total_companies,
            'total_internships': total_internships,
            'total_applications': total_applications,
            'selected_students': selected_count,
            'active_internships': active_internships,
            'applications_by_status': status_data,
            'recent_students': [dict(r) for r in recent_students]
        })
    finally:
        db.close()

@app.route('/api/admin/students', methods=['GET'])
@admin_required
def admin_get_students():
    db = get_db()
    try:
        search = request.args.get('search', '').strip()
        q = "SELECT s.*, GROUP_CONCAT(ss.skill_name, ', ') as skills FROM students s LEFT JOIN student_skills ss ON s.id=ss.student_id"
        params = []
        if search:
            q += " WHERE s.full_name LIKE ? OR s.email LIKE ? OR s.college LIKE ?"
            params.extend([f'%{search}%', f'%{search}%', f'%{search}%'])
        q += " GROUP BY s.id ORDER BY s.created_at DESC"
        rows = db.execute(q, params).fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        db.close()

@app.route('/api/admin/students/<int:sid>', methods=['GET'])
@admin_required
def admin_get_student(sid):
    db = get_db()
    try:
        student = db.execute("SELECT * FROM students WHERE id=?", (sid,)).fetchone()
        if not student:
            return jsonify({'error': 'Not found'}), 404
        skills = get_student_skills(sid, db)
        return jsonify({**dict(student), 'skills': skills})
    finally:
        db.close()

@app.route('/api/admin/students/<int:sid>', methods=['PUT'])
@admin_required
def admin_update_student(sid):
    data = request.get_json()
    db = get_db()
    try:
        db.execute("""UPDATE students SET full_name=?,email=?,phone=?,college=?,department=?,cgpa=?,grad_year=?
            WHERE id=?""",
            (data.get('full_name',''), data.get('email',''), data.get('phone',''),
             data.get('college',''), data.get('department',''),
             data.get('cgpa', 0), data.get('grad_year', 0), sid))
        db.commit()
        return jsonify({'message': 'Student updated'})
    finally:
        db.close()

@app.route('/api/admin/students/<int:sid>', methods=['DELETE'])
@admin_required
def admin_delete_student(sid):
    db = get_db()
    try:
        db.execute("DELETE FROM students WHERE id=?", (sid,))
        db.execute("DELETE FROM users WHERE id=?", (sid,))
        db.commit()
        return jsonify({'message': 'Student deleted'})
    finally:
        db.close()

@app.route('/api/admin/profile', methods=['GET'])
@admin_required
def admin_get_profile():
    db = get_db()
    try:
        user = db.execute("SELECT id, username, full_name, email, phone, department, created_at FROM users WHERE id=?", (session['user_id'],)).fetchone()
        if not user:
            return jsonify({'error': 'Profile not found'}), 404
        return jsonify({
            'id': user['id'],
            'username': user['username'],
            'full_name': user['full_name'] or '',
            'email': user['email'] or '',
            'phone': user['phone'] or '',
            'department': user['department'] or '',
            'created_at': user['created_at']
        })
    finally:
        db.close()

@app.route('/api/admin/profile', methods=['PUT'])
@admin_required
def admin_update_profile():
    data = request.get_json() or {}
    db = get_db()
    try:
        db.execute("""UPDATE users SET full_name=?, email=?, phone=?, department=?
            WHERE id=?""",
            (data.get('full_name',''), data.get('email',''),
             data.get('phone',''), data.get('department',''), session['user_id']))
        db.commit()
        return jsonify({'message': 'Admin profile updated'})
    finally:
        db.close()

@app.route('/api/admin/companies', methods=['GET'])
@admin_required
def admin_get_companies():
    db = get_db()
    try:
        rows = db.execute("SELECT * FROM companies ORDER BY created_at DESC").fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        db.close()

@app.route('/api/admin/companies', methods=['POST'])
@admin_required
def admin_add_company():
    data = request.get_json()
    if not data.get('name', '').strip():
        return jsonify({'error': 'Company name required'}), 400
    db = get_db()
    try:
        db.execute("INSERT INTO companies(name,website,industry,location,description) VALUES(?,?,?,?,?)",
                   (data['name'], data.get('website',''), data.get('industry',''),
                    data.get('location',''), data.get('description','')))
        db.commit()
        return jsonify({'message': 'Company added'}), 201
    finally:
        db.close()

@app.route('/api/admin/companies/<int:cid>', methods=['PUT'])
@admin_required
def admin_update_company(cid):
    data = request.get_json()
    db = get_db()
    try:
        db.execute("UPDATE companies SET name=?,website=?,industry=?,location=?,description=? WHERE id=?",
                   (data.get('name',''), data.get('website',''), data.get('industry',''),
                    data.get('location',''), data.get('description',''), cid))
        db.commit()
        return jsonify({'message': 'Company updated'})
    finally:
        db.close()

@app.route('/api/admin/companies/<int:cid>', methods=['DELETE'])
@admin_required
def admin_delete_company(cid):
    db = get_db()
    try:
        db.execute("DELETE FROM companies WHERE id=?", (cid,))
        db.commit()
        return jsonify({'message': 'Company deleted'})
    finally:
        db.close()

@app.route('/api/admin/internships', methods=['GET'])
@admin_required
def admin_get_internships():
    db = get_db()
    try:
        rows = db.execute("""SELECT i.*, c.name as company_name FROM internships i
            LEFT JOIN companies c ON i.company_id=c.id ORDER BY i.created_at DESC""").fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        db.close()

@app.route('/api/admin/internships', methods=['POST'])
@admin_required
def admin_add_internship():
    data = request.get_json()
    if not data.get('title', '').strip():
        return jsonify({'error': 'Title required'}), 400
    db = get_db()
    try:
        db.execute("""INSERT INTO internships(company_id,title,skills_required,location,duration,work_mode,stipend,deadline,description)
            VALUES(?,?,?,?,?,?,?,?,?)""",
            (data.get('company_id'), data['title'], data.get('skills_required',''),
             data.get('location',''), data.get('duration',''), data.get('work_mode','remote'),
             data.get('stipend', 0), data.get('deadline',''), data.get('description','')))
        db.commit()
        return jsonify({'message': 'Internship created'}), 201
    finally:
        db.close()

@app.route('/api/admin/internships/<int:iid>', methods=['PUT'])
@admin_required
def admin_update_internship(iid):
    data = request.get_json()
    db = get_db()
    try:
        db.execute("""UPDATE internships SET company_id=?,title=?,skills_required=?,location=?,
            duration=?,work_mode=?,stipend=?,deadline=?,description=? WHERE id=?""",
            (data.get('company_id'), data.get('title',''), data.get('skills_required',''),
             data.get('location',''), data.get('duration',''), data.get('work_mode','remote'),
             data.get('stipend', 0), data.get('deadline',''), data.get('description',''), iid))
        db.commit()
        return jsonify({'message': 'Internship updated'})
    finally:
        db.close()

@app.route('/api/admin/internships/<int:iid>', methods=['DELETE'])
@admin_required
def admin_delete_internship(iid):
    db = get_db()
    try:
        db.execute("DELETE FROM internships WHERE id=?", (iid,))
        db.commit()
        return jsonify({'message': 'Internship deleted'})
    finally:
        db.close()

@app.route('/api/admin/internships/<int:iid>/matches', methods=['GET'])
@admin_required
def admin_get_internship_matches(iid):
    db = get_db()
    try:
        intern = db.execute("SELECT * FROM internships WHERE id=?", (iid,)).fetchone()
        if not intern:
            return jsonify({'error': 'Internship not found'}), 404
        students = db.execute("SELECT s.* FROM students s").fetchall()
        results = []
        for s in students:
            skills = get_student_skills(s['id'], db)
            score = compute_match_score(skills, intern['skills_required'])
            results.append({
                'id': s['id'],
                'full_name': s['full_name'],
                'email': s['email'],
                'college': s['college'],
                'cgpa': s['cgpa'],
                'match_score': score,
                'skills': skills
            })
        results.sort(key=lambda x: x['match_score'], reverse=True)
        return jsonify(results)
    finally:
        db.close()

@app.route('/api/admin/applications', methods=['GET'])
@admin_required
def admin_get_applications():
    db = get_db()
    try:
        search = request.args.get('search', '').strip()
        status_filter = request.args.get('status', '').strip()
        q = """SELECT a.id, a.status, a.applied_date, a.updated_at,
            s.full_name as student_name, s.email as student_email,
            i.title as internship_title, c.name as company_name
            FROM applications a
            JOIN students s ON a.student_id=s.id
            JOIN internships i ON a.internship_id=i.id
            LEFT JOIN companies c ON i.company_id=c.id WHERE 1=1"""
        params = []
        if search:
            q += " AND (s.full_name LIKE ? OR i.title LIKE ? OR c.name LIKE ?)"
            params.extend([f'%{search}%', f'%{search}%', f'%{search}%'])
        if status_filter:
            q += " AND a.status=?"
            params.append(status_filter)
        q += " ORDER BY a.applied_date DESC"
        rows = db.execute(q, params).fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        db.close()

@app.route('/api/admin/applications/<int:aid>/status', methods=['PUT'])
@admin_required
def admin_update_application_status(aid):
    data = request.get_json() or {}
    new_status = data.get('status', '')
    valid = ('saved', 'applied', 'under_review', 'interview_scheduled', 'selected', 'rejected')
    if new_status not in valid:
        return jsonify({'error': 'Invalid status'}), 400
    db = get_db()
    try:
        if new_status == 'interview_scheduled':
            db.execute("""UPDATE applications SET status=?, interview_date=?, interview_time=?, interview_message=?, updated_at=datetime('now')
                WHERE id=?""", (new_status, data.get('interview_date',''), data.get('interview_time',''), data.get('interview_message',''), aid))
        else:
            db.execute("UPDATE applications SET status=?, updated_at=datetime('now') WHERE id=?", (new_status, aid))
        db.commit()
        return jsonify({'message': 'Status updated'})
    finally:
        db.close()

def make_csv_response(headers, rows, filename):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    writer.writerows(rows)
    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8-sig')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=filename
    )

@app.route('/api/admin/reports/students', methods=['GET'])
@admin_required
def report_students():
    db = get_db()
    try:
        rows = db.execute("""SELECT s.full_name, s.email, s.phone, s.college, s.department,
            s.cgpa, s.grad_year, s.resume_path, s.created_at,
            GROUP_CONCAT(ss.skill_name, ', ') as skills
            FROM students s LEFT JOIN student_skills ss ON s.id=ss.student_id
            GROUP BY s.id ORDER BY s.created_at DESC""").fetchall()
        headers = ['Full Name', 'Email', 'Phone', 'College', 'Department', 'CGPA', 'Grad Year', 'Resume', 'Registered At', 'Skills']
        data = [[r['full_name'], r['email'], r['phone'], r['college'], r['department'],
                 r['cgpa'], r['grad_year'], r['resume_path'], r['created_at'], r['skills']] for r in rows]
        return make_csv_response(headers, data, 'students_report.csv')
    finally:
        db.close()

@app.route('/api/admin/reports/internships', methods=['GET'])
@admin_required
def report_internships():
    db = get_db()
    try:
        rows = db.execute("""SELECT i.title, c.name as company, i.skills_required, i.location,
            i.duration, i.work_mode, i.stipend, i.deadline, i.description, i.created_at
            FROM internships i LEFT JOIN companies c ON i.company_id=c.id
            ORDER BY i.created_at DESC""").fetchall()
        headers = ['Title', 'Company', 'Skills Required', 'Location', 'Duration', 'Work Mode', 'Stipend', 'Deadline', 'Description', 'Created At']
        data = [[r['title'], r['company'], r['skills_required'], r['location'], r['duration'],
                 r['work_mode'], r['stipend'], r['deadline'], r['description'], r['created_at']] for r in rows]
        return make_csv_response(headers, data, 'internships_report.csv')
    finally:
        db.close()

@app.route('/api/admin/reports/applications', methods=['GET'])
@admin_required
def report_applications():
    db = get_db()
    try:
        rows = db.execute("""SELECT s.full_name, s.email, i.title, c.name as company,
            a.status, a.applied_date, a.updated_at
            FROM applications a
            JOIN students s ON a.student_id=s.id
            JOIN internships i ON a.internship_id=i.id
            LEFT JOIN companies c ON i.company_id=c.id
            ORDER BY a.applied_date DESC""").fetchall()
        headers = ['Student Name', 'Email', 'Internship', 'Company', 'Status', 'Applied Date', 'Last Updated']
        data = [[r['full_name'], r['email'], r['title'], r['company'],
                 r['status'], r['applied_date'], r['updated_at']] for r in rows]
        return make_csv_response(headers, data, 'applications_report.csv')
    finally:
        db.close()

@app.route('/api/admin/reports/skillgap', methods=['GET'])
@admin_required
def report_skillgap():
    db = get_db()
    try:
        students = db.execute("SELECT s.id, s.full_name, s.college FROM students s").fetchall()
        paths = db.execute("SELECT * FROM career_paths").fetchall()
        headers = ['Student Name', 'College', 'Career Path', 'Readiness Score (%)', 'Missing Skills']
        data = []
        for student in students:
            skills = get_student_skills(student['id'], db)
            student_set = set(s.lower() for s in skills)
            for path in paths:
                req = [s.strip() for s in path['skills_required'].split(',') if s.strip()]
                missing = [s for s in req if s.lower() not in student_set]
                score = round(((len(req) - len(missing)) / len(req)) * 100) if req else 0
                data.append([student['full_name'], student['college'], path['title'], score, ', '.join(missing)])
        return make_csv_response(headers, data, 'skillgap_report.csv')
    finally:
        db.close()

if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5000)