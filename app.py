from flask import Flask, render_template, request, redirect, url_for, session, jsonify, make_response
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from functools import wraps
import json
import os
import random
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = 'secretneonkey'

MEMES_FILE = 'memes.json'
USERS_FILE = 'users.json'
UPLOAD_FOLDER = os.path.join('static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ---------- ПРЕДЗАГРУЖЕННЫЕ МЕМЫ (ПУСТО) ----------
DEFAULT_MEMES = []

# ---------- Функции работы с данными ----------
def load_memes():
    if not os.path.exists(MEMES_FILE):
        save_memes(DEFAULT_MEMES)
        return DEFAULT_MEMES
    try:
        with open(MEMES_FILE, 'r', encoding='utf-8') as f:
            memes = json.load(f)
            if not isinstance(memes, list):
                save_memes(DEFAULT_MEMES)
                return DEFAULT_MEMES
            return memes
    except:
        save_memes(DEFAULT_MEMES)
        return DEFAULT_MEMES

def save_memes(memes):
    with open(MEMES_FILE, 'w', encoding='utf-8') as f:
        json.dump(memes, f, ensure_ascii=False, indent=2)

def get_meme_by_id(meme_id):
    memes = load_memes()
    for m in memes:
        if m['id'] == meme_id:
            return m
    return None

# ---------- Пользователи ----------
def load_users():
    if not os.path.exists(USERS_FILE) or os.path.getsize(USERS_FILE) == 0:
        admin = {'id': 1, 'username': 'admin', 'password_hash': generate_password_hash('1111'), 'is_admin': True}
        save_users([admin])
        return [admin]
    try:
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            users = json.load(f)
            if not users:
                admin = {'id': 1, 'username': 'admin', 'password_hash': generate_password_hash('1111'), 'is_admin': True}
                save_users([admin])
                return [admin]
            return users
    except:
        admin = {'id': 1, 'username': 'admin', 'password_hash': generate_password_hash('1111'), 'is_admin': True}
        save_users([admin])
        return [admin]

def save_users(users):
    with open(USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(users, f, ensure_ascii=False, indent=2)

def get_user_by_id(user_id):
    users = load_users()
    for u in users:
        if u['id'] == user_id:
            return u
    return None

def get_user_by_username(username):
    users = load_users()
    for u in users:
        if u['username'] == username:
            return u
    return None

@app.context_processor
def utility_processor():
    def is_admin():
        if 'user_id' in session:
            user = get_user_by_id(session['user_id'])
            return user and user.get('is_admin', False)
        return False
    theme = request.cookies.get('theme', 'dark')
    return dict(get_user_by_id=get_user_by_id, get_user_by_username=get_user_by_username,
                is_admin=is_admin, theme=theme)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# ---------- Маршруты ----------
@app.route('/')
def index():
    query = request.args.get('q', '').strip().lower()
    memes = load_memes()
    if query:
        memes = [m for m in memes if query in m['title'].lower() or query in m['origin'].lower()]
    user_map = {u['id']: u['username'] for u in load_users()}
    for meme in memes:
        meme['author'] = user_map.get(meme.get('user_id'), 'Аноним')
    current_user = None
    if 'user_id' in session:
        user = get_user_by_id(session['user_id'])
        if user:
            current_user = user['username']
    now = datetime.now()
    week_ago = now - timedelta(days=7)
    weekly_memes = [m for m in load_memes() if datetime.fromisoformat(m['created_at']) >= week_ago]
    weekly_memes.sort(key=lambda x: x.get('likes', 0), reverse=True)
    weekly_top3 = weekly_memes[:3]
    for m in weekly_top3:
        m['author'] = user_map.get(m.get('user_id'), 'Аноним')
    random_meme = random.choice(load_memes()) if load_memes() else None
    if random_meme:
        random_meme['author'] = user_map.get(random_meme.get('user_id'), 'Аноним')
    return render_template('index.html', memes=memes, query=query, current_user=current_user,
                           weekly_top3=weekly_top3, random_meme=random_meme)

@app.route('/add', methods=['POST'])
@login_required
def add_meme():
    title = request.form.get('title', '').strip()
    origin = request.form.get('origin', '').strip()
    media_url = request.form.get('media_url', '').strip()
    uploaded_filename = None
    if 'media_file' in request.files:
        file = request.files['media_file']
        if file and file.filename:
            filename = secure_filename(file.filename)
            base, ext = os.path.splitext(filename)
            filename = f"{base}_{session['user_id']}_{int(datetime.now().timestamp())}{ext}"
            file.save(os.path.join(UPLOAD_FOLDER, filename))
            uploaded_filename = 'uploads/' + filename
    final_media = uploaded_filename if uploaded_filename else (media_url if media_url else None)
    if title and origin:
        memes = load_memes()
        new_id = max([m['id'] for m in memes], default=0) + 1
        memes.append({
            'id': new_id, 'title': title, 'origin': origin, 'media_url': final_media,
            'user_id': session['user_id'], 'likes': 0, 'dislikes': 0, 'views': 0,
            'created_at': datetime.now().isoformat(), 'comments': []
        })
        save_memes(memes)
    return redirect(url_for('index'))

@app.route('/edit/<int:meme_id>', methods=['GET', 'POST'])
@login_required
def edit_meme(meme_id):
    meme = get_meme_by_id(meme_id)
    if not meme:
        return redirect(url_for('index'))
    user = get_user_by_id(session['user_id'])
    if not user or (meme['user_id'] != session['user_id'] and not user.get('is_admin')):
        return "Нет прав", 403
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        origin = request.form.get('origin', '').strip()
        media_url = request.form.get('media_url', '').strip()
        if title and origin:
            memes = load_memes()
            for m in memes:
                if m['id'] == meme_id:
                    m['title'] = title
                    m['origin'] = origin
                    m['media_url'] = media_url if media_url else None
                    break
            save_memes(memes)
            return redirect(url_for('index'))
    return render_template('edit.html', meme=meme)

@app.route('/delete/<int:meme_id>', methods=['POST'])
@login_required
def delete_meme(meme_id):
    meme = get_meme_by_id(meme_id)
    if not meme:
        return redirect(url_for('index'))
    user = get_user_by_id(session['user_id'])
    if not user or (meme['user_id'] != session['user_id'] and not user.get('is_admin')):
        return "Нет прав", 403
    memes = load_memes()
    memes = [m for m in memes if m['id'] != meme_id]
    save_memes(memes)
    return redirect(url_for('index'))

@app.route('/clear_all', methods=['POST'])
@login_required
def clear_all():
    user = get_user_by_id(session['user_id'])
    if not user or not user.get('is_admin'):
        return "Только админ", 403
    save_memes([])
    return redirect(url_for('index'))

@app.route('/meme/<int:meme_id>')
def view_meme(meme_id):
    meme = get_meme_by_id(meme_id)
    if not meme:
        return redirect(url_for('index'))
    memes = load_memes()
    for m in memes:
        if m['id'] == meme_id:
            m['views'] = m.get('views', 0) + 1
            break
    save_memes(memes)
    meme['views'] = meme.get('views', 0) + 1
    user_map = {u['id']: u['username'] for u in load_users()}
    meme['author'] = user_map.get(meme.get('user_id'), 'Аноним')
    for c in meme.get('comments', []):
        c['author_name'] = user_map.get(c.get('author_id'), 'Аноним')
    return render_template('meme.html', meme=meme)

@app.route('/comment/<int:meme_id>', methods=['POST'])
@login_required
def add_comment(meme_id):
    text = request.form.get('comment', '').strip()
    if not text:
        return redirect(url_for('view_meme', meme_id=meme_id))
    memes = load_memes()
    for m in memes:
        if m['id'] == meme_id:
            m.setdefault('comments', []).append({
                'author_id': session['user_id'],
                'text': text,
                'date': datetime.now().strftime('%Y-%m-%d %H:%M')
            })
            break
    save_memes(memes)
    return redirect(url_for('view_meme', meme_id=meme_id))

@app.route('/like/<int:meme_id>', methods=['POST'])
def like_meme_ajax(meme_id):
    return vote_ajax(meme_id, 'like')

@app.route('/dislike/<int:meme_id>', methods=['POST'])
def dislike_meme_ajax(meme_id):
    return vote_ajax(meme_id, 'dislike')

def vote_ajax(meme_id, action):
    vote_key = f'voted_{meme_id}'
    memes = load_memes()
    for m in memes:
        if m['id'] == meme_id:
            prev = session.get(vote_key)
            if prev == 'like':
                m['likes'] = max(0, m['likes'] - 1)
            elif prev == 'dislike':
                m['dislikes'] = max(0, m['dislikes'] - 1)
            if action == 'like':
                m['likes'] = m.get('likes', 0) + 1
            else:
                m['dislikes'] = m.get('dislikes', 0) + 1
            session[vote_key] = action
            save_memes(memes)
            return jsonify({'likes': m['likes'], 'dislikes': m['dislikes']})
    return jsonify({'error': 'not found'}), 404

@app.route('/like/<int:meme_id>', methods=['GET'])
def like_meme_get(meme_id):
    vote(meme_id, 'like')
    return redirect(request.referrer or url_for('index'))

@app.route('/dislike/<int:meme_id>', methods=['GET'])
def dislike_meme_get(meme_id):
    vote(meme_id, 'dislike')
    return redirect(request.referrer or url_for('index'))

def vote(meme_id, action):
    vote_key = f'voted_{meme_id}'
    if session.get(vote_key) == action:
        return
    memes = load_memes()
    for m in memes:
        if m['id'] == meme_id:
            prev = session.get(vote_key)
            if prev == 'like':
                m['likes'] = max(0, m['likes'] - 1)
            elif prev == 'dislike':
                m['dislikes'] = max(0, m['dislikes'] - 1)
            if action == 'like':
                m['likes'] = m.get('likes', 0) + 1
            else:
                m['dislikes'] = m.get('dislikes', 0) + 1
            session[vote_key] = action
            break
    save_memes(memes)

@app.route('/user/<username>')
def user_profile(username):
    user = get_user_by_username(username)
    if not user:
        return "Пользователь не найден", 404
    memes = load_memes()
    user_memes = [m for m in memes if m.get('user_id') == user['id']]
    total_views = sum(m.get('views', 0) for m in user_memes)
    total_likes = sum(m.get('likes', 0) for m in user_memes)
    total_dislikes = sum(m.get('dislikes', 0) for m in user_memes)
    total_memes = len(user_memes)
    return render_template('user.html', profile_user=user, memes=user_memes,
                           total_views=total_views, total_likes=total_likes,
                           total_dislikes=total_dislikes, total_memes=total_memes)

@app.route('/random')
def random_meme():
    memes = load_memes()
    if memes:
        r = random.choice(memes)
        return redirect(url_for('view_meme', meme_id=r['id']))
    return redirect(url_for('index'))

@app.route('/browse')
def browse_start():
    memes = load_memes()
    if not memes:
        return redirect(url_for('index'))
    return redirect(url_for('browse_meme', meme_id=memes[0]['id']))

@app.route('/browse/<int:meme_id>')
def browse_meme(meme_id):
    meme = get_meme_by_id(meme_id)
    if not meme:
        return redirect(url_for('browse_start'))
    memes = load_memes()
    ids = [m['id'] for m in memes]
    current_index = ids.index(meme_id)
    prev_id = ids[current_index - 1] if current_index > 0 else None
    next_id = ids[current_index + 1] if current_index < len(ids) - 1 else None
    user_map = {u['id']: u['username'] for u in load_users()}
    meme['author'] = user_map.get(meme.get('user_id'), 'Аноним')
    for c in meme.get('comments', []):
        c['author_name'] = user_map.get(c.get('author_id'), 'Аноним')
    return render_template('browse.html', meme=meme, prev_id=prev_id, next_id=next_id)

@app.route('/set_theme/<theme>')
def set_theme(theme):
    if theme not in ('light', 'dark'):
        theme = 'dark'
    resp = make_response(redirect(request.referrer or url_for('index')))
    resp.set_cookie('theme', theme, max_age=60*60*24*365)
    return resp

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        if not username or not password:
            return render_template('register.html', error='Заполните все поля')
        users = load_users()
        if get_user_by_username(username):
            return render_template('register.html', error='Пользователь уже есть')
        new_id = max([u['id'] for u in users], default=0) + 1
        users.append({'id': new_id, 'username': username, 'password_hash': generate_password_hash(password), 'is_admin': False})
        save_users(users)
        session['user_id'] = new_id
        return redirect(url_for('index'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        user = get_user_by_username(username)
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            return redirect(url_for('index'))
        return render_template('login.html', error='Неверный логин или пароль')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)