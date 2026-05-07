from flask import Flask, jsonify, request
from flask_cors import CORS
import sqlite3
import os
from datetime import datetime
import json
import base64
import face_recognition
import cv2
import numpy as np
from PIL import Image
import io

app = Flask(__name__)
CORS(app)

app.config['SECRET_KEY'] = 'your-secret-key-here'
app.config['DATABASE'] = 'attendance.db'

def get_db():
    """Get database connection"""
    conn = sqlite3.connect(app.config['DATABASE'])
    conn.row_factory = sqlite3.Row  # This enables column access by name
    return conn

def init_db():
    """Initialize database tables"""
    conn = get_db()
    cursor = conn.cursor()
    
    # Create students table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            class_name TEXT NOT NULL,
            section TEXT,
            department TEXT,
            face_encoding TEXT,  -- Will store face encoding as JSON
            has_face INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create attendance table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT NOT NULL,
            name TEXT NOT NULL,
            class_name TEXT NOT NULL,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            status TEXT DEFAULT 'present',
            FOREIGN KEY (student_id) REFERENCES students (student_id)
        )
    ''')
    
    # Create admin table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admin (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Insert default admin (username: admin, password: admin123)
    cursor.execute('''
        INSERT OR IGNORE INTO admin (username, password)
        VALUES ('admin', 'admin123')
    ''')
    
    conn.commit()
    conn.close()
    print("✅ Database initialized successfully!")

# Initialize database when app starts
with app.app_context():
    init_db()

@app.route('/')
def home():
    return jsonify({
        'message': 'Face Recognition Attendance System API',
        'status': 'online',
        'database': 'connected',
        'endpoints': {
            'health': '/api/health',
            'register': '/api/register (POST)',
            'students': '/api/students (GET)',
            'student': '/api/student/<student_id> (GET)',
            'attendance': '/api/mark-attendance (POST)',
            'attendance_records': '/api/attendance (GET)',
            'login': '/api/login (POST)',
            'detect_faces': '/api/detect-faces (POST)',
            'recognize_face': '/api/recognize-face (POST)'
        }
    })

@app.route('/api/health', methods=['GET'])
def health_check():
    # Test database connection
    try:
        conn = get_db()
        conn.execute('SELECT 1')
        conn.close()
        db_status = 'connected'
    except Exception as e:
        db_status = f'error: {str(e)}'
    
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'server': 'running',
        'database': db_status
    })

# Register new student with face
@app.route('/api/register', methods=['POST'])
def register_student():
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    required_fields = ['student_id', 'name', 'class_name']
    for field in required_fields:
        if field not in data:
            return jsonify({'error': f'Missing field: {field}'}), 400
    
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # Check if student already exists
        cursor.execute('SELECT * FROM students WHERE student_id = ?', (data['student_id'],))
        existing = cursor.fetchone()
        
        if existing:
            conn.close()
            return jsonify({'error': 'Student ID already exists'}), 400
        
        # Process face encoding if provided
        face_encoding_json = '[]'
        has_face = 0
        
        if 'face_image' in data and data['face_image']:
            try:
                # Decode base64 image
                image_data = base64.b64decode(data['face_image'].split(',')[1])
                image = Image.open(io.BytesIO(image_data))
                
                # Convert PIL image to numpy array
                image_np = np.array(image)
                
                # Convert RGB to BGR (OpenCV format)
                if len(image_np.shape) == 3 and image_np.shape[2] == 3:
                    image_np = cv2.cvtColor(image_np, cv2.COLOR_RGB2BGR)
                
                # Detect faces and get encoding
                face_locations = face_recognition.face_locations(image_np)
                
                if face_locations:
                    face_encodings = face_recognition.face_encodings(image_np, face_locations)
                    if face_encodings:
                        new_face_encoding = face_encodings[0]
                        
                        # =========================
                        # CHECK DUPLICATE FACE USING FACE DISTANCE
                        # =========================
                        cursor.execute("SELECT name, student_id, face_encoding FROM students WHERE has_face = 1")
                        existing_students = cursor.fetchall()
                        
                        duplicate_found = False
                        
                        for student in existing_students:
                            if student['face_encoding'] and student['face_encoding'] != '[]':
                                stored_encoding = np.array(json.loads(student['face_encoding']))
                                
                                # Calculate face distance (lower = more similar)
                                face_distance = face_recognition.face_distance(
                                    [stored_encoding],
                                    new_face_encoding
                                )[0]
                                
                                print(f"📊 Checking with {student['name']} ({student['student_id']}) -> Distance: {face_distance:.4f}")
                                
                                # Smaller distance = same person
                                # 0.45 or lower means same person (adjustable)
                                if face_distance < 0.45:
                                    duplicate_found = True
                                    conn.close()
                                    return jsonify({
                                        'error': 'Face already registered',
                                        'message': f"This face already belongs to {student['name']} ({student['student_id']})",
                                        'distance': float(face_distance)
                                    }), 400
                        
                        # Save face if not duplicate
                        face_encoding_json = json.dumps(new_face_encoding.tolist())
                        has_face = 1
                        print(f"✅ Face encoding captured for {data['name']} (No duplicate found)")
                    else:
                        print("⚠️ No face encoding generated")
                else:
                    print("⚠️ No face detected in image")
            except Exception as e:
                print(f"❌ Error processing face: {str(e)}")
        
        # Insert new student
        cursor.execute('''
            INSERT INTO students (student_id, name, class_name, section, department, face_encoding, has_face)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            data['student_id'],
            data['name'],
            data['class_name'],
            data.get('section', ''),
            data.get('department', ''),
            face_encoding_json,
            has_face
        ))
        
        conn.commit()
        
        # Get the inserted student
        cursor.execute('SELECT * FROM students WHERE student_id = ?', (data['student_id'],))
        new_student = dict(cursor.fetchone())
        conn.close()
        
        return jsonify({
            'message': 'Student registered successfully',
            'student': new_student,
            'face_captured': face_encoding_json != '[]'
        }), 201
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Get all students
@app.route('/api/students', methods=['GET'])
def get_students():
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM students ORDER BY created_at DESC')
        students = []
        for row in cursor.fetchall():
            student = dict(row)
            # Don't send face encoding in list view (optional)
            if 'face_encoding' in student:
                student['has_face'] = student['face_encoding'] != '[]'
                del student['face_encoding']
            students.append(student)
        
        conn.close()
        
        return jsonify({
            'total': len(students),
            'students': students
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Get specific student
@app.route('/api/student/<student_id>', methods=['GET'])
def get_student(student_id):
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM students WHERE student_id = ?', (student_id,))
        student = cursor.fetchone()
        conn.close()
        
        if student:
            student_dict = dict(student)
            return jsonify(student_dict)
        else:
            return jsonify({'error': 'Student not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Delete student
@app.route('/api/student/<student_id>', methods=['DELETE'])
def delete_student(student_id):
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # Check if student exists
        cursor.execute('SELECT * FROM students WHERE student_id = ?', (student_id,))
        if not cursor.fetchone():
            conn.close()
            return jsonify({'error': 'Student not found'}), 404
        
        # Delete student
        cursor.execute('DELETE FROM students WHERE student_id = ?', (student_id,))
        
        # Delete attendance records for this student
        cursor.execute('DELETE FROM attendance WHERE student_id = ?', (student_id,))
        
        conn.commit()
        conn.close()
        
        return jsonify({'message': 'Student deleted successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Search students
@app.route('/api/search-students', methods=['GET'])
def search_students():
    query = request.args.get('q', '')
    
    if not query:
        return jsonify({'students': []})
    
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT student_id, name, class_name, section, department 
            FROM students 
            WHERE student_id LIKE ? OR name LIKE ?
            LIMIT 10
        ''', (f'%{query}%', f'%{query}%'))
        
        students = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        return jsonify({'students': students})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Detect faces in image
@app.route('/api/detect-faces', methods=['POST'])
def detect_faces():
    data = request.get_json()
    
    if not data or 'image' not in data:
        return jsonify({'error': 'No image provided'}), 400
    
    try:
        # Decode base64 image
        image_data = base64.b64decode(data['image'].split(',')[1])
        image = Image.open(io.BytesIO(image_data))
        
        # Convert PIL image to numpy array
        image_np = np.array(image)
        
        # Convert RGB to BGR (OpenCV format)
        if len(image_np.shape) == 3 and image_np.shape[2] == 3:
            image_np = cv2.cvtColor(image_np, cv2.COLOR_RGB2BGR)
        
        # Detect faces
        face_locations = face_recognition.face_locations(image_np)
        
        # Get face encodings if faces found
        face_encodings = []
        if face_locations:
            face_encodings = face_recognition.face_encodings(image_np, face_locations)
        
        return jsonify({
            'faces_detected': len(face_locations),
            'face_locations': face_locations,
            'encodings_count': len(face_encodings),
            'message': f'Found {len(face_locations)} face(s)'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Recognize face from image
@app.route('/api/recognize-face', methods=['POST'])
def recognize_face():
    data = request.get_json()
    
    if not data or 'image' not in data:
        return jsonify({'error': 'No image provided'}), 400
    
    try:
        # Decode base64 image
        image_data = base64.b64decode(data['image'].split(',')[1])
        image = Image.open(io.BytesIO(image_data))
        
        # Convert PIL image to numpy array
        image_np = np.array(image)
        
        # Convert RGB to BGR (OpenCV format)
        if len(image_np.shape) == 3 and image_np.shape[2] == 3:
            image_np = cv2.cvtColor(image_np, cv2.COLOR_RGB2BGR)
        
        # Detect faces in the image
        face_locations = face_recognition.face_locations(image_np)
        
        if not face_locations:
            return jsonify({
                'recognized': False,
                'message': 'No face detected in image'
            })
        
        # Get encoding of the face to recognize
        face_encodings = face_recognition.face_encodings(image_np, face_locations)
        
        if not face_encodings:
            return jsonify({
                'recognized': False,
                'message': 'Could not generate face encoding'
            })
        
        unknown_encoding = face_encodings[0]
        
        # Get all students with face encodings from database
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT student_id, name, class_name, face_encoding FROM students WHERE face_encoding != "[]"')
        students = cursor.fetchall()
        conn.close()
        
        if not students:
            return jsonify({
                'recognized': False,
                'message': 'No students with face data in database'
            })
        
        # Compare with known faces
        known_encodings = []
        known_student_ids = []
        known_names = []
        known_classes = []
        
        for student in students:
            try:
                encoding_list = json.loads(student['face_encoding'])
                if encoding_list:
                    known_encodings.append(np.array(encoding_list))
                    known_student_ids.append(student['student_id'])
                    known_names.append(student['name'])
                    known_classes.append(student['class_name'])
            except:
                continue
        
        if not known_encodings:
            return jsonify({
                'recognized': False,
                'message': 'No valid face encodings in database'
            })
        
        # Compare faces using face_distance
        face_distances = face_recognition.face_distance(known_encodings, unknown_encoding)
        
        # Find the best match (lowest distance)
        best_match_index = np.argmin(face_distances)
        best_distance = face_distances[best_match_index]
        
        print(f"📊 Recognition - Best match distance: {best_distance:.4f}")
        
        # Use distance threshold (lower is better)
        # 0.45 or lower means good match
        if best_distance < 0.45:
            confidence = 1 - best_distance
            return jsonify({
                'recognized': True,
                'student_id': known_student_ids[best_match_index],
                'name': known_names[best_match_index],
                'class_name': known_classes[best_match_index],
                'confidence': float(confidence),
                'distance': float(best_distance),
                'message': f"Recognized as {known_names[best_match_index]}"
            })
        
        return jsonify({
            'recognized': False,
            'message': 'Face not recognized',
            'best_distance': float(best_distance)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Mark attendance with face recognition
@app.route('/api/mark-attendance', methods=['POST'])
def mark_attendance():
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    # If student_id is provided directly
    if 'student_id' in data:
        student_id = data['student_id']
    # If image is provided, recognize face first
    elif 'image' in data:
        # First recognize the face
        try:
            # Decode base64 image
            image_data = base64.b64decode(data['image'].split(',')[1])
            image = Image.open(io.BytesIO(image_data))
            image_np = np.array(image)
            
            if len(image_np.shape) == 3 and image_np.shape[2] == 3:
                image_np = cv2.cvtColor(image_np, cv2.COLOR_RGB2BGR)
            
            # Detect and recognize face
            face_locations = face_recognition.face_locations(image_np)
            if not face_locations:
                return jsonify({'error': 'No face detected'}), 400
            
            face_encodings = face_recognition.face_encodings(image_np, face_locations)
            if not face_encodings:
                return jsonify({'error': 'Could not generate face encoding'}), 400
            
            unknown_encoding = face_encodings[0]
            
            # Get students from database
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute('SELECT student_id, name, class_name, face_encoding FROM students WHERE face_encoding != "[]"')
            students = cursor.fetchall()
            conn.close()
            
            if not students:
                return jsonify({'error': 'No registered students with face data'}), 404
            
            # Compare faces
            known_encodings = []
            known_student_ids = []
            known_names = []
            known_classes = []
            
            for student in students:
                try:
                    encoding_list = json.loads(student['face_encoding'])
                    if encoding_list:
                        known_encodings.append(np.array(encoding_list))
                        known_student_ids.append(student['student_id'])
                        known_names.append(student['name'])
                        known_classes.append(student['class_name'])
                except:
                    continue
            
            if not known_encodings:
                return jsonify({'error': 'No valid face encodings'}), 500
            
            # Find matches using face_distance
            face_distances = face_recognition.face_distance(known_encodings, unknown_encoding)
            best_match_index = np.argmin(face_distances)
            best_distance = face_distances[best_match_index]
            
            print(f"📊 Attendance - Best match distance: {best_distance:.4f}")
            
            if best_distance < 0.45:  # Good match threshold
                student_id = known_student_ids[best_match_index]
                student_name = known_names[best_match_index]
                student_class = known_classes[best_match_index]
            else:
                return jsonify({'error': 'Face not recognized or low confidence match', 'distance': float(best_distance)}), 400
                
        except Exception as e:
            return jsonify({'error': f'Face recognition failed: {str(e)}'}), 500
    else:
        return jsonify({'error': 'Either student_id or image required'}), 400
    
    # Mark attendance
    current_date = datetime.now().strftime('%Y-%m-%d')
    current_time = datetime.now().strftime('%H:%M:%S')
    
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # If we don't have name and class yet (when student_id was provided directly)
        if 'name' not in locals():
            cursor.execute('SELECT name, class_name FROM students WHERE student_id = ?', (student_id,))
            student = cursor.fetchone()
            if not student:
                return jsonify({'error': 'Student not found'}), 404
            student_name = student['name']
            student_class = student['class_name']
        
        # Check if already marked today
        cursor.execute('''
            SELECT * FROM attendance 
            WHERE student_id = ? AND date = ?
        ''', (student_id, current_date))
        
        existing = cursor.fetchone()
        
        if existing:
            return jsonify({'error': 'Attendance already marked for today'}), 400
        
        # Mark attendance
        cursor.execute('''
            INSERT INTO attendance (student_id, name, class_name, date, time)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            student_id,
            student_name,
            student_class,
            current_date,
            current_time
        ))
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'message': 'Attendance marked successfully',
            'student_id': student_id,
            'name': student_name,
            'date': current_date,
            'time': current_time,
            'method': 'face_recognition' if 'image' in data else 'manual'
        }), 201
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Get attendance records
@app.route('/api/attendance', methods=['GET'])
def get_attendance():
    date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    class_name = request.args.get('class', '')
    
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        query = 'SELECT * FROM attendance WHERE date = ?'
        params = [date]
        
        if class_name:
            query += ' AND class_name = ?'
            params.append(class_name)
        
        query += ' ORDER BY time DESC'
        
        cursor.execute(query, params)
        records = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        return jsonify({
            'date': date,
            'total': len(records),
            'records': records
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Admin login
@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    
    if not data or 'username' not in data or 'password' not in data:
        return jsonify({'error': 'Username and password required'}), 400
    
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM admin 
            WHERE username = ? AND password = ?
        ''', (data['username'], data['password']))
        
        admin = cursor.fetchone()
        conn.close()
        
        if admin:
            return jsonify({
                'message': 'Login successful',
                'username': data['username']
            })
        else:
            return jsonify({'error': 'Invalid credentials'}), 401
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print('='*50)
    print('FACE RECOGNITION ATTENDANCE SYSTEM')
    print('='*50)
    print('🚀 Server starting...')
    print('📍 http://127.0.0.1:5000')
    print('📍 http://127.0.0.1:5000/api/health')
    print('📁 Database: attendance.db')
    print('📸 Face Recognition: ENABLED')
    print('='*50)
    print('Default Admin Login:')
    print('   Username: admin')
    print('   Password: admin123')
    print('='*50)
    print('📊 Face Matching Threshold: 0.45 (lower = stricter)')
    print('='*50)
    app.run(debug=True, host='127.0.0.1', port=5000)