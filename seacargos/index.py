import functools

from flask import (
    Blueprint, flash, g, redirect, render_template, session, request, url_for
)
from werkzeug.exceptions import abort
from werkzeug.security import check_password_hash, generate_password_hash
from seacargos.db import db_conn
from bson.objectid import ObjectId

bp = Blueprint('home', __name__)

def user_login_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            return redirect(url_for('home'))
        elif g.user['role'] != 'user':
            abort(403, 'You are note authorized to view this page.')
        return view(**kwargs)
    return wrapped_view

@bp.before_app_request
def load_logged_in_user():
    """Loads logged in user from session to g."""
    user_id = session.get('user_id')

    if user_id is None:
        g.user = None
    else:
        #conn = db_conn()
        #g.user = conn.seacargos.users.find_one({'_id': user_id})
        g.user = db_conn().seacargos.users.find_one({'_id': ObjectId(user_id)})

@bp.route('/', methods=('GET', 'POST'))
def home():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = db_conn()
        error = None
        user = conn.seacargos.users.find_one({"name": username})

        if user is None:
            error = 'Incorrect username.'
        elif not check_password_hash(user['password'], password):
            error = 'Incorrect password.'
        
        if error is None:
            session.clear()
            session['user_id'] = user['_id'].__str__()
            if user['role'] == 'admin':
                return redirect(url_for('admin'))
            elif user['role'] == 'user':
                return redirect(url_for('home.dashboard'))
        
        flash(error)
    conn = db_conn()
    db = conn.seacargos
    content = {}
    content["vessels"] = db.vessels.count_documents({})
    content["users"] = db.users.count_documents({})
    content["shipments"] = db.shipments.count_documents({})
    content["tracking"] = db.tracking.count_documents({})
    content["logs"] = db.logs.count_documents({})
    ps_ = generate_password_hash("xyz")
    content['passtype'] = type(ps_)
    content['password'] = ps_
    content['g'] = g.user
    content['sessonUser'] = session.keys()
    return render_template('home/home.html', content=content)
    
    #return render_template('home/home.html')

@bp.route('/dashboard')
@user_login_required
def dashboard():
    """Home dashboard view function."""
    content = None
    # temporary return, create dashboard template
    return render_template('home/home.html', content=content)

@bp.route('/logout')
def logout():
    """Logout function."""
    session.clear()
    return redirect(url_for('home'))
