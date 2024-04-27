import mysql.connector
from flask import Flask, render_template, request, session, redirect, url_for
import pandas as pd
from sklearn.feature_extraction.text import CountVectorizer
from nltk.stem import PorterStemmer
from sklearn.metrics.pairwise import cosine_similarity
import bcrypt

app = Flask(__name__)

# Load data and prepare for recommendation
df = pd.read_csv('newMedData.csv')

# Drop any rows with missing values
df.dropna(inplace=True)

# Combine 'Description' and 'Reason' columns to create 'tags'
df['tags'] = df['Description'] + ' ' + df['Reason']

# Initialize PorterStemmer
ps = PorterStemmer()

# Function to preprocess text: split, remove spaces, and stem
def preprocess_text(text):
    tokens = text.split()
    stemmed_tokens = [ps.stem(token) for token in tokens]
    return " ".join(stemmed_tokens)

# Apply preprocessing to 'tags' column
df['tags'] = df['tags'].apply(lambda x: preprocess_text(x.lower()))

# Initialize CountVectorizer
cv = CountVectorizer(stop_words='english', max_features=5000)

# Vectorize 'tags' column
vectors = cv.fit_transform(df['tags']).toarray()

def recommend_based_on_tags(user_tags):
    # Preprocess user input tags
    user_tags = preprocess_text(user_tags.lower())

    # Transform user input tags into a vector using CountVectorizer
    user_vector = cv.transform([user_tags]).toarray()

    # Calculate cosine similarity between user vector and all medicine vectors
    similarity_scores = cosine_similarity(vectors, user_vector)

    # Get indices of medicines sorted by similarity (excluding exact matches)
    sorted_indices = sorted(range(len(similarity_scores)), key=lambda i: similarity_scores[i], reverse=True)

    recommended_medicines = []
    unique_medicines = set()  # Set to keep track of unique medicine names

    for idx in sorted_indices:
        if len(recommended_medicines) == 4:
            break

        medicine_name = df.iloc[idx]['Drug_Name']
        treatment_info = df.iloc[idx]['Treatment']

        # Check if medicine name is not already recommended
        if medicine_name not in unique_medicines:
            recommended_medicines.append((medicine_name, treatment_info))
            unique_medicines.add(medicine_name)  # Add medicine name to set of unique medicines

    return recommended_medicines


# Flask routes

@app.route('/recommendations', methods=['POST'])
def recommend():
    # Get form data including symptoms, name, age, and gender
    user_input_tags = request.form['user_tags']
    user_name = request.form['name']
    user_age = int(request.form['age'])  # Convert age to integer
    user_gender = request.form['gender']

    # Create a dictionary with user information
    user_info = {
        'name': user_name,
        'age': user_age,
        'gender': user_gender
    }

    # Get recommendations based on symptoms and user information
    recommendations = recommend_based_on_tags(user_input_tags)

    # Render the result.html template with user input and recommendations
    return render_template('result.html', user_input_tags=user_input_tags, user_info=user_info, recommendations=recommendations)

app.secret_key = 'your_secret_key'

# Configure MySQL connection
db = mysql.connector.connect(
    host='localhost',
    user='root',
    password='',
    database='healthcare_db'
)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/prescription')
def prescription():
    if 'user' in session:
        user = session['user']
        return render_template('prescription.html', user=user)
    else:
        return redirect(url_for('login'))

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        # Get form data
        username = request.form['username']
        password = request.form['password']
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        name = request.form['name']
        qualification = request.form['qualification']
        gender = request.form['gender']
        specialist_area = request.form['specialist_area']
        email = request.form['email']
        phone = request.form['phone']
        address = request.form['address']

        try:
            # Create cursor
            cursor = db.cursor()

            # Check if user already exists
            cursor.execute("SELECT * FROM doctors WHERE username = %s OR email = %s", (username, email))
            existing_user = cursor.fetchone()

            if existing_user:
                error = "Username or email already exists. Please choose a different one."
                return render_template('register.html', error=error)

            # Insert new user with hashed password
            insert_query = "INSERT INTO doctors (username, password, name, qualification, gender, specialist_area, email, phone, address) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"
            cursor.execute(insert_query, (username, hashed_password, name, qualification, gender, specialist_area, email, phone, address))

            # Commit to DB
            db.commit()

            return redirect(url_for('login'))

        except mysql.connector.Error as err:
            error = f"An error occurred: {err}"
            return render_template('register.html', error=error)

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user' in session:
        # If user is already logged in, redirect to home or display a message
        message = "You are already logged in. No new logins available."
        return render_template('login.html', message=message)

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        try:
            # Create cursor
            cursor = db.cursor()

            # Execute query to fetch user from database
            query = "SELECT * FROM doctors WHERE username = %s"
            cursor.execute(query, (username,))
            user = cursor.fetchone()

            if user:
                # Verify password
                hashed_password = user[2]  # Assuming password hash is stored in the second column
                if bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8')):
                    # Store user information in session
                    session['user'] = user
                    return redirect(url_for('index'))
                else:
                    error = 'Invalid credentials. Please try again.'
                    return render_template('login.html', error=error)
            else:
                error = 'Invalid credentials. Please try again.'
                return render_template('login.html', error=error)

        except mysql.connector.Error as err:
            error = f"An error occurred: {err}"
            return render_template('login.html', error=error)

    return render_template('login.html')



if __name__ == '__main__':
    app.run(debug=True,host='0.0.0.0', port=5000)
