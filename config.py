import os
from datetime import datetime

class Config:
    """Configuration settings for the Attendance System"""
    
    # Flask Configuration
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'your-secret-key-change-this-in-production'
    # Always use the DB inside the instance folder to avoid CWD/path mismatches
    _default_db_path = os.path.join(os.path.dirname(__file__), 'instance', 'attendance.db')
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or f"sqlite:///{_default_db_path}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # Control whether to auto-seed sample admin and employees on startup
    SEED_SAMPLE_DATA = (os.environ.get('SEED_SAMPLE_DATA', 'false').lower() == 'true')
    
    
    # Timesheet Configuration
    TIMESHEET_ENABLED = True
    REQUIRE_TIMESHEET_FOR_SIGNOUT = True  # Require timesheet submission before sign-out
    TIMESHEET_FIELDS = [
        {'name': 'tasks_completed', 'label': 'Tasks Completed Today', 'type': 'textarea', 'required': True},
        {'name': 'challenges_faced', 'label': 'Challenges Faced', 'type': 'textarea', 'required': False},
        {'name': 'achievements', 'label': 'Key Achievements', 'type': 'textarea', 'required': False},
        {'name': 'tomorrow_plans', 'label': 'Plans for Tomorrow', 'type': 'textarea', 'required': False},
        {'name': 'additional_notes', 'label': 'Additional Notes', 'type': 'textarea', 'required': False}
    ]
    
    DEFAULT_ADMIN_USERNAME = 'admin'
    DEFAULT_ADMIN_PASSWORD = 'admin123'
    DEFAULT_ADMIN_NAME = 'System Administrator'
    
    # Sample Employees Configuration
    SAMPLE_EMPLOYEES = [
        {
            'employee_id': 'EMP001',
            'name': 'John Doe',
            'email': 'john@company.com',
            'department': 'IT',
            'password': 'emp001123'
        },
        {
            'employee_id': 'EMP002',
            'name': 'Jane Smith',
            'email': 'jane@company.com',
            'department': 'HR',
            'password': 'emp002123'
        },
        {
            'employee_id': 'EMP003',
            'name': 'Mike Johnson',
            'email': 'mike@company.com',
            'department': 'Sales',
            'password': 'emp003123'
        },
        {
            'employee_id': 'EMP004',
            'name': 'Sarah Wilson',
            'email': 'sarah@company.com',
            'department': 'Marketing',
            'password': 'emp004123'
        },
        {
            'employee_id': 'EMP005',
            'name': 'David Brown',
            'email': 'david@company.com',
            'department': 'Finance',
            'password': 'emp005123'
        }
    ]
    
    # Application Settings
    APP_NAME = 'Employee Attendance System'
    APP_VERSION = '1.0.0'
    DEBUG = os.environ.get('FLASK_ENV') != 'production'
    
    # Time Settings
    WORKING_HOURS_START = 10 
    WORKING_HOURS_END = 18   
    
    
    OFFICE_LOCATIONS = [
        # {
        #     'name': 'Main Office',
        #     'latitude': 12.92499,
        #     'longitude': 77.61800,
        #     'radius_meters': 1000
        # },
        {
            'name': 'Home Office',
            'latitude': 12.9040293,
            'longitude': 77.5634288,
            'radius_meters': 1000
        },
        {
            'name': 'college',
            'latitude': 13.11734540585317,
            'longitude':77.6361704517549,
            'radius_meters': 1000
        }
    ]
    
    # Legacy single location settings (for backward compatibility)
    OFFICE_LATITUDE = float(os.environ.get('OFFICE_LATITUDE', '12.92499'))
    OFFICE_LONGITUDE = float(os.environ.get('OFFICE_LONGITUDE', '77.6180062'))
    OFFICE_RADIUS_METERS = float(os.environ.get('OFFICE_RADIUS_METERS', '1000'))
    
    # Payroll removed
    
    @staticmethod
    def is_office_hours():
        """Check if current time is within office hours"""
        now = datetime.now()
        return Config.WORKING_HOURS_START <= now.hour < Config.WORKING_HOURS_END
    
    @staticmethod
    def is_within_office_location(user_latitude, user_longitude):
        """
        Check if user's location is within any of the defined office locations
        Returns: (is_within_office, office_name) - tuple of boolean and office name if found
        """
        import math
        
        def calculate_distance(lat1, lon1, lat2, lon2):
            """Calculate distance between two points using Haversine formula"""
            # Convert latitude and longitude from degrees to radians
            lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
            
            # Haversine formula
            dlat = lat2 - lat1
            dlon = lon2 - lon1
            a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
            c = 2 * math.asin(math.sqrt(a))
            
            # Radius of earth in meters
            r = 6371000
            return c * r
        
        for office in Config.OFFICE_LOCATIONS:
            distance = calculate_distance(
                user_latitude, user_longitude,
                office['latitude'], office['longitude']
            )
            
            if distance <= office['radius_meters']:
                return True, office['name']
        
        return False, None 
