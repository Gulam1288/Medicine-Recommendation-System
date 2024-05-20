import mysql.connector
from flask import Flask, render_template, request, session, redirect, url_for, jsonify
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
    # Split user input tags by commas to handle multiple symptoms
    user_symptoms = [symptom.strip().lower() for symptom in user_tags.split(',')]

    recommended_medicines = []
    unique_medicines = set()  # Set to keep track of unique medicine names

    for symptom in user_symptoms:
        # Preprocess user input tags
        symptom = preprocess_text(symptom)

        # Transform user input tags into a vector using CountVectorizer
        user_vector = cv.transform([symptom]).toarray()

        # Calculate cosine similarity between user vector and all medicine vectors
        similarity_scores = cosine_similarity(vectors, user_vector)

        # Get indices of medicines sorted by similarity (excluding exact matches)
        sorted_indices = sorted(range(len(similarity_scores)), key=lambda i: similarity_scores[i], reverse=True)

        # Counter to keep track of how many recommendations are made for each symptom
        count = 0

        for idx in sorted_indices:
            if count == 4:
                break

            medicine_name = df.iloc[idx]['Drug_Name']
            treatment_info = df.iloc[idx]['Treatment']

            # Check if medicine name is not already recommended
            if medicine_name not in unique_medicines:
                recommended_medicines.append((medicine_name, treatment_info))
                unique_medicines.add(medicine_name)  # Add medicine name to set of unique medicines
                count += 1

    return recommended_medicines



# Flask routes

@app.route('/recommendations', methods=['POST'])
def recommend():
    # Get form data including name, age, gender and symptoms
    user_name = request.form['name']
    user_age = int(request.form['age'])  # Convert age to integer
    user_gender = request.form['gender']
    user_input_tags = request.form['user_tags']

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

@app.route('/save_prescription', methods=['POST'])
def save_prescription():
    data = request.json
    try:
        # Create cursor
        cursor = db.cursor()

        cursor.execute("INSERT INTO prescriptions (user_name, age, gender, symptoms, medicines, treatments) VALUES (%s, %s, %s, %s, %s, %s)", 
                (data['userName'], data['age'], data['gender'], data['symptoms'], ','.join(data['medicines']), ','.join(data['treatments'])))

        # Commit to DB
        db.commit()
        inserted_id = cursor.lastrowid

        return jsonify({'message': 'Prescription data saved successfully', 'id': inserted_id})


    except mysql.connector.Error as err:
        error = f"An error occurred: {err}"
        return render_template('result.html', error=error)


    except mysql.connector.Error as err:
        error = f"An error occurred: {err}"
        return render_template('result.html', error=error)
    
@app.route('/display_prescription', methods=['GET', 'POST'])
def display_prescription_ID():
    if request.method == 'POST':
        prescription_ids = request.form['prescription_id']
        return redirect(url_for('display_prescriptions', prescription_ids=prescription_ids))
    else:
        prescription_ids = request.args.get('prescription_id')
        if prescription_ids:
            return redirect(url_for('display_prescriptions', prescription_ids=prescription_ids))
        else:
            return "Prescription IDs are required."

@app.route('/display_prescriptions')
def display_prescriptions():
    prescription_ids = request.args.get('prescription_ids')
    if not prescription_ids:
        return "Prescription IDs are required."

    ids = prescription_ids.split(',')
    length = len(ids)
    cursor = db.cursor(dictionary=True)
    query = "SELECT * FROM prescriptions WHERE id IN (%s)" % ','.join(['%s'] * len(ids))
    cursor.execute(query, tuple(ids))
    prescriptions = cursor.fetchall()
    cursor.close()
    prescription_ids = [int(id.strip()) for id in prescription_ids.split(',')]
    valid_prescriptions = []
    invalid_ids = []
    valid_ids = {prescription['id'] for prescription in prescriptions}
    for id in prescription_ids:
        if id in valid_ids:
            valid_prescriptions.append(id)
        else:
            invalid_ids.append(id)

    
    for prescription in prescriptions:
        # Split medicines and treatments into lists for each prescription
        prescription['medicines'] = prescription['medicines'].split(',')
        prescription['treatments'] = prescription['treatments'].split(',')
    return render_template('patientHistory.html', prescriptions=prescriptions, length = length, invalid_ids=invalid_ids, lenin=len(invalid_ids))
    


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
    return render_template("logout.html")

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        # Get form data
        username = request.form['username']
        password = request.form['password']
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        name = request.form['name']
        gender = request.form['gender']
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
            insert_query = "INSERT INTO doctors (username, password, name, gender, email, phone, address) VALUES (%s, %s, %s, %s, %s, %s, %s)"
            cursor.execute(insert_query, (username, hashed_password, name, gender, email, phone, address))

            # Commit to DB
            db.commit()

            return render_template('register.html', message="Registraion successful!")

        except mysql.connector.Error as err:
            error = f"An error occurred: {err}"
            return render_template('register.html', error=error)

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user' in session:
        # If user is already logged in, redirect to index or display a message
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
                    return redirect(url_for('prescription'))
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

@app.route('/reset', methods=['GET', 'POST'])
def reset_password():
    if request.method == 'POST':
        username = request.form['username']
        new_password = request.form['password']
        hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())

        try:
            # Create cursor
            cursor = db.cursor()

            # Check if the username exists in the database
            cursor.execute("SELECT * FROM doctors WHERE username = %s", (username,))
            user = cursor.fetchone()

            if user:
                # Update user's password
                cursor.execute("UPDATE doctors SET password = %s WHERE username = %s", (hashed_password, username))
                db.commit()
                cursor.close()
                message = 'Password reset successful. You can now log in with your new password.'
                return render_template('reset.html', message=message)
            else:
                error = 'Username not found. Please enter a valid username.'
                return render_template('reset.html', error=error)

        except mysql.connector.Error as err:
            error = f"An error occurred: {err}"
            return render_template('reset.html', error=error)

    return render_template('reset.html')

# Update the Flask route for autocomplete suggestions
@app.route('/autocomplete', methods=['POST'])
def autocomplete():
    input_text = request.form['input']
    suggestions = get_reason_suggestions(input_text)  # Implement this function
    return jsonify(suggestions)

def get_reason_suggestions(input_text):
    # Filter reasons from your dataset based on input_text
    suggestions = df[df['Reason'].str.contains(input_text, case=False)]['Reason'].unique()
    return list(suggestions)



if __name__ == '__main__':
    app.run(debug=True,host='0.0.0.0', port=5000)
