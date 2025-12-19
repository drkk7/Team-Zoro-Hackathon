# Team-Zoro-Hackathon
# Quiz Master V2 - MAD II

## Overview
Quiz Master V2 is a comprehensive quiz platform built with modern technologies as part of Modern Application Development II. This upgraded version includes advanced features like Redis caching, Celery background jobs, VueJS frontend, and scheduled tasks.

## 🚀 Features

### Core Features
- **Multi-user platform** with Admin and User roles
- **Subject-Chapter-Quiz hierarchy** for organized content
- **Real-time quiz taking** with timer functionality
- **Score tracking and analytics** with charts
- **Responsive design** for mobile and desktop

### Advanced Features (MAD-2)
- **Redis Caching** for improved performance
- **Celery Background Jobs** for async processing
- **Scheduled Tasks**:
  - Daily reminders via email
  - Monthly activity reports
- **CSV Export** functionality
- **VueJS SPA** frontend
- **API-first architecture**

## 🛠 Technology Stack

### Backend
- **Flask** - Web framework
- **SQLite** - Database
- **Redis** - Caching and message broker
- **Celery** - Background task processing
- **Flask-Mail** - Email functionality
- **Flask-CORS** - Cross-origin resource sharing

### Frontend
- **Vue.js 3** - Progressive JavaScript framework
- **Vue Router** - Client-side routing
- **Vuex** - State management
- **Bootstrap 5** - UI framework
- **Chart.js** - Data visualization
- **Axios** - HTTP client

## 📁 Project Structure

```
MAD-1/
├── app.py                 # Main Flask application
├── celery_config.py       # Celery configuration
├── requirements.txt       # Python dependencies
├── backend/
│   ├── models.py         # Database models
│   └── controllers.py    # Business logic
├── frontend/             # Vue.js application
│   ├── src/
│   │   ├── components/   # Vue components
│   │   ├── views/        # Page components
│   │   ├── router/       # Vue router
│   │   ├── store/        # Vuex store
│   │   ├── App.vue       # Main app component
│   │   └── main.js       # App entry point
│   ├── public/
│   │   └── index.html    # HTML template
│   └── package.json      # Node.js dependencies
├── templates/            # Legacy Jinja2 templates
├── static/              # Static assets
└── instance/            # Database files
```

## 🚀 Installation & Setup

### Prerequisites
- Python 3.8+
- Node.js 14+
- Redis Server
- Git

### Backend Setup

1. **Install Python dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Start Redis Server:**
   ```bash
   # Windows
   redis-server
   
   # Linux/Mac
   sudo systemctl start redis
   ```

3. **Start Celery Worker:**
   ```bash
   celery -A celery_config.celery_app worker --loglevel=info
   ```

4. **Start Celery Beat (for scheduled tasks):**
   ```bash
   celery -A celery_config.celery_app beat --loglevel=info
   ```

5. **Run Flask Application:**
   ```bash
   python app.py
   ```

### Frontend Setup

1. **Navigate to frontend directory:**
   ```bash
   cd frontend
   ```

2. **Install Node.js dependencies:**
   ```bash
   npm install
   ```

3. **Run development server:**
   ```bash
   npm run serve
   ```

4. **Build for production:**
   ```bash
   npm run build
   ```

## 🔧 Configuration

### Email Configuration
Update the email settings in `app.py`:
```python
app.config['MAIL_USERNAME'] = 'your-email@gmail.com'
app.config['MAIL_PASSWORD'] = 'your-app-password'
```

### Redis Configuration
Default Redis configuration:
- Host: localhost
- Port: 6379
- Database: 0 (for Celery), 1 (for caching)

## 📊 API Endpoints

### Authentication
- `POST /api/auth/login` - User login
- `POST /api/auth/register` - User registration

### Subjects & Chapters
- `GET /api/subjects` - Get all subjects
- `GET /api/subjects/{id}/chapters` - Get chapters for subject

### Quizzes
- `GET /api/chapters/{id}/quizzes` - Get quizzes for chapter
- `GET /api/quizzes/{id}/questions` - Get questions for quiz

### Scores
- `POST /api/scores` - Submit quiz score
- `GET /api/user/scores` - Get user scores

### Export
- `POST /api/export/user-csv` - Export user data as CSV

## 🔄 Background Jobs

### Scheduled Tasks
- **Daily Reminders**: Sent at 6 PM daily to users who haven't taken quizzes
- **Monthly Reports**: Generated and sent on the 1st of each month

### Async Tasks
- **CSV Export**: User-triggered export of quiz data
- **Email Notifications**: Background email sending

## 🎯 Key Features Implementation

### 1. Redis Caching
- API responses cached for 5 minutes
- User scores cached with automatic invalidation
- Improved performance for frequently accessed data

### 2. Celery Background Jobs
- Email sending in background
- CSV generation and export
- Scheduled task execution

### 3. VueJS Frontend
- Single Page Application (SPA)
- Reactive data management with Vuex
- Modern UI with Bootstrap 5
- Chart.js for data visualization

### 4. Enhanced Database Schema
- Subjects → Chapters → Quizzes → Questions hierarchy
- Comprehensive user profiles
- Detailed score tracking

## 🧪 Testing

### Backend Testing
```bash
# Run Flask tests
python -m pytest tests/

# Test Celery tasks
celery -A celery_config.celery_app test
```

### Frontend Testing
```bash
cd frontend
npm run test
```

## 📈 Performance Optimizations

1. **Redis Caching**: Reduces database queries
2. **API Response Caching**: 5-minute cache for static data
3. **Background Processing**: Non-blocking operations
4. **Frontend Optimization**: Lazy loading and code splitting

## 🔒 Security Features

- JWT-based authentication
- Role-based access control
- Input validation and sanitization
- CORS configuration
- Secure password hashing

## 📱 Responsive Design

- Mobile-first approach
- Bootstrap 5 responsive grid
- Touch-friendly interface
- Progressive Web App features

## 🚀 Deployment

### Production Setup
1. Use Gunicorn for Flask
2. Configure Nginx as reverse proxy
3. Set up Redis persistence
4. Configure Celery with Redis backend
5. Build and serve Vue.js frontend

### Environment Variables
```bash
export FLASK_ENV=production
export REDIS_URL=redis://localhost:6379
export CELERY_BROKER_URL=redis://localhost:6379/0
```

## 📝 API Documentation

### Authentication Flow
1. User registers/logs in
2. JWT token issued
3. Token included in subsequent requests
4. Automatic token refresh

### Quiz Flow
1. User selects subject
2. Chooses chapter
3. Selects quiz
4. Takes quiz with timer
5. Score automatically calculated and stored

## 🤝 Contributing

1. Fork the repository
2. Create feature branch
3. Make changes
4. Add tests
5. Submit pull request

## 📄 License

This project is part of Modern Application Development II coursework.

## 👨‍💻 Author

**Student Name**: KARTHIK Kalleti  
**Roll Number**: 23f2001791  
**Email**: karthikkalleti7777@gmail.com  
**Course**: Modern Application Development II

---

## 🎯 MAD-2 Requirements Checklist

- ✅ SQLite for data storage
- ✅ Flask for API
- ✅ VueJS for UI
- ✅ Bootstrap for styling
- ✅ Redis for caching
- ✅ Redis and Celery for batch jobs
- ✅ Admin and User roles
- ✅ Subject-Chapter-Quiz hierarchy
- ✅ Daily reminders
- ✅ Monthly reports
- ✅ CSV export functionality
- ✅ Performance optimizations
- ✅ Responsive design 
