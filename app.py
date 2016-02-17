from flask import Flask
from flask import render_template, abort, flash, request, session, g, redirect, url_for, send_from_directory
from flask_bootstrap import Bootstrap

from flask_wtf import Form
from wtforms import StringField, SubmitField, BooleanField, validators
from wtforms.validators import DataRequired

from flask.ext.sqlalchemy import SQLAlchemy
from flask.ext.login import current_user, login_required
from flask.ext.security import Security, SQLAlchemyUserDatastore, \
    UserMixin, RoleMixin

from datetime import timedelta
from werkzeug import secure_filename

from hashlib import md5
from PIL import Image
import sqlite3
import time

import os
import wtf_helpers

class IdeaForm(Form):
    idea_name = StringField('Idea name', validators=[DataRequired()])
    #Creates a field to type subject str
    idea_description = StringField('Idea description', [validators.optional(), validators.length(max=500)])
    is_private = BooleanField('Check to make it private')
    #Creates a boolean checkbox to mark private
    submit_button = SubmitField('Add idea')
    #Creates a button to post the str with the private attribute

app = Flask(__name__)
# in a real app, these should be configured through Flask-Appconfig
app.config['SECRET_KEY'] = 'devkey'
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ['DATABASE_URL']
app.config['SECURITY_REGISTERABLE'] = True
app.config['SECURITY_SEND_REGISTER_EMAIL'] = False
app.config['SECURITY_SEND_PASSWORD_CHANGE_EMAIL'] = False
app.config['SECURITY_SEND_PASSWORD_RESET_NOTICE_EMAIL'] = False
app.config['SECURITY_FLASH_MESSAGES'] = True

db = SQLAlchemy(app)
DATABASE = db
ALLOWED_EXTENSIONS = set(['png', 'jpg',
                          'jpeg', 'gif'])
UPLOAD_DIR = 'http://udenbrus.herokuapp.com/upload'

roles_users = db.Table('roles_users',
                       db.Column('user_id', db.Integer(), db.ForeignKey('user.id')),
                       db.Column('role_id', db.Integer(), db.ForeignKey('role.id')))


class Role(db.Model, RoleMixin):
    id = db.Column(db.Integer(), primary_key=True)
    name = db.Column(db.String(80), unique=True)
    subject = db.Column(db.String(50))
    #Added a description field
    description = db.Column(db.String(500))
    permissions = db.Column(db.Integer)


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True)
    password = db.Column(db.String(255))
    active = db.Column(db.Boolean())
    confirmed_at = db.Column(db.DateTime())
    roles = db.relationship('Role', secondary=roles_users,
                            backref=db.backref('users', lazy='dynamic'))

    ideas = db.relationship('Idea', backref='user', lazy='dynamic')

#Sets up Flask Security
user_datastore = SQLAlchemyUserDatastore(db, User, Role)
security = Security(app, user_datastore)


class Idea(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    idea_name = db.Column(db.String(50))
    idea_description = db.Column(db.String(500))
    is_private = db.Column(db.Boolean())
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))

    def __init__(self, idea, user):
        self.idea_name = idea
        self.user_id = user.id

#Formatted to Python 3.0 syntax
    def __repr__(self):
        return '<Idea {}>'.format(self.id)


db.create_all()

Bootstrap(app)
wtf_helpers.add_helpers(app)

#Changes the permanent session from 31 days to 5 minutes
@app.before_request()
def make_session_permanent():
    session.permanent = True
    app.permanent_session_lifetime = timedelta(minutes=5)

@app.route("/")
def index():
    #Creates a counter that increases on each page load, which is stored in session data
    try:
        session['counter'] += 1
    except KeyError:
        session['counter'] = 1
    return 'Number of reloads on the current session: {}'.format(session['counter'])
    users = User.query
    #Renders template with a timestamp
    return render_template("index.html", users=users, timestamp=datetime.now())

@app.route("/", methods = ['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        #Get the filestorage instance from request
        file = request.files['Upload File']
        filename = secure_filename(file.filename)
        #Render template with file information
        return render_template('file.html', filename = filename, type = file.content_type)

#Ensuring that the extension is in the ALLOWED_EXTENSIONS set
def check_extension(extension):
    return extension in ALLOWED_EXTENSIONS

def connect_db():
    return sqlite3.connect(app.config['DATABASE'])

#Returns a list of the last 5 uploaded images
def get_last_pics():
    try:
        cur = g.db.execute('select filename, label from pics order by id desc limit 5')
        filenames = [dict(id=row[0], filename=row[1], label=row[2]) for row in cur.fetchall()]
    except:
        return []

#Insert filename into database
def add_pic(filename, label):
    g.db.execute('insert into pics (filename, label) values (?, ?)', [filename, label])
    g.db.commit()

#Generates thumbnail image
def gen_thumbnail(filename):
    height = width = 80
    original = Image.open(os.path.join(app.config['UPLOAD_DIR'], filename))
    thumbnail = original.resize((width, height), Image.ANTIALIAS)
    thumbnail.save(os.path.join(app.config['UPLOAD_DIR'], 'thum_'+filename))

def add_label(label):
    label = request.form['label']
    g.db.execute('INSERT INTO pics (label) VALUES (?)', [label])
    g.db.commit()

@app.before_request
def before_request():
    g.db = connect_db()

@app.teardown_request
def teardown_request(exception):
    db = getattr(g, 'db', None)
    if db is not None:
        db.close()

@app.route('/', methods=['GET','POST'])
def upload_pic():
    if request.method == 'POST':
        file = request.files['file']
        label = request.form['label']
        extension = file.filename.rsplit('.', 1)[1].lower()
        try:
            extension = file.filename.rsplit('.', 1)[1].lower()
        except IndexError:
            abort(404)
        if file and check_extension(extension):
            # Salt and hash the file contents
            filename = md5(file.read() + str(round(time.time() * 1000))).hexdigest() + '.' + extension
            file.seek(0)
            # Move cursor back to beginning so we can write to disk
            file.save(os.path.join(app.config['UPLOAD_DIR'], filename, label))
            add_pic(filename, label)
            gen_thumbnail(filename)
            return redirect(url_for('show_pic', filename=filename))
        else: # Bad file extension
            abort(404)
    else:
        return render_template('upload.html', pics=get_last_pics())

@app.route('/show')
def show_pic():
    filename = request.args.get('filename','')
    t = (filename,)
    cur = g.db.execute('select label from pics where filename=?', t)
    label = cur.fetchone()[0]

    return render_template('upload.html', filename=filename, label=label)
def show_label():
    g.db = connect_db()
    cur = g.db.execute('SELECT label FROM pics WHERE id=(?)')
    labels = cur.fetchone()
    return render_template('upload.html', labels=labels)

@app.route('/pics/<filename>')
def return_pic(filename):
    return send_from_directory(app.config['UPLOAD_DIR'], secure_filename(filename))

@app.route("/edit_idea/<idea_id>", methods=["GET", "POST"])
@login_required
def edit_idea(idea_id):
    idea = Idea.query.get_or_404(idea_id)
    if idea.user_id != current_user.id:
        abort(403)

    form = IdeaForm()
    if request.method == "GET":
        form.is_private.data = idea.is_private
        form.idea_name.data = idea.idea_name
        form.idea_description = idea.idea_description

    if form.validate_on_submit():
        idea.is_private = form.is_private.data
        idea.name = form.idea_name.data
        idea.description = form.idea_description.data
        db.session.commit()
        flash("Updated successfully!", "success")

    return render_template("edit_idea.html", form=form)


@app.route("/ideas/<user_email>/<privacy_filter>", methods=["GET", "POST"])
@app.route("/ideas/<user_email>", defaults={'privacy_filter': 'public'}, methods=["GET", "POST"])
def ideas(user_email, privacy_filter):
    user = User.query.filter_by(email=user_email).first_or_404()
    if privacy_filter == 'private' and user != current_user:
        abort(403)
    elif privacy_filter == 'private':
        is_private = True
    elif privacy_filter == 'public':
        is_private = False
    else:
        abort(404)

    if user == current_user:
        form = IdeaForm()
    else:
        form = None

    if form and form.validate_on_submit():
        idea = Idea(form.idea_name.data, user)
        description = Idea(form.idea_description.data, user)
        idea.is_private = form.is_private.data
        form.idea_name.data = ""
        form.idea_description.data = ""
        db.session.add(idea)
        db.session.commit()
        flash("Idea was added successfully", "success")

    list_of_ideas = user.ideas.filter_by(is_private=is_private)
    return render_template("ideas.html", form=form, list_of_ideas=list_of_ideas, user_email=user_email, is_private=is_private)

if __name__ == "__main__":
    app.run(debug=True)
