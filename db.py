import sqlite3
import os
from werkzeug.security import generate_password_hash

DB_PATH = os.path.join(os.path.dirname(__file__), 'internship_tracker.db')
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    conn = get_db()
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT CHECK(role IN ('admin','student')) NOT NULL DEFAULT 'student',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS students (
        id INTEGER PRIMARY KEY,
        full_name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        phone TEXT DEFAULT '',
        college TEXT DEFAULT '',
        department TEXT DEFAULT '',
        cgpa REAL DEFAULT 0.0,
        grad_year INTEGER DEFAULT 0,
        resume_path TEXT DEFAULT '',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(id) REFERENCES users(id) ON DELETE CASCADE
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS companies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        website TEXT DEFAULT '',
        industry TEXT DEFAULT '',
        location TEXT DEFAULT '',
        description TEXT DEFAULT '',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS internships (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER,
        title TEXT NOT NULL,
        skills_required TEXT NOT NULL DEFAULT '',
        location TEXT DEFAULT '',
        duration TEXT DEFAULT '',
        work_mode TEXT CHECK(work_mode IN ('remote','hybrid','on-site')) NOT NULL DEFAULT 'remote',
        stipend REAL DEFAULT 0,
        deadline TEXT DEFAULT '',
        description TEXT DEFAULT '',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(company_id) REFERENCES companies(id) ON DELETE CASCADE
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS skills (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS student_skills (
        student_id INTEGER,
        skill_name TEXT NOT NULL,
        PRIMARY KEY(student_id, skill_name),
        FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE CASCADE
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS applications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER,
        internship_id INTEGER,
        status TEXT CHECK(status IN ('saved','applied','under_review','interview_scheduled','selected','rejected')) DEFAULT 'applied',
        applied_date DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(student_id, internship_id),
        FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE CASCADE,
        FOREIGN KEY(internship_id) REFERENCES internships(id) ON DELETE CASCADE
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS career_paths (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT UNIQUE NOT NULL,
        skills_required TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT ''
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS certifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        career_path_id INTEGER,
        name TEXT NOT NULL,
        provider TEXT NOT NULL,
        course_url TEXT DEFAULT '',
        FOREIGN KEY(career_path_id) REFERENCES career_paths(id) ON DELETE CASCADE
    )''')

    conn.commit()

    try:
        c.execute("ALTER TABLE users ADD COLUMN full_name TEXT DEFAULT ''")
        c.execute("ALTER TABLE users ADD COLUMN email TEXT DEFAULT ''")
        c.execute("ALTER TABLE users ADD COLUMN phone TEXT DEFAULT ''")
        c.execute("ALTER TABLE users ADD COLUMN department TEXT DEFAULT ''")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    try:
        c.execute("ALTER TABLE applications ADD COLUMN interview_date TEXT")
        c.execute("ALTER TABLE applications ADD COLUMN interview_time TEXT")
        c.execute("ALTER TABLE applications ADD COLUMN interview_message TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    existing_admin = c.execute("SELECT id FROM users WHERE username='admin'").fetchone()
    if not existing_admin:
        pw = generate_password_hash('admin123')
        c.execute("INSERT INTO users(username,password_hash,role) VALUES(?,?,?)", ('admin', pw, 'admin'))
        conn.commit()

    career_paths = [
        ('Frontend Developer', 'HTML,CSS,JavaScript,React,Tailwind,Git',
         'Build beautiful user interfaces and web experiences using modern frontend technologies.'),
        ('Backend Developer', 'Python,SQL,REST API,Git,Django,Flask',
         'Design and build robust server-side systems, APIs, and databases.'),
        ('Full Stack Developer', 'HTML,CSS,JavaScript,React,Python,Flask,SQL,Git',
         'Handle both frontend and backend development for end-to-end web applications.'),
        ('Data Analyst', 'Python,SQL,Excel,Pandas,Tableau,Data Visualization',
         'Analyze data to uncover insights and drive data-driven decisions.'),
        ('Python Developer', 'Python,SQL,Flask,Git,Django,REST API',
         'Build scalable applications and automate workflows using Python.'),
        ('AI Engineer', 'Python,SQL,PyTorch,TensorFlow,Machine Learning,Git,Scikit-learn',
         'Design and deploy machine learning and AI systems at scale.'),
    ]
    for title, skills, desc in career_paths:
        c.execute("INSERT OR IGNORE INTO career_paths(title,skills_required,description) VALUES(?,?,?)",
                  (title, skills, desc))
    conn.commit()

    certs = {
        'Frontend Developer': [
            ('The Complete Web Developer Bootcamp', 'Udemy', 'https://udemy.com/course/the-complete-web-development-bootcamp'),
            ('JavaScript Algorithms and Data Structures', 'freeCodeCamp', 'https://freecodecamp.org/learn/javascript-algorithms-and-data-structures'),
            ('React - The Complete Guide', 'Udemy', 'https://udemy.com/course/react-the-complete-guide-incl-redux'),
        ],
        'Backend Developer': [
            ('Python and Django Full Stack Web Developer Bootcamp', 'Udemy', 'https://udemy.com/course/python-and-django-full-stack-web-developer-bootcamp'),
            ('REST APIs with Flask and Python', 'Udemy', 'https://udemy.com/course/rest-api-flask-and-python'),
            ('SQL and Database Design A-Z', 'Udemy', 'https://udemy.com/course/sqldatabases'),
        ],
        'Full Stack Developer': [
            ('Full Stack Open', 'University of Helsinki', 'https://fullstackopen.com/en'),
            ('The Web Developer Bootcamp', 'Udemy', 'https://udemy.com/course/the-web-developer-bootcamp'),
            ('CS50 Web Programming with Python and JavaScript', 'Harvard / edX', 'https://cs50.harvard.edu/web'),
        ],
        'Data Analyst': [
            ('Google Data Analytics Certificate', 'Google / Coursera', 'https://coursera.org/professional-certificates/google-data-analytics'),
            ('Python for Data Science and Machine Learning Bootcamp', 'Udemy', 'https://udemy.com/course/python-for-data-science-and-machine-learning-bootcamp'),
            ('SQL for Data Science', 'Coursera', 'https://coursera.org/learn/sql-for-data-science'),
        ],
        'Python Developer': [
            ('100 Days of Code - The Complete Python Pro Bootcamp', 'Udemy', 'https://udemy.com/course/100-days-of-code'),
            ('Python Mega Course: Learn Python in 60 Days', 'Udemy', 'https://udemy.com/course/the-python-mega-course'),
            ('Flask Mega-Tutorial', 'Miguel Grinberg', 'https://blog.miguelgrinberg.com/post/the-flask-mega-tutorial-part-i-hello-world'),
        ],
        'AI Engineer': [
            ('Machine Learning Specialization', 'DeepLearning.AI / Coursera', 'https://coursera.org/specializations/machine-learning-introduction'),
            ('Deep Learning Specialization', 'DeepLearning.AI / Coursera', 'https://coursera.org/specializations/deep-learning'),
            ('Practical Deep Learning for Coders', 'fast.ai', 'https://course.fast.ai'),
        ],
    }
    for path_title, path_certs in certs.items():
        path_row = c.execute("SELECT id FROM career_paths WHERE title=?", (path_title,)).fetchone()
        if path_row:
            pid = path_row['id']
            for name, provider, url in path_certs:
                c.execute("INSERT OR IGNORE INTO certifications(career_path_id,name,provider,course_url) VALUES(?,?,?,?)",
                          (pid, name, provider, url))
    conn.commit()

    sample_companies = [
        ('Zoho Corporation', 'https://zoho.com', 'Enterprise Software', 'Chennai', 'Cloud software suite developer and enterprise solution provider.'),
        ('Cognizant Technology Solutions (CTS)', 'https://cognizant.com', 'IT Services', 'Chennai', 'Global technology services consulting company.'),
        ('Tata Consultancy Services (TCS)', 'https://tcs.com', 'IT Services', 'Chennai', 'Largest IT consultancy and services firm in India.'),
        ('AI Nexus Labs', 'https://ainexus.ai', 'Artificial Intelligence', 'Chennai', 'Research and applied AI company.'),
        ('HCL Technologies', 'https://hcltech.com', 'IT Services', 'Chennai', 'Global IT enterprise service provider.'),
    ]
    for name, website, industry, loc, desc in sample_companies:
        c.execute("INSERT OR IGNORE INTO companies(name,website,industry,location,description) VALUES(?,?,?,?,?)",
                  (name, website, industry, loc, desc))
    conn.commit()

    company_ids = {row['name']: row['id'] for row in c.execute("SELECT id, name FROM companies").fetchall()}
    sample_internships = [
        (company_ids.get('Zoho Corporation'), 'Python Backend Developer Intern', 'Python,Flask,SQL,Git', 'Chennai', '3 months', 'hybrid', 15000, '2026-08-31', 'Build REST APIs and backend services using Flask and SQLite.'),
        (company_ids.get('Zoho Corporation'), 'Frontend Web Developer Intern', 'HTML,CSS,JavaScript,React,Git', 'Chennai', '2 months', 'remote', 10000, '2026-07-31', 'Develop responsive UI components using React and Tailwind.'),
        (company_ids.get('Cognizant Technology Solutions (CTS)'), 'Data Analyst Intern', 'Python,SQL,Pandas,Tableau,Excel', 'Chennai', '3 months', 'on-site', 12000, '2026-09-01', 'Analyze large datasets and build dashboards using Tableau.'),
        (company_ids.get('Tata Consultancy Services (TCS)'), 'Full Stack Developer Intern', 'HTML,CSS,JavaScript,Python,Flask,SQL', 'Chennai', '4 months', 'hybrid', 18000, '2026-08-15', 'Work on cloud-native full stack applications.'),
        (company_ids.get('AI Nexus Labs'), 'AI/ML Research Intern', 'Python,Machine Learning,TensorFlow,SQL,Git', 'Chennai', '6 months', 'on-site', 20000, '2026-10-01', 'Research and implement ML models for NLP tasks.'),
        (company_ids.get('HCL Technologies'), 'React Developer Intern', 'JavaScript,React,CSS,HTML,Git', 'Chennai', '2 months', 'remote', 8000, '2026-07-15', 'Build interactive web apps and landing pages with React.'),
        (company_ids.get('Cognizant Technology Solutions (CTS)'), 'SQL & BI Analyst Intern', 'SQL,Excel,Tableau,Data Visualization', 'Chennai', '2 months', 'remote', 10000, '2026-07-30', 'Design SQL queries and BI reports for business insights.'),
        (company_ids.get('AI Nexus Labs'), 'Python Data Science Intern', 'Python,Pandas,SQL,Scikit-learn,Git', 'Chennai', '3 months', 'hybrid', 14000, '2026-09-15', 'Apply machine learning techniques on real-world datasets.'),
    ]
    for internship in sample_internships:
        if internship[0]:
            c.execute("""INSERT OR IGNORE INTO internships
                (company_id,title,skills_required,location,duration,work_mode,stipend,deadline,description)
                VALUES(?,?,?,?,?,?,?,?,?)""", internship)
    conn.commit()
    conn.close()
    print("Database initialized successfully.")

if __name__ == '__main__':
    init_db()