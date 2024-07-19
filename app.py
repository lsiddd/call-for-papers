from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import pandas as pd
from datetime import datetime
from functools import wraps

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# List of preferred conferences
preferred_conferences = [
    "IEEE",
    "ACM",
]

# Decorator for routes that require login
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('is_admin'):
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def get_conferences():
    conn = sqlite3.connect('conferences.db')
    df = pd.read_sql_query("SELECT id, conference_name, link, additional_details, when_date, where_location, deadline FROM conferences WHERE deleted = 0", conn)
    conn.close()

    # Calculate days until deadline
    df['days_until_deadline'] = df['deadline'].apply(lambda x: (datetime.strptime(x.strip(), '%b %d, %Y').date() - datetime.now().date()).days)

    return df

def init_db():
    conn = sqlite3.connect('conferences.db')
    c = conn.cursor()
    # Create table if not exists
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            is_admin BOOLEAN NOT NULL DEFAULT 0
        )
    ''')
    conn.commit()
    # Check if admin user exists, if not create one
    c.execute("SELECT * FROM users WHERE username = 'admin'")
    if not c.fetchone():
        c.execute("INSERT INTO users (username, password, is_admin) VALUES (?, ?, ?)",
                  ('admin', generate_password_hash('admin', method='pbkdf2:sha256'), True))
    conn.commit()
    conn.close()

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = sqlite3.connect('conferences.db')
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE username = ?", (username,))
        user = c.fetchone()
        conn.close()
        if user and check_password_hash(user[2], password):
            session['user_id'] = user[0]
            session['username'] = user[1]
            session['is_admin'] = user[3]
            return redirect(url_for('index'))
        return "Invalid credentials"
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    session.pop('user_id', None)
    session.pop('username', None)
    session.pop('is_admin', None)
    return redirect(url_for('login'))

@app.route('/admin', methods=['GET', 'POST'])
@login_required
@admin_required
def admin():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        is_admin = 'is_admin' in request.form
        conn = sqlite3.connect('conferences.db')
        c = conn.cursor()
        try:
            c.execute("INSERT INTO users (username, password, is_admin) VALUES (?, ?, ?)",
                      (username, generate_password_hash(password, method='pbkdf2:sha256'), is_admin))
            conn.commit()
        except sqlite3.IntegrityError:
            return "User already exists"
        conn.close()
    return render_template('admin.html')

@app.route('/api/conferences', methods=['GET'])
@login_required
def api_conferences():
    search_query = request.args.get('search[value]', default='', type=str)
    order_column = request.args.get('order[0][column]', default='0', type=str)
    order_dir = request.args.get('order[0][dir]', default='asc', type=str)

    conferences = get_conferences()

    if search_query:
        conferences = conferences[
            conferences.apply(lambda row: row.astype(str).str.contains(search_query, case=False).any(), axis=1)
        ]

    order_column_name = conferences.columns[int(order_column)]
    conferences = conferences.sort_values(by=order_column_name, ascending=(order_dir == 'asc'))

    mask = conferences.apply(lambda row: any(pref in row["conference_name"] or pref in row["additional_details"] for pref in preferred_conferences), axis=1)

    preferred_df = conferences[mask]
    other_df = conferences[~mask]

    return jsonify({
        'preferred': preferred_df.to_dict(orient='records'),
        'others': other_df.to_dict(orient='records'),
        'recordsTotal': len(conferences),
        'recordsFiltered': len(conferences)
    })

@app.route('/', methods=['GET', 'POST'])
@login_required
def index():
    return render_template('index.html')

@app.route('/manage_conferences', methods=['GET'])
@login_required
@admin_required
def manage_conferences():
    conferences = get_conferences()
    return render_template('manage_conferences.html', conferences=conferences.to_dict(orient='records'))

@app.route('/delete_conference/<int:id>', methods=['POST'])
@login_required
@admin_required
def delete_conference(id):
    conn = sqlite3.connect('conferences.db')
    c = conn.cursor()
    c.execute("UPDATE conferences SET deleted = 1 WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    flash('Conference marked as deleted successfully.')
    return redirect(url_for('manage_conferences'))

@app.route('/bulk_delete_conferences', methods=['POST'])
@login_required
@admin_required
def bulk_delete_conferences():
    conference_ids = request.form.getlist('conference_ids')
    if conference_ids:
        conn = sqlite3.connect('conferences.db')
        c = conn.cursor()
        c.execute("UPDATE conferences SET deleted = 1 WHERE id IN ({})".format(','.join('?' * len(conference_ids))), conference_ids)
        conn.commit()
        conn.close()
        flash('Selected conferences marked as deleted successfully.')
    else:
        flash('No conferences selected for deletion.')
    return redirect(url_for('manage_conferences'))

@app.route('/edit_conference/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_conference(id):
    if request.method == 'POST':
        conference_name = request.form['conference_name']
        link = request.form['link']
        additional_details = request.form['additional_details']
        when_date = request.form['when_date']
        where_location = request.form['where_location']
        deadline = request.form['deadline']

        conn = sqlite3.connect('conferences.db')
        c = conn.cursor()
        c.execute('''
            UPDATE conferences
            SET conference_name = ?, link = ?, additional_details = ?, when_date = ?, where_location = ?, deadline = ?
            WHERE id = ?
        ''', (conference_name, link, additional_details, when_date, where_location, deadline, id))
        conn.commit()
        conn.close()
        flash('Conference updated successfully.')
        return redirect(url_for('manage_conferences'))

    conn = sqlite3.connect('conferences.db')
    c = conn.cursor()
    c.execute("SELECT * FROM conferences WHERE id = ?", (id,))
    conference = c.fetchone()
    conn.close()

    if not conference:
        flash('Conference not found.')
        return redirect(url_for('manage_conferences'))

    conference_dict = {
        'id': conference[0],
        'conference_name': conference[1],
        'link': conference[2],
        'additional_details': conference[3],
        'when_date': conference[4],
        'where_location': conference[5],
        'deadline': conference[6]
    }

    return render_template('edit_conference.html', conference=conference_dict)

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
