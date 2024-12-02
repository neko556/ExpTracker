from flask import Flask, request,render_template, flash, redirect, url_for, session, jsonify
from flask_mysqldb import MySQL
from wtforms import Form, StringField, PasswordField, IntegerField, EmailField, validators
from passlib.hash import sha256_crypt
from functools import wraps
import timeago
from datetime import datetime, timedelta
import plotly.graph_objects as go
import os
import pdfplumber
import re
import tabula
import pandas as pd
from datetime import datetime as dt


app = Flask(__name__, static_url_path='/static',
           )
app.config.from_pyfile('config.py')
UPLOAD_FOLDER = 'uploads/'  # Make sure this directory exists
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER


# Ensure the upload folder exists
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
mysql = MySQL(app)
class TransactionForm(Form):
    amount = IntegerField('Amount', [validators.NumberRange(min=1, max=1000000)])
    category = StringField('Category', [validators.Length(min=1, max=200)])
    date = StringField('Date', [validators.Length(min=1, max=200)])
    description = StringField('Description', [validators.Length(min=1, max=200)])

class SignUpForm(Form):
    first_name = StringField('First Name', [validators.Length(min=1, max=100)])
    last_name = StringField('Last Name', [validators.Length(min=1, max=100)])
    email = EmailField('Email address', [validators.DataRequired(), validators.Email()])
    username = StringField('Username', [validators.Length(min=4, max=100)])
    password = PasswordField('Password', [
        validators.DataRequired(),
        validators.EqualTo('confirm', message='Passwords do not match')
    ])
    confirm = PasswordField('Confirm Password')

class LoginForm(Form):
    username = StringField('Username', [validators.Length(min=4, max=100)])
    password = PasswordField('Password', [validators.DataRequired()])




def is_logged_in(f):
    @wraps(f)
    def wrap(*args, **kwargs):
        if 'logged_in' in session:
            return f(*args, **kwargs)
        else:
            flash('Please login', 'info')
            return redirect(url_for('login'))
    return wrap

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/about')
@is_logged_in
def about():
    return render_template('about.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if 'logged_in' in session:
        flash('You are already logged in', 'info')
        return redirect(url_for('addTransactions'))

    form = SignUpForm(request.form)
    if request.method == 'POST' and form.validate():
        first_name = form.first_name.data
        last_name = form.last_name.data
        email = form.email.data
        username = form.username.data
        password = sha256_crypt.encrypt(str(form.password.data))

        with mysql.connection.cursor() as cur:
            result = cur.execute("SELECT * FROM users WHERE email=%s", [email])
            if result > 0:
                flash('The entered email address has already been taken. Please try using or creating another one.', 'info')
                return redirect(url_for('signup'))
            else:
                cur.execute("INSERT INTO users(first_name, last_name, email, username, password) VALUES(%s, %s, %s, %s, %s)",
                            (first_name, last_name, email, username, password))
                mysql.connection.commit()
                flash('You are now registered and can log in', 'success')
                return redirect(url_for('login'))

    return render_template('signUp.html', form=form)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'logged_in' in session:
        flash('You are already logged in', 'info')
        return redirect(url_for('addTransactions'))

    form = LoginForm(request.form)
    if request.method == 'POST' and form.validate():
        username = form.username.data
        password_input = form.password.data

        with mysql.connection.cursor() as cur:
            result = cur.execute("SELECT * FROM users WHERE username = %s", [username])
            if result > 0:
                data = cur.fetchone()
                password = data['password']
                if sha256_crypt.verify(password_input, password):
                    session['logged_in'] = True
                    session['username'] = username
                    session['userID'] = data['id']
                    flash('You are now logged in', 'success')
                    return redirect(url_for('addTransactions'))
                else:
                    error = 'Invalid Password'
                    return render_template('login.html', form=form, error=error)
            else:
                error = 'Username not found'
                return render_template('login.html', form=form, error=error)

    return render_template('login.html', form=form)

@app.route('/logout')
@is_logged_in
def logout():
    session.clear()
    flash('You are now logged out', 'success')
    return redirect(url_for('login'))


def extract_withdrawal_transactions(file_path):
    transactions = []

    try:
        # Use tabula to extract tables from the PDF
        dfs = tabula.read_pdf(file_path, pages='all', stream=True)

        for df in dfs:
            for index, row in df.iterrows():
                print(f"Processing row {index}: {row}")  # Debugging output

                if len(row) > 4:  # Ensure there are enough columns in the row
                    transaction_type = str(row[1] ) # Assuming UPI/DR or similar is in the second column

                    # Check if this is a withdrawal transaction
                    if is_withdrawal_transaction(transaction_type):
                        try:
                            # Extract date and amount from relevant columns
                            date_str = str(row[0]).strip()  # Assuming date is in the first column
                            amount_str = str(row[4]).replace(",", "").strip()  # Assuming amount is in the fifth column

                            # Debugging output for extracted values
                            print(f"Extracted date: '{date_str}', amount: '{amount_str}'")

                            # Check if date or amount fields are empty
                            if not date_str or not amount_str:
                                print(f"Skipping due to empty date or amount: {row}")
                                continue

                            # Convert date and amount
                            transaction_date = dt.strptime(date_str, "%d-%m-%Y").date()
                            amount = float(amount_str)

                            # Ignore zero or invalid amounts
                            if amount <= 0:
                                print(f"Skipping non-positive amount transaction: {row}")
                                continue

                            # Assuming description can be constructed from other columns
                            description = " ".join(map(str, row[2:4]))  # Adjust based on your actual data structure

                            # Add the withdrawal transaction to the list
                            transactions.append({
                                "date": transaction_date,
                                "description": description,
                                "amount": amount,
                                "category": infer_category(description)  # This function can be expanded as needed
                            })

                        except ValueError as ve:
                            print(f"Skipping invalid line due to parsing error: {row} - {ve}")
                            continue

            print(f"Total transactions extracted: {len(transactions)}")

    except Exception as e:
        print(f"Error reading PDF with tabula: {e}")

    return transactions

def is_withdrawal_transaction(transaction_type):
    """
    Determine if the transaction type indicates a withdrawal.
    This function can be expanded with more rules as needed.
    """
    withdrawal_keywords = ["UPI/DR", "Withdrawal", "Debit", "Transfer"]
    return any(keyword in transaction_type for keyword in withdrawal_keywords)

def infer_category(description):
    description = description.lower()
    if "grocery" or "supermarket" or "zepto" or "blinkit" or "jiomart" or "bigbasket" or "kiranakart" in description():
        return "Grocery"
    elif "fuel"or "hp" or "bharatpetroleum" or "indianoil" or "hpcl" or "iocl" or "bpcl" or "bp" or "iocl" in description():

        return "Fuel"
    elif "restaurant" or "food" or "dine" or "eat" or "hotel " or "cafe" or "bar" or "pub" or "kfc" or "pizzahut" or "dominos" or "burgerking" in description():
        return "Food"
    elif "travel" or "flight" or "air" or "train" or "bus" in description:
        return "Travel"
    elif "bookmyshow"  in description:
        return "Movies"
    elif "amazon" in description:
        return "Amazon"
    elif "flipkart" in description:
        return "Flipkart"
    elif "myntra" in description:
        return "Myntra"
    elif "paytm" in description:
        return "Paytm"
    elif "zomato" in description:
        return "Zomato"
    elif "uber" in description:
         return "Uber"
    elif "olacabs" in description:
        return "Ola"
    elif "swiggy" in description:
        return "Swiggy"
    elif "dunzo" in description:
        return "Dunzo"
    elif "tata" in description:
        return "Tata"
    elif "medplus" in description:
        return "Medplus"
    elif "apollo" in description:
        return "Apollo"
    elif "pharmacy" in description:
        return "Pharmacy"
    elif "mobile" or "phone" or "recharge" or "airtel" or "jio" or "vodafone" or "idea" or "bharti" in description():
        return "Mobile recharge "
    
    
    elif "transfer" in description:
        return "Transfer"
    elif "upi" in description:
        return "UPI Payment"
    else:
        return "Uncategorized"

# In the upload_pdf function, ensure that the extracted transactions are saved to the database
@app.route('/upload_pdf', methods=['POST'])
@is_logged_in
def upload_pdf():
    user_id = session.get('userID')
    if not user_id:
        flash('Please login first', 'danger')
        return redirect(url_for('login'))

    if 'pdf_file' not in request.files:
        return jsonify({'success': False, 'message': 'No file part'}), 400

    file = request.files['pdf_file']

    if file.filename == '':
        return jsonify({'success': False, 'message': 'No selected file'}), 400

    try:
        # Save the file to the specified directory
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
        file.save(file_path)

        # Process the PDF file for withdrawal transactions
        withdrawals = extract_withdrawal_transactions(file_path)
        if withdrawals:
            save_withdrawals_to_db(withdrawals, user_id)

        return jsonify({'success': True, 'message': 'File uploaded and transactions processed successfully!'}), 200

    except Exception as e:
        print(f"Error processing the PDF file: {e}")
        return jsonify({'success': False, 'message': 'Error processing the file'}), 500

def extract_withdrawal_transactions(file_path):
    transactions = []

    try:
        # Use pdfplumber to extract tables from the PDF
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                table = page.extract_table()
                
                if table:
                    # Convert the extracted table into a DataFrame for easier manipulation
                    df = pd.DataFrame(table[1:], columns=table[0])
                    
                    # Debugging output to check the first few rows
                    print(df.head())
                    
                    for index, row in df.iterrows():
                        print(f"Processing row {index}: {row}")  # Debugging output

                        if len(row) > 4:  # Ensure there are enough columns in the row
                            transaction_type = str(row[1])  # Assuming transaction type is in the second column

                            # Check if this is a withdrawal transaction
                            if is_withdrawal_transaction(transaction_type):
                                try:
                                    # Extract date and amount from relevant columns
                                    date_str = str(row[0]).strip()  # Assuming date is in the first column
                                    amount_str = str(row[4]).replace(",", "").strip()  # Assuming amount is in the fifth column

                                    # Debugging output for extracted values
                                    print(f"Extracted date: '{date_str}', amount: '{amount_str}'")

                                    # Check if date or amount fields are empty
                                    if not date_str or not amount_str:
                                        print(f"Skipping due to empty date or amount: {row}")
                                        continue

                                    # Convert date and amount
                                    transaction_date = dt.strptime(date_str, "%d-%m-%Y").date()
                                    amount = float(amount_str)

                                    # Ignore zero or invalid amounts
                                    if amount <= 0:
                                        print(f"Skipping non-positive amount transaction: {row}")
                                        continue

                                    # Assuming description can be constructed from other columns
                                    description = " ".join(map(str, row[2:4]))  # Adjust based on your actual data structure

                                    # Add the withdrawal transaction to the list
                                    transactions.append({
                                        "date": transaction_date,
                                        "description": description,
                                        "amount": amount,
                                        "category": infer_category(description)  # This function can be expanded as needed
                                    })

                                except ValueError as ve:
                                    print(f"Skipping invalid line due to parsing error: {row} - {ve}")
                                    continue

            print(f"Total transactions extracted: {len(transactions)}")

    except Exception as e:
        print(f"Error reading PDF with pdfplumber: {e}")

    return transactions

def is_withdrawal_transaction(transaction_type):
    """
    Determine if the transaction type indicates a withdrawal.
    This function can be expanded with more rules as needed.
    """
    withdrawal_keywords = ["UPI/DR", "Withdrawal", "Debit", "Transfer"]
    return any(keyword in transaction_type for keyword in withdrawal_keywords)


def save_withdrawals_to_db(transactions, user_id):
    try:
        with mysql.connection.cursor() as cur:
            for transaction in transactions:
                # Check if the transaction already exists in the database
                cur.execute("""
                    SELECT COUNT(*) FROM transactions 
                    WHERE user_id = %s 
                    AND date = %s 
                    AND description = %s 
                    AND amount = %s
                """, (
                    user_id,
                    transaction["date"],
                    transaction["description"],
                    int(transaction["amount"])
                ))
                
                # If the transaction doesn't exist, insert it
                if cur.fetchone()[0] == 0:
                    cur.execute("""
                        INSERT INTO transactions (user_id, date, description, amount, category)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (
                        user_id,
                        transaction["date"],
                        transaction["description"],
                        int(transaction["amount"]),
                        transaction["category"]
                    ))
                    print(f"Transaction added: {transaction}")
                else:
                    # Flash a message for duplicate transactions
                    flash(f"Duplicate transaction skipped: {transaction['description']} on {transaction['date']} with amount {transaction['amount']}", 'warning')

            mysql.connection.commit()
            print("Transactions processed successfully.")
    except Exception as e:
        print(f"Database error: {e}")





@app.route('/addTransactions', methods=['GET', 'POST'])
@is_logged_in
def addTransactions():
    if request.method == 'POST':
        # Handle regular form submission
        if 'amount' in request.form:
            amount = request.form['amount']
            description = request.form['description']
            category = request.form['category']

            # Insert the transaction into the database
            with mysql.connection.cursor() as cur:
                cur.execute("INSERT INTO transactions(user_id, amount, description, category) VALUES(%s, %s, %s, %s)",
                            (session['userID'], amount, description, category))
                mysql.connection.commit()

                # Flash a success message after the transaction is recorded
                flash('Transaction Successfully Recorded', 'success')

                # Redirect to avoid resubmission
                return redirect(url_for('addTransactions'))

    # Fetch total expenses and transactions for rendering
    with mysql.connection.cursor() as cur:
        cur.execute("SELECT SUM(amount) FROM transactions WHERE MONTH(date) = MONTH(CURRENT_DATE()) AND YEAR(date) = YEAR(CURRENT_DATE()) AND user_id = %s", [session['userID']])
        totalExpenses = cur.fetchone()['SUM(amount)'] or 0

        cur.execute("SELECT * FROM transactions WHERE MONTH(date) = MONTH(CURRENT_DATE()) AND YEAR(date) = YEAR(CURRENT_DATE()) AND user_id = %s ORDER BY date DESC", [session['userID']])
        transactions = cur.fetchall()

        for transaction in transactions:
            transaction['date'] = timeago.format(transaction['date'], datetime.now()) if datetime.now() - transaction['date'] < timedelta(days=0.5) else transaction['date'].strftime('%d %B, %Y')

        return render_template('addTransactions.html', totalExpenses=totalExpenses, transactions=transactions)
@app.route('/transactionHistory',methods=['GET','POST'])
@is_logged_in
def transactionHistory():
    user_id = session['userID']
    selected_category = request.args.get('category', default=None)

    with mysql.connection.cursor() as cur:
        cur.execute("SELECT DISTINCT category FROM transactions WHERE user_id = %s", [user_id])
        categories = cur.fetchall()

        if request.method == 'POST':
            month = request.form['month']
            year = request.form['year']
            if month == "00":
                cur.execute("SELECT SUM(amount) FROM transactions WHERE YEAR(date) = %s AND user_id = %s", [year, user_id])
            else:
                cur.execute("SELECT SUM(amount) FROM transactions WHERE MONTH(date) = %s AND YEAR(date) = %s AND user_id = %s", [month, year, user_id])
            totalExpenses = cur.fetchone()['SUM(amount)'] or 0

            cur.execute("SELECT * FROM transactions WHERE MONTH(date) = %s AND YEAR(date) = %s AND user_id = %s ORDER BY date DESC", [month, year, user_id])
            transactions = cur.fetchall()
        else:
            cur.execute("SELECT SUM(amount) FROM transactions WHERE user_id = %s", [user_id])
            totalExpenses = cur.fetchone()['SUM(amount)'] or 0
            category_filter = f"AND category = '{selected_category}'" if selected_category else ''
            cur.execute(f"SELECT * FROM transactions WHERE user_id = %s {category_filter} ORDER BY date DESC", [user_id])
            transactions = cur.fetchall()

        for transaction in transactions:
            transaction['date'] = transaction['date'].strftime('%d %B, %Y')

        return render_template('transactionHistory.html', totalExpenses=totalExpenses, transactions= transactions, categories=categories, selected_category=selected_category)


@app.route('/track_budget', methods=['GET', 'POST'])
@is_logged_in
def track_budget():
    user_id = session.get('userID')
    if not user_id:
        flash('Please login first', 'danger')
        return redirect(url_for('login'))

    with mysql.connection.cursor() as cur:
        cur.execute("SELECT budget_password FROM users WHERE id = %s", [user_id])
        user = cur.fetchone()

        if request.method == 'POST':
            if user['budget_password'] is None:
                new_password = request.form.get('new_password')
                confirm_password = request.form.get('confirm_password')

                if new_password and new_password == confirm_password:
                    hashed_password = sha256_crypt.hash(new_password)
                    cur.execute("UPDATE users SET budget_password = %s WHERE id = %s", (hashed_password, user_id))
                    mysql.connection.commit()
                    flash('Budget password created successfully. You can now update your budget.', 'success')
                    return redirect(url_for('track_budget'))
                else:
                    flash('Passwords do not match. Please try again.', 'danger')
            else:
                password_input = request.form.get('password')
                monthly_budget = request.form.get('monthly_budget')
                monthly_savings_goal = request.form.get('monthly_savings_goal')

                if sha256_crypt.verify(password_input, user['budget_password']):
                    cur.execute("""
                        SELECT COUNT(*) as update_count 
                        FROM user_budget 
                        WHERE user_id = %s AND MONTH(updated_at) = MONTH(CURRENT_DATE()) AND YEAR(updated_at) = YEAR(CURRENT_DATE())
                    """, [user_id])
                    update_count = cur.fetchone()['update_count']

                    if update_count < 3:
                        cur.execute("SELECT * FROM user_budget WHERE user_id = %s", [user_id])
                        exists = cur.fetchone()

                        if exists:
                            cur.execute("""
                                UPDATE user_budget 
                                SET monthly_budget = %s, monthly_savings_goal = %s, updated_at = CURRENT_TIMESTAMP
                                WHERE user_id = %s
                            """, (monthly_budget, monthly_savings_goal, user_id))
                        else:
                            cur.execute("""
                                INSERT INTO user_budget (user_id, monthly_budget, monthly_savings_goal)
                                VALUES (%s, %s, %s)
                            """, (user_id, monthly_budget, monthly_savings_goal))

                        mysql.connection.commit()
                        flash('Budget updated successfully', 'success')
                    else:
                        flash('You have reached the maximum number of updates for this month.', 'warning')
                else:
                    flash('Invalid password. Please try again.', 'danger')

        cur.execute("SELECT monthly_budget, monthly_savings_goal FROM user_budget WHERE user_id = %s", [user_id])
        budget_data = cur.fetchone()

        if not budget_data:
            budget_data = {'monthly_budget': 0, 'monthly_savings_goal': 0}
        
        monthly_budget = budget_data['monthly_budget']
        monthly_savings_goal = budget_data['monthly_savings_goal']

        # Fetch total spending for the month
        cur.execute("""
            SELECT COALESCE(SUM(amount), 0) as total_spent
            FROM transactions
            WHERE user_id = %s AND MONTH(date) = MONTH(CURRENT_DATE()) AND YEAR(date) = YEAR(CURRENT_DATE())
        """, [user_id])
        total_spent = cur.fetchone()['total_spent']

        # Calculate remaining budget
        remaining_budget = monthly_budget - monthly_savings_goal - total_spent

        # Calculate progress
        if remaining_budget > 0:
            progress_percentage = (total_spent / remaining_budget) * 100
        else:
            progress_percentage = 100 if total_spent > 0 else 0

        cur.execute("SELECT DISTINCT category FROM transactions WHERE user_id = %s ORDER BY category", [user_id])
        categories = [row['category'] for row in cur.fetchall()]

        cur.execute("""
            SELECT cb.category, cb.budget_limit,
                   COALESCE(SUM(t.amount), 0) as current_spending,
                   cb.budget_limit - COALESCE(SUM(t.amount), 0) as remaining
            FROM category_budgets cb
            LEFT JOIN transactions t ON cb.category = t.category 
                AND cb.user_id = t.user_id 
                AND MONTH(t.date) = MONTH(CURRENT_DATE())
                AND YEAR(t.date) = YEAR(CURRENT_DATE())
            WHERE cb.user_id = %s
            GROUP BY cb.category, cb.budget_limit
        """, [user_id])
        category_budgets = cur.fetchall()

        if not category_budgets:
            category_budgets = []

    return render_template(
        'track_budget.html',progress_percentage=progress_percentage,
        float=float,remaining_budget=remaining_budget,total_spent=total_spent,
        budget_data=budget_data,
        categories=categories,
        category_budgets=category_budgets,
        user_has_password=user['budget_password'] is not None
    )


      
@app.route('/set_category_budget', methods=['POST'])
@is_logged_in
def set_category_budget():
    user_id = session['userID']
    category = request.form.get('category')
    budget_limit = request.form.get('budget_limit')

    with mysql.connection.cursor() as cur:
        cur.execute("SELECT * FROM category_budgets WHERE user_id = %s AND category = %s", (user_id, category))
        existing_budget = cur.fetchone()

        if existing_budget:
            flash('Budget limit already exists. Delete this current one to proceed.', 'danger')
        else:
            try:
                # Insert the new budget limit if it doesn't exist
                cur.execute("INSERT INTO category_budgets (user_id, category, budget_limit) VALUES (%s, %s, %s)", (user_id, category, budget_limit))
                mysql.connection.commit()
                flash('Category budget set successfully', 'success')
            except IntegrityError:
                mysql.connection.rollback()  # Rollback the transaction in case of an error
                flash('An error occurred while setting the budget. Please try again.', 'danger')

    return redirect(url_for('track_budget'))
@app.route('/category_budget/delete/<category>', methods=['POST'])
@is_logged_in
def delete_category_budget(category):
    user_id=session['userID']
    if not user_id:
        flash('Please login first', 'danger')
        return redirect(url_for('login'))

    with mysql.connection.cursor() as cur:
        try:
            cur.execute("DELETE FROM category_budgets WHERE user_id = %s AND category = %s", (user_id, category))
            mysql.connection.commit()
            flash('Category budget deleted successfully', 'success')
        except Exception as e:
            flash('Error deleting category budget', 'danger')
            print(f"Error: {e}")

    return redirect(url_for('track_budget'))

@app.route('/deleteTransaction/<string:id>', methods=['POST'])
@is_logged_in
def deleteTransaction(id):
    with mysql.connection.cursor() as cur:
        cur.execute("DELETE FROM transactions WHERE id = %s", [id])
        mysql.connection.commit()

    flash('Transaction Deleted', 'success')
    return redirect(url_for('transactionHistory'))

@app.route('/editCurrentMonthTransaction/<string:id>', methods=['GET', 'POST'])
@is_logged_in
def editCurrentMonthTransaction(id):
    with mysql.connection.cursor() as cur:
        cur.execute("SELECT * FROM transactions WHERE id = %s", [id])
        transaction = cur.fetchone()

    form = TransactionForm(request.form)
    form.amount.data = transaction['amount']
    form.description.data = transaction['description']

    if request.method == 'POST' and form.validate():
        amount = form.amount.data
        description = form.description.data

        with mysql.connection.cursor() as cur:
            cur.execute("UPDATE transactions SET amount=%s, description=%s WHERE id = %s",
                        (amount, description, id))
            mysql.connection.commit()

        flash('Transaction Updated', 'success')
        return redirect(url_for('addTransactions'))

    return render_template('editTransaction.html', form=form)

@app.route('/deleteCurrentMonthTransaction/<string:id>', methods=['POST'])
@is_logged_in
def deleteCurrentMonthTransaction(id):
    with mysql.connection.cursor() as cur:
        cur.execute("DELETE FROM transactions WHERE id = %s", [id])
        mysql.connection.commit()

    flash('Transaction Deleted', 'success')
    return redirect(url_for('addTransactions'))



@app.route('/category')
def createBarCharts():
    with mysql.connection.cursor() as cur:
        cur.execute("SELECT SUM(amount) AS amount, category FROM transactions WHERE YEAR(date) = YEAR(CURRENT_DATE()) AND user_id = %s GROUP BY category ORDER BY category", [session['userID']])
        transactions = cur.fetchall()

        values = [transaction['amount'] for transaction in transactions]
        labels = [transaction['category'] for transaction in transactions]

        fig = go.Figure(data=[go.Pie(labels=labels, values=values)])
        fig.update_traces(textinfo='label+value', hoverinfo='percent')
        fig.update_layout(title_text='Category Wise Pie Chart For Current Year')
        fig.show()

    return redirect(url_for('addTransactions'))

@app.route('/yearly_bar')
def yearlyBar():
    with mysql.connection.cursor() as cur:
        year_data = []
        for month in range(1, 13):
            cur.execute("SELECT SUM(amount) FROM transactions WHERE MONTH(date ) = %s AND YEAR(date) = YEAR(CURRENT_DATE()) AND user_id = %s", (month, session['userID']))
            year_data.append(cur.fetchone()['SUM(amount)'] or 0)

        last_year_data = []
        for month in range(1, 13):
            cur.execute("SELECT SUM(amount) FROM transactions WHERE MONTH(date) = %s AND YEAR(date) = YEAR(DATE_SUB(CURDATE(), INTERVAL 1 YEAR)) AND user_id = %s", (month, session['userID']))
            last_year_data.append(cur.fetchone()['SUM(amount)'] or 0)

        year_labels = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        fig = go.Figure(data=[
            go.Bar(name='Last Year', x=year_labels, y=last_year_data),
            go.Bar(name='This Year', x=year_labels, y=year_data)
        ])
        fig.update_layout(barmode='group', title_text='Comparison Between This Year and Last Year')
        fig.show()

    return redirect(url_for('addTransactions'))

@app.route('/monthly_bar')
def monthlyBar():
    with mysql.connection.cursor() as cur:
        cur.execute("SELECT SUM(amount) as amount, MONTH(date) as month FROM transactions WHERE YEAR(date) = YEAR(CURRENT_DATE()) AND user_id = %s GROUP BY MONTH(date) ORDER BY MONTH(date)", [session['userID']])
        transactions = cur.fetchall()

        months = []
        values = []

        for transaction in transactions:
            if 'month' in transaction and 'amount' in transaction:
                months.append(transaction['month'])
                values.append(transaction['amount'])

        fig = go.Figure([go.Bar(x=months, y=values)])
        fig.update_layout(title_text='Monthly Bar Chart For Current Year')
        fig.show()

    return redirect(url_for('addTransactions'))
@app.route('/dashboard', methods=['GET'])
@is_logged_in
def dashboard():
    user_id = session['userID']
    
    if not user_id:
        flash('User  ID not found in session. Please log in again.', 'danger')
        return redirect(url_for('login'))

    with mysql.connection.cursor() as cur:
        # Get spending data for the last month
        thirty_days_ago = datetime.now() - timedelta(days=30)
        cur.execute('''
            SELECT DATE(date) as date, SUM(amount) as amount
            FROM transactions
            WHERE user_id = %s AND date >= %s
            GROUP BY DATE(date)
            ORDER BY date
        ''', (user_id, thirty_days_ago))

        rows = cur.fetchall()
        print("Rows fetched:", rows)

        # Prepare data for the daily spending chart
        daily_spending = []
        for row in rows:
            daily_spending.append({
                'date': row['date'].strftime('%Y-%m-%d'),  # Format date as string
                'amount': float(row['amount']) if row['amount'] is not None else 0.0
            })

        print("Daily Spending Data:", daily_spending)

        # Get category-wise spending
        cur.execute('''
            SELECT category, SUM(amount) as amount
            FROM transactions
            WHERE user_id = %s
            GROUP BY category
        ''', (user_id,))
        
        category_spending = [{'category': row['category'], 'amount': float(row['amount'])} for row in cur.fetchall()]

        # Get total spending
        cur.execute('''
            SELECT 
                SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) as total_spending
            FROM transactions
            WHERE user_id = %s
        ''', (user_id,))
        
        financial_summary = cur.fetchone()
        financial_summary = {
            'total_spending': float(financial_summary['total_spending']) if financial_summary['total_spending'] is not None else 0
        }

    return render_template('dashboard.html', user_id=user_id, 
                           daily_spending=daily_spending,
                           category_spending=category_spending, 
                           financial_summary=financial_summary)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5002, debug=True)