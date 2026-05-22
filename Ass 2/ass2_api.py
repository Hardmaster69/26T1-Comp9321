#!/usr/bin/env python
# coding: utf-8

# In[1]:


import io
import os
import json
import pandas as pd
from flask import Flask, request, send_file
from flask_restx import Api, Resource, fields, Namespace, abort
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity, get_jwt
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.datastructures import FileStorage
from rapidfuzz import fuzz, process
from zoneinfo import ZoneInfo
from datetime import datetime
from flask_jwt_extended import verify_jwt_in_request
import matplotlib.pyplot as plt

app = Flask(__name__)

# db setting
BASE_DIR = os.path.abspath(os.path.dirname(__name__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(BASE_DIR, 'z5617485.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# JWT
app.config['JWT_SECRET_KEY'] = 'comp9321-super-secret-key'  
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = False 

db = SQLAlchemy(app)
jwt = JWTManager(app)

# JWT token input
authorizations = {
    'Bearer Auth': {
        'type': 'apiKey',
        'in': 'header',
        'name': 'Authorization',
        'description': "input: Bearer <Your Token>"
    }
}

api = Api(app, 
          version='1.0.0', 
          title='COMP9321 Movie API',
          description='Assignment 2 - Movie Management API',
          authorizations=authorizations,
          security='Bearer Auth')

ns_users = api.namespace('users', description='User Management and Access Control')
ns_movies = api.namespace('movies', description='Movies and Credits Management')
upload_parser = ns_movies.parser()
upload_parser.add_argument('movies_file', location='files', type=FileStorage, required=True, help='upload movies.csv')
upload_parser.add_argument('credits_file', location='files', type=FileStorage, required=True, help='upload credits.csv')


# In[2]:


class User(db.Model):
    __tablename__ = 'users'

    # set username as main key
    username = db.Column(db.String(50), primary_key=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False) # admin or user
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    collections = db.relationship('Collection', backref='user', lazy='dynamic', cascade="all, delete-orphan")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)



# In[3]:


def init_db():
    # init db and create account
    with app.app_context():
        db.create_all() 

        # check if admin exists
        if not User.query.filter_by(username='admin').first():
            admin_user = User(username='admin', role='Admin', is_active=True)
            admin_user.set_password('admin')
            db.session.add(admin_user)

        # check if user exists
        if not User.query.filter_by(username='user').first():
            normal_user = User(username='user', role='User', is_active=True)
            normal_user.set_password('user')
            db.session.add(normal_user)

        db.session.commit()


# In[4]:


# user and account model

login_model = api.model('Login', {
    'username': fields.String(required=True),
    'password': fields.String(required=True)
})

user_response_model = api.model('UserResponse', {
    'username': fields.String(),
    'role': fields.String(),
    'is_active': fields.Boolean()
})

user_create_model = api.model('UserCreate', {
    'username': fields.String(required=True, description='Username of new user'),
    'password': fields.String(required=True, description='Password of new user')
})

user_status_model = api.model('UserStatus', {
    'is_active': fields.Boolean(required=True, description='True-active, False-inactive')
})

# login
@ns_users.route('/login')
class UserLogin(Resource):
    @api.doc(security=None) # no token
    @api.expect(login_model)
    def post(self):
        data = api.payload
        user = User.query.filter_by(username=data.get('username')).first()

        if not user or not user.check_password(data.get('password')):
            abort(401, "Wrong username or password")

        if not user.is_active:
            abort(403, "Invalid account")

        # create token
        access_token = create_access_token(
            identity=user.username, 
            additional_claims={"role": user.role}
        )
        return {"access_token": access_token}, 200

# account management
@ns_users.route('/')
class UserList(Resource):

    # get
    @api.doc(description='Get all account')
    @api.marshal_list_with(user_response_model)
    @jwt_required()
    def get(self):
        claims = get_jwt()
        if claims.get("role") != 'Admin':
            abort(403, "Admin only")

        users = User.query.all()
        return users 

    # post
    @api.doc(description='Create new user account')
    @api.expect(user_create_model, validate=True)
    @api.response(201, 'Add user success')
    @api.response(400, 'Username exists')
    @api.response(403, 'Admin only')
    @jwt_required()
    def post(self):
        # create new account
        claims = get_jwt()
        if claims.get("role") != 'Admin':
            abort(403, "Admin only")

        data = api.payload
        username = data.get('username')
        password = data.get('password')

        # check if username exist
        if User.query.filter_by(username=username).first():
            abort(400, "Username exist")

        new_user = User(username=username, role='User', is_active=True)
        new_user.set_password(password)

        db.session.add(new_user)
        db.session.commit()

        return {"message": f"Create account {username} success"}, 201

@ns_users.route('/<string:username>')
@api.doc(params={'username': 'Target account username'})
class UserResource(Resource):

    @api.doc(description='Delete account')
    @api.response(200, 'Delete success')
    @api.response(403, 'Admin only')
    @api.response(404, 'Account not exist')
    @jwt_required()
    def delete(self, username):
        claims = get_jwt()
        if claims.get("role") != 'Admin':
            abort(403, "Admin only")

        if username == 'admin':
            abort(403, "Admin can not be deleted")

        user = User.query.filter_by(username=username).first()
        if not user:
            abort(404, "Account do not exist")

        db.session.delete(user)
        db.session.commit()

        return {"message": f"Account {username} delete"}, 200


@ns_users.route('/<string:username>/status')
@api.doc(params={'username': 'Target account username'})
class UserStatusResource(Resource):

    @api.doc(description='Active account')
    @api.expect(user_status_model, validate=True)
    @api.response(200, 'Update sueccess')
    @api.response(403, 'Admin only')
    @api.response(404, 'Account do not exist')
    @jwt_required()
    def patch(self, username):
        claims = get_jwt()
        if claims.get("role") != 'Admin':
            abort(403, "Admin only")

        if username == 'admin':
            abort(403, "Admin status can not be changed")

        user = User.query.filter_by(username=username).first()
        if not user:
            abort(404, "Account do not exist")

        data = api.payload
        user.is_active = data.get('is_active')
        db.session.commit()

        status_str = "Active" if user.is_active else "Inactive"
        return {"message": f"User {username} has been {status_str}"}, 200


# In[5]:


# movie data model

# movie and cast
movie_cast = db.Table('movie_cast',
    db.Column('movie_id', db.Integer, db.ForeignKey('movies.id', ondelete='CASCADE'), primary_key=True),
    db.Column('cast_id', db.Integer, db.ForeignKey('cast_members.id', ondelete='CASCADE'), primary_key=True),
    db.Column('character', db.String(255))
)

# movie and crew
movie_crew = db.Table('movie_crew',
    db.Column('movie_id', db.Integer, db.ForeignKey('movies.id', ondelete='CASCADE'), primary_key=True),
    db.Column('crew_id', db.Integer, db.ForeignKey('crew_members.id', ondelete='CASCADE'), primary_key=True),
    db.Column('job', db.String(255)),
    db.Column('department', db.String(255))
)

class Movie(db.Model):
    __tablename__ = 'movies'
    id = db.Column(db.Integer, primary_key=True) 
    title = db.Column(db.String(255), nullable=False)
    release_date = db.Column(db.String(50))
    overview = db.Column(db.Text)
    genres = db.Column(db.Text) #

    casts = db.relationship('CastMember', secondary=movie_cast, backref=db.backref('movies', lazy='dynamic'))
    crews = db.relationship('CrewMember', secondary=movie_crew, backref=db.backref('movies', lazy='dynamic'))

class CastMember(db.Model):
    __tablename__ = 'cast_members'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)

class CrewMember(db.Model):
    __tablename__ = 'crew_members'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)

# movie data
@ns_movies.route('/import')
class MovieImport(Resource):

    @api.doc(description='upload movie data(Admin only)')
    @api.expect(upload_parser)
    @api.response(201, 'Success')
    @api.response(400, 'Data broken')
    @api.response(403, 'Admin only')
    @jwt_required()
    def post(self):
        # check admin
        claims = get_jwt()
        if claims.get("role") != 'Admin':
            abort(403, "Admin only")

        # get data
        args = upload_parser.parse_args()
        movies_file = args['movies_file']
        credits_file = args['credits_file']

        # check data
        if not movies_file.filename.endswith('.csv') or not credits_file.filename.endswith('.csv'):
            abort(400, "Wrong file type")
        try:
            # read csv
            df_movies = pd.read_csv(movies_file)
            df_credits = pd.read_csv(credits_file)

            # 2. get deta
            df_movies_clean = df_movies[['id', 'title', 'release_date', 'overview', 'genres']].copy()

            # split cast and crew
            cast_records, crew_records = [], []
            movie_cast_records, movie_crew_records = [], []

            for _, row in df_credits.iterrows():
                m_id = row['movie_id']

                # read cast
                if pd.notna(row['cast']):
                    casts = json.loads(row['cast'])
                    for c in casts:
                        cast_records.append({'id': c['id'], 'name': c['name']})
                        movie_cast_records.append({'movie_id': m_id, 'cast_id': c['id'], 'character': c['character']})

                # read crew
                if pd.notna(row['crew']):
                    crews = json.loads(row['crew'])
                    for c in crews:
                        crew_records.append({'id': c['id'], 'name': c['name']})
                        movie_crew_records.append({'movie_id': m_id, 'crew_id': c['id'], 'job': c['job'], 'department': c['department']})

            # delete duplicate
            df_cast = pd.DataFrame(cast_records).drop_duplicates(subset=['id'])
            df_crew = pd.DataFrame(crew_records).drop_duplicates(subset=['id'])
            df_mc = pd.DataFrame(movie_cast_records).drop_duplicates(subset=['movie_id', 'cast_id'])
            df_mcr = pd.DataFrame(movie_crew_records).drop_duplicates(subset=['movie_id', 'crew_id'])

            # clean old data
            db.session.query(movie_cast).delete()
            db.session.query(movie_crew).delete()
            Movie.query.delete()
            CastMember.query.delete()
            CrewMember.query.delete()
            db.session.commit()

            # upload
            with db.engine.begin() as conn:
                df_movies_clean.to_sql('movies', con=conn, if_exists='append', index=False)
                df_cast.to_sql('cast_members', con=conn, if_exists='append', index=False)
                df_crew.to_sql('crew_members', con=conn, if_exists='append', index=False)
                df_mc.to_sql('movie_cast', con=conn, if_exists='append', index=False)
                df_mcr.to_sql('movie_crew', con=conn, if_exists='append', index=False)

            return {"message": f"Upload {len(df_movies_clean)} success！"}, 201

        except Exception as e:
            abort(400, f"Error: {str(e)}")



# In[6]:


# Search movie by id
movie_details_model = api.model('MovieDetails', {
    'id': fields.Integer(description='movie id'),
    'title': fields.String(description='movie title'),
    'release_date': fields.String(description='release date'),
    'overview': fields.String(description='overview'),
    'genres': fields.String(description='genres (JSON)')
})

person_details_model = api.model('PersonDetails', {
    'id': fields.Integer(description='staff ID'),
    'name': fields.String(description='staff name'),
    # staff in movie
    'movies': fields.List(fields.Nested(movie_details_model), description='movie list')
})

@ns_movies.route('/<int:id>')
@api.doc(params={'id': 'Movie id'})
class MovieResource(Resource):
    @api.doc(description='Search by movie id (all user)')
    @api.marshal_with(movie_details_model)
    @jwt_required()
    def get(self, id):
        movie = Movie.query.get_or_404(id, description="Movie not found")
        return movie

@ns_movies.route('/cast/<int:id>')
@api.doc(params={'id': 'Cast id'})
class CastResource(Resource):
    @api.doc(description='Search by cast id (all user)')
    @api.marshal_with(person_details_model)
    @jwt_required()
    def get(self, id):
        cast_member = CastMember.query.get_or_404(id, description="Cast not found")
        # return cast's movie list 
        return {
            'id': cast_member.id,
            'name': cast_member.name,
            'movies': list(cast_member.movies)
        }

@ns_movies.route('/crew/<int:id>')
@api.doc(params={'id': 'Crew id'})
class CrewResource(Resource):
    @api.doc(description='Search by crew id (all user)')
    @api.marshal_with(person_details_model)
    @jwt_required()
    def get(self, id):
        crew_member = CrewMember.query.get_or_404(id, description="Crew not found")
        return {
            'id': crew_member.id,
            'name': crew_member.name,
            'movies': list(crew_member.movies)
        }



# In[7]:


# fuzzy search
@ns_movies.route('/search')
class MovieSearch(Resource):

    @api.doc(description='fuzzy search with rapidfuzz')
    @api.doc(params={'q': 'Search by movie name, cast name or crew name'})
    @api.marshal_list_with(movie_details_model) # return movie list
    @jwt_required()
    def get(self):
        query_str = request.args.get('q', '').strip()
        if not query_str:
            return []

        SCORE_THRESHOLD = 70 

        movie_scores = {} # for sorting

        # search by movie name
        all_movies = Movie.query.with_entities(Movie.id, Movie.title).all()
        movie_dict = {m.id: m.title for m in all_movies}

        movie_matches = process.extract(
            query_str, movie_dict, limit=None, score_cutoff=SCORE_THRESHOLD, scorer=fuzz.WRatio
        )
        for _, score, m_id in movie_matches:
            movie_scores[m_id] = max(movie_scores.get(m_id, 0), score)

        # search by cast name
        all_casts = CastMember.query.with_entities(CastMember.id, CastMember.name).all()
        cast_dict = {c.id: c.name for c in all_casts}

        cast_matches = process.extract(
            query_str, cast_dict, limit=None, score_cutoff=SCORE_THRESHOLD, scorer=fuzz.WRatio
        )
        if cast_matches:
            matched_cast_ids = [m[2] for m in cast_matches]
            # set score for this cast
            cast_score_map = {m[2]: m[1] for m in cast_matches} 

            # get movie id from cast_movie table
            cast_movies = db.session.query(movie_cast.c.movie_id, movie_cast.c.cast_id).filter(
                movie_cast.c.cast_id.in_(matched_cast_ids)
            ).all()

            for m_id, c_id in cast_movies:
                # set socre to movie
                movie_scores[m_id] = max(movie_scores.get(m_id, 0), cast_score_map[c_id])

        # search by crew
        all_crews = CrewMember.query.with_entities(CrewMember.id, CrewMember.name).all()
        crew_dict = {c.id: c.name for c in all_crews}

        crew_matches = process.extract(
            query_str, crew_dict, limit=None, score_cutoff=SCORE_THRESHOLD, scorer=fuzz.WRatio
        )
        if crew_matches:
            matched_crew_ids = [m[2] for m in crew_matches]
            crew_score_map = {m[2]: m[1] for m in crew_matches}

            crew_movies = db.session.query(movie_crew.c.movie_id, movie_crew.c.crew_id).filter(
                movie_crew.c.crew_id.in_(matched_crew_ids)
            ).all()

            for m_id, c_id in crew_movies:
                movie_scores[m_id] = max(movie_scores.get(m_id, 0), crew_score_map[c_id])

        # build movie list and sort
        if not movie_scores:
            return []

        # build list
        final_movies = Movie.query.filter(Movie.id.in_(movie_scores.keys())).all()

        # sort by score
        final_movies.sort(key=lambda m: movie_scores[m.id], reverse=True)

        return final_movies



# In[8]:


# personal movie collection
collection_movie = db.Table('collection_movie',
    db.Column('collection_id', db.Integer, db.ForeignKey('collections.id', ondelete='CASCADE'), primary_key=True),
    db.Column('movie_id', db.Integer, db.ForeignKey('movies.id', ondelete='CASCADE'), primary_key=True)
)

class Collection(db.Model):
    __tablename__ = 'collections'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)

    # key to user table
    user_username = db.Column(db.String(80), db.ForeignKey('users.username', ondelete='CASCADE'), nullable=False)

    # combine with movie table
    movies = db.relationship('Movie', secondary=collection_movie, backref=db.backref('collections', lazy='dynamic'))

# 
ns_collections = api.namespace('collections', description='Private Movie Collections')

# create collection model
collection_create_model = api.model('CollectionCreate', {
    'name': fields.String(required=True, description='Collection name'),
    'description': fields.String(description='description')
})

# output coll-list model
collection_response_model = api.model('CollectionResponse', {
    'id': fields.Integer(),
    'name': fields.String(),
    'description': fields.String(),
    'movies': fields.List(fields.Nested(movie_details_model)) # show list
})

@ns_collections.route('/')
class CollectionList(Resource):

    @api.doc(description='Get user all playlist')
    @api.marshal_list_with(collection_response_model)
    @jwt_required()
    def get(self):
        current_username = get_jwt_identity()
        user = User.query.filter_by(username=current_username).first()

        # retern list
        return list(user.collections)

    @api.doc(description='Create new playlist')
    @api.expect(collection_create_model, validate=True)
    @api.response(201, 'Success')
    @jwt_required()
    def post(self):
        current_username = get_jwt_identity()
        user = User.query.filter_by(username=current_username).first()

        data = api.payload
        new_collection = Collection(
            name=data.get('name'),
            description=data.get('description', ''),
            user_username=user.username
        )

        db.session.add(new_collection)
        db.session.commit()

        return {"message": f"Create playlist '{new_collection.name}' success", "id": new_collection.id}, 201



@ns_collections.route('/<int:collection_id>/movies/<int:movie_id>')
@api.doc(params={'collection_id': 'playlist ID', 'movie_id': 'movie ID'})
class CollectionMovie(Resource):

    # add to list
    @api.doc(description='Add into playlist')
    @api.response(201, 'Success')
    @api.response(400, 'already exist')
    @api.response(403, 'Admin only')
    @api.response(404, 'List or movie dose not exist')
    @jwt_required()
    def post(self, collection_id, movie_id):
        current_username = get_jwt_identity()
        user = User.query.filter_by(username=current_username).first()

        # get list
        collection = Collection.query.get_or_404(collection_id, description="List not found")
        if collection.user_username != user.username:
            abort(403, "Forbidden")

        # search movie
        movie = Movie.query.get_or_404(movie_id, description="Movie not found")

        # add to list
        if movie in collection.movies:
            abort(400, "Movie already exist")

        collection.movies.append(movie)
        db.session.commit()

        return {"message": f"Add {movie.title} into '{collection.name}' success"}, 201

    # remove from list
    @api.doc(description='Remove from list')
    @api.response(200, 'Success')
    @api.response(403, 'Forbidden')
    @jwt_required()
    def delete(self, collection_id, movie_id):
        current_username = get_jwt_identity()
        user = User.query.filter_by(username=current_username).first()

        collection = Collection.query.get_or_404(collection_id)
        if collection.user_username != user.username:
            abort(403, "Forbidden")

        movie = Movie.query.get_or_404(movie_id)

        if movie in collection.movies:
            collection.movies.remove(movie)
            db.session.commit()
            return {"message": f"Remove《{movie.title}》from '{collection.name}' Success"}, 200
        else:
            abort(400, "Movie dose not exist in list")


# In[9]:


# data log
class APILog(db.Model):
    __tablename__ = 'api_logs'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), default='Anonymous') 
    endpoint = db.Column(db.String(255), nullable=False)     
    method = db.Column(db.String(10), nullable=False)        
    timestamp = db.Column(db.String(50), nullable=False)     # sydney time

@app.after_request
def log_api_action(response):
    # user and admin request only
    if request.path.startswith('/swagger') or request.path == '/' or request.method == 'OPTIONS':
        return response

    username = 'Anonymous'
    try:
        verify_jwt_in_request(optional=True)
        identity = get_jwt_identity()
        if identity:
            username = identity
    except Exception:
        pass 

    sydney_tz = ZoneInfo('Australia/Sydney')
    sydney_time = datetime.now(sydney_tz).strftime('%Y-%m-%d %H:%M:%S')

    route_endpoint = str(request.url_rule) if request.url_rule else request.path

    # write log
    log_entry = APILog(
        username=username,
        endpoint=route_endpoint, 
        method=request.method,
        timestamp=sydney_time
    )

    db.session.add(log_entry)
    db.session.commit()

    return response

# datalog chart
ns_stats = api.namespace('statistics', description='API Usage Statistics')

@ns_stats.route('/')
class APIStatistics(Resource):

    @api.doc(description='Get data')
    @api.doc(params={
        'format': 'Return .csv or .png',
        'target_user': 'Target user (Admin only)'
    })
    @jwt_required()
    def get(self):
        current_username = get_jwt_identity()
        user = User.query.filter_by(username=current_username).first()

        fmt = request.args.get('format', 'png').lower()
        target_user = request.args.get('target_user')

        # check token
        query = APILog.query

        if user.role == 'Admin':
            if target_user:
                # admin get user
                query = query.filter_by(username=target_user)
            else:
                # admin get all
                query = query.filter(APILog.username != 'admin')
        else:
            # user get user
            target_user = None 
            query = query.filter_by(username=user.username)

        logs = query.all()

        if not logs:
            abort(404, "No datalog fond")

        # change to dataframe
        df = pd.DataFrame([{
            'username': log.username,
            'endpoint': log.endpoint,
            'method': log.method,
            'timestamp': log.timestamp
        } for log in logs])

        # get date
        df['date'] = df['timestamp'].str.slice(0, 10)

        # output csv
        if fmt == 'csv':
            stats_df = df.groupby(['date', 'endpoint']).size().reset_index(name='request_count')

            # dataframe to csv
            output = io.StringIO()
            stats_df.to_csv(output, index=False)
            output.seek(0)

            return send_file(
                io.BytesIO(output.getvalue().encode('utf-8')),
                mimetype='text/csv',
                as_attachment=True,
                download_name=f'api_stats_{current_username}.csv'
            )

        # output png
        elif fmt == 'png':
            # 2 graph
            daily_counts = df.groupby('date').size()
            endpoint_counts = df['endpoint'].value_counts().head(10)

            fig, axes = plt.subplots(nrows=2, ncols=1, figsize=(10, 12))

            # title
            user_label = "All Users (Excluding Admin)" if not target_user and user.role == 'Admin' else f"User: {target_user or user.username}"
            fig.suptitle(f"API Usage Dashboard\n[{user_label}]", fontsize=16, fontweight='bold')

            # daily api usage
            daily_counts.plot(kind='bar', ax=axes[0], color='#4CAF50', edgecolor='black')
            axes[0].set_title("1. Daily API Usage Trends", fontsize=13, pad=10)
            axes[0].set_xlabel("Date (Sydney Time)", fontsize=11)
            axes[0].set_ylabel("Number of Requests", fontsize=11)
            axes[0].tick_params(axis='x', rotation=0) 
            axes[0].grid(axis='y', linestyle='--', alpha=0.7)

            # top 10 usge api
            endpoint_counts.sort_values().plot(kind='barh', ax=axes[1], color='#3498db', edgecolor='black')
            axes[1].set_title("2. Top 10 API Endpoints Activity", fontsize=13, pad=10)
            axes[1].set_xlabel("Number of Requests", fontsize=11)
            axes[1].set_ylabel("API Endpoint", fontsize=11)
            axes[1].grid(axis='x', linestyle='--', alpha=0.7)

            plt.tight_layout()
            plt.subplots_adjust(top=0.92)

            img_io = io.BytesIO()
            plt.savefig(img_io, format='png', dpi=120) 
            img_io.seek(0)
            plt.close() 

            return send_file(img_io, mimetype='image/png')

        else:
            abort(400, "Please choose 'csv' or 'png'")


# In[10]:


if __name__ == '__main__':
    init_db()
    app.run(debug=True, use_reloader=False)


# In[ ]:




