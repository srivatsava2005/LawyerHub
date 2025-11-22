from flask import Flask, request, jsonify, session, redirect, url_for, render_template
from flask_bcrypt import Bcrypt
from flask_pymongo import PyMongo
from bson.objectid import ObjectId
from datetime import datetime, timedelta
import jwt
from functools import wraps
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__, static_folder='static', template_folder='templates')
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev_secret_key')
app.config['MONGO_URI'] = os.getenv('MONGO_URI', 'mongodb://localhost:27017/lawyerhub')
app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY', 'jwt_secret_key')
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(days=1)

# Initialize extensions
mongo = PyMongo(app)
bcrypt = Bcrypt(app)

# Database collections
users = mongo.db.users
lawyers = mongo.db.lawyers
reviews = mongo.db.reviews
categories = mongo.db.categories

# Token required decorator
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            token = request.headers['Authorization'].split(' ')[1]
        
        if not token:
            return jsonify({'message': 'Token is missing!'}), 401
        
        try:
            data = jwt.decode(token, app.config['JWT_SECRET_KEY'], algorithms=["HS256"])
            current_user = users.find_one({'_id': ObjectId(data['user_id'])})
        except:
            return jsonify({'message': 'Token is invalid!'}), 401
            
        return f(current_user, *args, **kwargs)
    
    return decorated

# User routes
@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    
    # Check if user already exists
    existing_user = users.find_one({'email': data['email']})
    if existing_user:
        return jsonify({'message': 'User already exists!'}), 409
    
    # Hash password
    hashed_password = bcrypt.generate_password_hash(data['password']).decode('utf-8')
    
    # Create new user
    new_user = {
        'email': data['email'],
        'password': hashed_password,
        'name': data['name'],
        'role': data.get('role', 'client'),  # 'client' or 'lawyer'
        'created_at': datetime.utcnow(),
        'updated_at': datetime.utcnow()
    }
    
    # If user is a lawyer, add lawyer-specific fields
    if data.get('role') == 'lawyer':
        new_user['specialty'] = data.get('specialty', [])
        new_user['location'] = data.get('location', {})
        new_user['bio'] = data.get('bio', '')
        new_user['education'] = data.get('education', [])
        new_user['experience'] = data.get('experience', [])
        new_user['license_info'] = data.get('license_info', {})
        new_user['profile_complete'] = False
        new_user['is_verified'] = False
        
        # Initialize reward system fields
        new_user['rating'] = 0
        new_user['review_count'] = 0
        new_user['badges'] = []
        new_user['reward_points'] = 0
        new_user['reward_tier'] = 'standard'  # standard, silver, gold, platinum
    
    # Insert user
    result = users.insert_one(new_user)
    
    return jsonify({
        'message': 'User registered successfully!',
        'user_id': str(result.inserted_id)
    }), 201

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    
    user = users.find_one({'email': data['email']})
    
    if not user:
        return jsonify({'message': 'Invalid credentials!'}), 401
    
    if bcrypt.check_password_hash(user['password'], data['password']):
        # Generate JWT token
        token = jwt.encode(
            {
                'user_id': str(user['_id']),
                'role': user['role'],
                'exp': datetime.utcnow() + app.config['JWT_ACCESS_TOKEN_EXPIRES']
            },
            app.config['JWT_SECRET_KEY'],
            algorithm="HS256"
        )
        
        return jsonify({
            'message': 'Login successful!',
            'token': token,
            'user': {
                'id': str(user['_id']),
                'name': user['name'],
                'email': user['email'],
                'role': user['role']
            }
        })
    
    return jsonify({'message': 'Invalid credentials!'}), 401

# Lawyer profile routes
@app.route('/api/lawyers', methods=['GET'])
def get_lawyers():
    # Get query parameters
    specialty = request.args.get('specialty')
    location = request.args.get('location')
    sort_by = request.args.get('sort_by', 'rating')  # default sort by rating
    sort_order = int(request.args.get('sort_order', -1))  # default descending
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 10))
    min_rating = float(request.args.get('min_rating', 0))
    reward_tier = request.args.get('reward_tier')
    
    # Build query
    query = {'role': 'lawyer', 'profile_complete': True, 'is_verified': True}
    
    if specialty:
        query['specialty'] = {'$in': [specialty]}
    
    if location:
        query['location.city'] = location
    
    if min_rating > 0:
        query['rating'] = {'$gte': min_rating}
    
    if reward_tier:
        query['reward_tier'] = reward_tier
    
    # Execute query with pagination and sorting
    total_lawyers = users.count_documents(query)
    lawyer_cursor = users.find(
        query,
        {'password': 0}  # Exclude password
    ).sort([(sort_by, sort_order)]).skip((page-1)*per_page).limit(per_page)
    
    # Convert cursor to list
    lawyer_list = []
    for lawyer in lawyer_cursor:
        lawyer['_id'] = str(lawyer['_id'])
        lawyer_list.append(lawyer)
    
    return jsonify({
        'total': total_lawyers,
        'page': page,
        'per_page': per_page,
        'lawyers': lawyer_list
    })

@app.route('/api/lawyers/<lawyer_id>', methods=['GET'])
def get_lawyer(lawyer_id):
    try:
        lawyer = users.find_one({'_id': ObjectId(lawyer_id), 'role': 'lawyer'}, {'password': 0})
        
        if not lawyer:
            return jsonify({'message': 'Lawyer not found!'}), 404
        
        # Convert ObjectId to string
        lawyer['_id'] = str(lawyer['_id'])
        
        # Get recent reviews
        recent_reviews_cursor = reviews.find(
            {'lawyer_id': lawyer_id}
        ).sort([('created_at', -1)]).limit(5)
        
        recent_reviews = []
        for review in recent_reviews_cursor:
            review['_id'] = str(review['_id'])
            review['user_id'] = str(review['user_id'])
            
            # Get reviewer name
            reviewer = users.find_one({'_id': ObjectId(review['user_id'])}, {'name': 1})
            if reviewer:
                review['reviewer_name'] = reviewer['name']
            
            recent_reviews.append(review)
        
        lawyer['recent_reviews'] = recent_reviews
        
        return jsonify(lawyer)
    
    except Exception as e:
        return jsonify({'message': str(e)}), 500

@app.route('/api/lawyers/<lawyer_id>', methods=['PUT'])
@token_required
def update_lawyer_profile(current_user, lawyer_id):
    # Verify user is updating their own profile or is admin
    if str(current_user['_id']) != lawyer_id and current_user.get('role') != 'admin':
        return jsonify({'message': 'Unauthorized!'}), 403
    
    data = request.get_json()
    
    # Fields that can be updated
    updatable_fields = [
        'name', 'specialty', 'location', 'bio', 'education',
        'experience', 'license_info', 'profile_image', 'contact_info'
    ]
    
    update_data = {
        'updated_at': datetime.utcnow()
    }
    
    for field in updatable_fields:
        if field in data:
            update_data[field] = data[field]
    
    # Check if profile is now complete
    if not current_user.get('profile_complete'):
        required_fields = ['name', 'specialty', 'location', 'bio', 'license_info']
        profile_complete = all(current_user.get(field) or update_data.get(field) for field in required_fields)
        
        if profile_complete:
            update_data['profile_complete'] = True
    
    # Update lawyer profile
    result = users.update_one(
        {'_id': ObjectId(lawyer_id)},
        {'$set': update_data}
    )
    
    if result.modified_count:
        return jsonify({'message': 'Profile updated successfully!'})
    else:
        return jsonify({'message': 'No changes made to profile.'}), 304

# Review and rating system
@app.route('/api/lawyers/<lawyer_id>/reviews', methods=['POST'])
@token_required
def post_review(current_user, lawyer_id):
    # Check if user is a client
    if current_user.get('role') != 'client':
        return jsonify({'message': 'Only clients can post reviews!'}), 403
    
    data = request.get_json()
    
    # Validate rating
    rating = data.get('rating')
    if not rating or not isinstance(rating, (int, float)) or rating < 1 or rating > 5:
        return jsonify({'message': 'Rating must be between 1 and 5!'}), 400
    
    # Check if lawyer exists
    lawyer = users.find_one({'_id': ObjectId(lawyer_id), 'role': 'lawyer'})
    if not lawyer:
        return jsonify({'message': 'Lawyer not found!'}), 404
    
    # Check if user has already reviewed this lawyer
    existing_review = reviews.find_one({
        'user_id': str(current_user['_id']),
        'lawyer_id': lawyer_id
    })
    
    if existing_review:
        return jsonify({'message': 'You have already reviewed this lawyer!'}), 409
    
    # Create new review
    new_review = {
        'user_id': str(current_user['_id']),
        'lawyer_id': lawyer_id,
        'rating': rating,
        'comment': data.get('comment', ''),
        'created_at': datetime.utcnow()
    }
    
    # Insert review
    review_result = reviews.insert_one(new_review)
    
    # Update lawyer's rating
    lawyer_reviews = reviews.find({'lawyer_id': lawyer_id})
    review_count = reviews.count_documents({'lawyer_id': lawyer_id})
    total_rating = sum(review['rating'] for review in lawyer_reviews)
    new_avg_rating = round(total_rating / review_count, 1) if review_count > 0 else 0
    
    # Update lawyer document with new rating
    users.update_one(
        {'_id': ObjectId(lawyer_id)},
        {
            '$set': {
                'rating': new_avg_rating,
                'review_count': review_count
            }
        }
    )
    
    # Process reward system update
    update_lawyer_rewards(lawyer_id, new_avg_rating, review_count)
    
    return jsonify({
        'message': 'Review posted successfully!',
        'review_id': str(review_result.inserted_id)
    }), 201

@app.route('/api/lawyers/<lawyer_id>/reviews', methods=['GET'])
def get_lawyer_reviews(lawyer_id):
    # Get pagination parameters
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 10))
    
    # Get reviews with pagination
    reviews_cursor = reviews.find(
        {'lawyer_id': lawyer_id}
    ).sort([('created_at', -1)]).skip((page-1)*per_page).limit(per_page)
    
    total_reviews = reviews.count_documents({'lawyer_id': lawyer_id})
    
    # Convert cursor to list
    review_list = []
    for review in reviews_cursor:
        review['_id'] = str(review['_id'])
        
        # Get reviewer name
        reviewer = users.find_one({'_id': ObjectId(review['user_id'])}, {'name': 1})
        if reviewer:
            review['reviewer_name'] = reviewer['name']
        
        review_list.append(review)
    
    return jsonify({
        'total': total_reviews,
        'page': page,
        'per_page': per_page,
        'reviews': review_list
    })

# Reward system functions
def update_lawyer_rewards(lawyer_id, rating, review_count):
    """Update lawyer rewards based on rating and review count"""
    # Get current lawyer data
    lawyer = users.find_one({'_id': ObjectId(lawyer_id)})
    
    if not lawyer:
        return
    
    # Calculate reward points based on rating and review count
    reward_points = calculate_reward_points(rating, review_count)
    
    # Determine reward tier
    new_tier = determine_reward_tier(reward_points, rating, review_count)
    
    # Determine badges
    badges = determine_badges(rating, review_count, lawyer.get('badges', []))
    
    # Update lawyer document
    users.update_one(
        {'_id': ObjectId(lawyer_id)},
        {
            '$set': {
                'reward_points': reward_points,
                'reward_tier': new_tier,
                'badges': badges
            }
        }
    )

def calculate_reward_points(rating, review_count):
    """Calculate reward points based on lawyer performance"""
    base_points = review_count * 10  # 10 points per review
    rating_multiplier = rating / 5.0  # 0.2 to 1.0 based on rating
    
    return int(base_points * rating_multiplier)

def determine_reward_tier(points, rating, review_count):
    """Determine lawyer's reward tier based on points, rating and review count"""
    if points >= 500 and rating >= 4.5 and review_count >= 30:
        return 'platinum'
    elif points >= 300 and rating >= 4.0 and review_count >= 20:
        return 'gold'
    elif points >= 150 and rating >= 3.5 and review_count >= 10:
        return 'silver'
    else:
        return 'standard'

def determine_badges(rating, review_count, current_badges):
    """Determine badges earned by lawyer"""
    badges = current_badges.copy() if current_badges else []
    
    # Define badge criteria
    badge_criteria = {
        'Top Rated': rating >= 4.8 and review_count >= 10,
        'Client Favorite': rating >= 4.5 and review_count >= 20,
        'Rising Star': rating >= 4.0 and review_count >= 5 and review_count < 15,
        'Experienced Pro': review_count >= 30,
        'Perfect Score': rating == 5.0 and review_count >= 3
    }
    
    # Add new badges
    for badge, criteria in badge_criteria.items():
        if criteria and badge not in badges:
            badges.append(badge)
    
    # Remove badges that no longer apply
    badges = [badge for badge in badges if badge in badge_criteria and badge_criteria[badge]]
    
    return badges

# Category routes
@app.route('/api/categories', methods=['GET'])
def get_categories():
    # Get all categories
    categories_cursor = categories.find()
    
    # Convert cursor to list
    category_list = []
    for category in categories_cursor:
        category['_id'] = str(category['_id'])
        category_list.append(category)
    
    return jsonify(category_list)

# Admin routes to initialize categories
@app.route('/api/admin/initialize_categories', methods=['POST'])
@token_required
def initialize_categories(current_user):
    # Check if user is admin
    if current_user.get('role') != 'admin':
        return jsonify({'message': 'Unauthorized!'}), 403
    
    # Sample categories
    sample_categories = [
        {
            'name': 'Corporate Law',
            'icon': 'fa-briefcase',
            'description': 'Legal professionals for business formation, contracts, and compliance.',
            'created_at': datetime.utcnow()
        },
        {
            'name': 'Family Law',
            'icon': 'fa-heart',
            'description': 'Experts in divorce, child custody, and family-related legal matters.',
            'created_at': datetime.utcnow()
        },
        {
            'name': 'Criminal Law',
            'icon': 'fa-gavel',
            'description': 'Attorneys specializing in criminal defense and prosecution.',
            'created_at': datetime.utcnow()
        },
        {
            'name': 'Real Estate Law',
            'icon': 'fa-home',
            'description': 'Find lawyers specialized in property transactions, disputes, and regulations.',
            'created_at': datetime.utcnow()
        },
        {
            'name': 'Immigration Law',
            'icon': 'fa-passport',
            'description': 'Assistance with visas, green cards, citizenship, and immigration issues.',
            'created_at': datetime.utcnow()
        },
        {
            'name': 'Intellectual Property',
            'icon': 'fa-lightbulb',
            'description': 'Protection for patents, trademarks, copyrights, and trade secrets.',
            'created_at': datetime.utcnow()
        },
        {
            'name': 'Personal Injury',
            'icon': 'fa-ambulance',
            'description': 'Representation for accident victims seeking compensation.',
            'created_at': datetime.utcnow()
        },
        {
            'name': 'Employment Law',
            'icon': 'fa-users',
            'description': 'Help with workplace issues, contracts, discrimination, and labor disputes.',
            'created_at': datetime.utcnow()
        }
    ]
    
    # Insert categories
    result = categories.insert_many(sample_categories)
    
    return jsonify({
        'message': f'Successfully initialized {len(result.inserted_ids)} categories!',
        'category_ids': [str(id) for id in result.inserted_ids]
    }), 201

# Main route for rendering frontend
@app.route('/')
def index():
    return render_template('index.html')

# Run the app
if __name__ == '__main__':
    app.run(debug=True)