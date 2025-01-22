from flask import Flask, render_template, request, jsonify, redirect, url_for, send_from_directory, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import json
from datetime import datetime, timedelta
import os

app = Flask(__name__, static_folder='static')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///salon.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = 'your-secret-key-here'  # Change this to a secure secret key

# Ensure static directory exists
os.makedirs(os.path.join(app.root_path, 'static', 'css'), exist_ok=True)

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(80), nullable=False)
    last_name = db.Column(db.String(80), nullable=False)
    phone_number = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    appointments = db.relationship('Appointment', backref='user', lazy=True)

class Appointment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    service_id = db.Column(db.String(80), nullable=False)
    date = db.Column(db.Date, nullable=False)
    time = db.Column(db.Time, nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def load_services():
    try:
        with open('services.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_services(services):
    with open('services.json', 'w') as f:
        json.dump(services, f, indent=4)

def validate_business_hours(date_str, time_str):
    """Validate if the appointment is within business hours (9 AM to 7 PM, Monday to Sunday)"""
    try:
        date = datetime.strptime(date_str, '%Y-%m-%d').date()
        time = datetime.strptime(time_str, '%H:%M').time()
        
        # Check if time is between 9 AM and 7 PM
        opening_time = datetime.strptime('09:00', '%H:%M').time()
        closing_time = datetime.strptime('19:00', '%H:%M').time()
        
        if not (opening_time <= time < closing_time):
            return False, "Appointments must be between 9 AM and 7 PM"
            
        return True, None
    except ValueError as e:
        return False, str(e)

@app.route('/')
@login_required
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('index'))
        return render_template('login.html', error='Invalid username or password')
    
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        first_name = request.form['first_name']
        last_name = request.form['last_name']
        phone_number = request.form['phone_number']
        email = request.form['email']
        username = request.form['username']
        password = request.form['password']

        # Check if username or email already exists
        if User.query.filter_by(username=username).first():
            flash('Username already exists')
            return redirect(url_for('signup'))
        
        if User.query.filter_by(email=email).first():
            flash('Email already registered')
            return redirect(url_for('signup'))

        # Create new user
        new_user = User(
            first_name=first_name,
            last_name=last_name,
            phone_number=phone_number,
            email=email,
            username=username,
            password_hash=generate_password_hash(password)
        )

        try:
            db.session.add(new_user)
            db.session.commit()
            login_user(new_user)
            return redirect(url_for('index'))
        except Exception as e:
            db.session.rollback()
            flash('Error creating account')
            return redirect(url_for('signup'))

    return render_template('signup.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/services')
@login_required
def get_services():
    return jsonify(load_services())

@app.route('/admin/services', methods=['POST', 'PUT'])
@login_required
def manage_service():
    if not current_user.is_admin:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403

    data = request.json
    services = load_services()
    
    if not all(key in data for key in ['id', 'name', 'duration']):
        return jsonify({'success': False, 'error': 'Missing required fields'})

    services[data['id']] = {
        'name': data['name'],
        'duration': data['duration']
    }
    
    save_services(services)
    return jsonify({'success': True})

@app.route('/admin/services', methods=['DELETE'])
@login_required
def delete_service():
    if not current_user.is_admin:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403

    service_id = request.args.get('id')
    if not service_id:
        return jsonify({'success': False, 'error': 'Service ID required'})

    services = load_services()
    if service_id in services:
        del services[service_id]
        save_services(services)
        return jsonify({'success': True})
    
    return jsonify({'success': False, 'error': 'Service not found'})

@app.route('/appointments')
@login_required
def get_appointments():
    appointments = []
    query = Appointment.query.all()  # Get all appointments
    services = load_services()

    for appointment in query:
        service = services.get(appointment.service_id, {})
        is_owner = current_user.is_admin or appointment.user_id == current_user.id
        
        # Base event information
        event = {
            'id': appointment.id,
            'start': f"{appointment.date}T{appointment.time}",
            'end': (datetime.combine(appointment.date, appointment.time) + 
                   timedelta(minutes=service.get('duration', 60))).strftime('%Y-%m-%dT%H:%M:%S'),
            'extendedProps': {
                'canEdit': is_owner,
                'serviceId': appointment.service_id,
                'serviceName': service.get('name', 'Unknown Service')
            }
        }

        # Add user details for admin or appointment owner
        if is_owner:
            event['title'] = f"{appointment.user.first_name} {appointment.user.last_name} - {service.get('name', 'Unknown Service')}"
            if current_user.is_admin:
                event['extendedProps'].update({
                    'userFirstName': appointment.user.first_name,
                    'userLastName': appointment.user.last_name,
                    'userPhone': appointment.user.phone_number,
                    'userEmail': appointment.user.email
                })
        else:
            event['title'] = "Busy"
            event['backgroundColor'] = '#ff9f89'  # Light red for busy slots
            event['borderColor'] = '#ff7f6e'
            event['display'] = 'block'  # Block display for busy slots

        appointments.append(event)
    
    return jsonify(appointments)

@app.route('/appointment/<int:appointment_id>')
@login_required
def get_appointment(appointment_id):
    appointment = Appointment.query.get_or_404(appointment_id)
    
    if not current_user.is_admin and appointment.user_id != current_user.id:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403

    return jsonify({
        'id': appointment.id,
        'service_id': appointment.service_id,
        'date': appointment.date.isoformat(),
        'time': appointment.time.strftime('%H:%M'),
        'user': {
            'first_name': appointment.user.first_name,
            'last_name': appointment.user.last_name,
            'phone_number': appointment.user.phone_number,
            'email': appointment.user.email
        }
    })

@app.route('/add_appointment', methods=['POST'])
@login_required
def add_appointment():
    data = request.json
    
    try:
        # Validate business hours
        is_valid, error_message = validate_business_hours(data['date'], data['time'])
        if not is_valid:
            return jsonify({'success': False, 'error': error_message})

        date = datetime.strptime(data['date'], '%Y-%m-%d').date()
        time = datetime.strptime(data['time'], '%H:%M').time()
        
        # Check for conflicting appointments
        start_time = datetime.combine(date, time)
        service = load_services().get(data['service_id'])
        if not service:
            return jsonify({'success': False, 'error': 'Invalid service'})
        
        end_time = start_time + timedelta(minutes=service['duration'])
        
        # Check for conflicts
        conflicts = Appointment.query.filter(
            Appointment.date == date,
            Appointment.time.between(time, end_time.time())
        ).first()
        
        if conflicts:
            return jsonify({'success': False, 'error': 'Time slot is already booked'})
        
        appointment = Appointment(
            user_id=current_user.id,
            service_id=data['service_id'],
            date=date,
            time=time,
            user=current_user
        )
        
        db.session.add(appointment)
        db.session.commit()
        
        return jsonify({'success': True})
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/appointment/<int:appointment_id>', methods=['PUT'])
@login_required
def update_appointment(appointment_id):
    appointment = Appointment.query.get_or_404(appointment_id)
    
    if not current_user.is_admin and appointment.user_id != current_user.id:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    data = request.json
    
    try:
        # Validate business hours
        is_valid, error_message = validate_business_hours(data['date'], data['time'])
        if not is_valid:
            return jsonify({'success': False, 'error': error_message})

        date = datetime.strptime(data['date'], '%Y-%m-%d').date()
        time = datetime.strptime(data['time'], '%H:%M').time()
        
        # Check for conflicting appointments
        start_time = datetime.combine(date, time)
        service = load_services().get(data['service_id'])
        if not service:
            return jsonify({'success': False, 'error': 'Invalid service'})
        
        end_time = start_time + timedelta(minutes=service['duration'])
        
        # Check for conflicts, excluding the current appointment
        conflicts = Appointment.query.filter(
            Appointment.id != appointment_id,
            Appointment.date == date,
            Appointment.time.between(time, end_time.time())
        ).first()
        
        if conflicts:
            return jsonify({'success': False, 'error': 'Time slot is already booked'})
        
        appointment.service_id = data['service_id']
        appointment.date = date
        appointment.time = time
        
        db.session.commit()
        
        return jsonify({'success': True})
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/appointment/<int:appointment_id>', methods=['DELETE'])
@login_required
def delete_appointment(appointment_id):
    appointment = Appointment.query.get_or_404(appointment_id)
    
    if not current_user.is_admin and appointment.user_id != current_user.id:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    try:
        db.session.delete(appointment)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/user/profile')
@login_required
def get_profile():
    return jsonify({
        'success': True,
        'user': {
            'first_name': current_user.first_name,
            'last_name': current_user.last_name,
            'phone_number': current_user.phone_number,
            'email': current_user.email
        }
    })

@app.route('/user/profile', methods=['PUT'])
@login_required
def update_profile():
    data = request.json
    
    try:
        # Check if email is being changed and if it's already taken by another user
        if data['email'] != current_user.email and User.query.filter(User.email == data['email'], User.id != current_user.id).first():
            return jsonify({'success': False, 'error': 'Email already registered'})

        # Update user information
        current_user.first_name = data['first_name']
        current_user.last_name = data['last_name']
        current_user.phone_number = data['phone_number']
        current_user.email = data['email']
        
        # Update password if provided
        if data['new_password']:
            current_user.password_hash = generate_password_hash(data['new_password'])
        
        db.session.commit()
        return jsonify({'success': True})
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        # Create default admin and user if they don't exist
        if not User.query.filter_by(username='admin').first():
            admin = User(
                username='admin',
                password_hash=generate_password_hash('admin123'),
                is_admin=True,
                first_name='Admin',
                last_name='User',
                phone_number='1234567890',
                email='admin@example.com'
            )
            db.session.add(admin)
        
        if not User.query.filter_by(username='user').first():
            user = User(
                username='user',
                password_hash=generate_password_hash('user123'),
                is_admin=False,
                first_name='Regular',
                last_name='User',
                phone_number='9876543210',
                email='user@example.com'
            )
            db.session.add(user)
        
        db.session.commit()
    
    # app.run(debug=True)
    app.run(host='0.0.0.0', port=8000)
