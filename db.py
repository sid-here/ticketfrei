from bottle import redirect, request, response
from functools import wraps
from inspect import Signature
import jwt
from os import path, urandom
from pylibscrypt import scrypt_mcf, scrypt_mcf_check
import sqlite3


class DB(object):
    def __init__(self):
        dbfile = path.join(path.dirname(path.abspath(__file__)),
                           'ticketfrei.sqlite')
        dbfile = ':memory:'
        self.conn = sqlite3.connect(dbfile)
        self.cur = self.conn.cursor()
        self.secret = urandom(32)
        self.create()

    def create(self):
        # init db
        self.cur.executescript('''
            CREATE TABLE "user" (
                `id`          INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT UNIQUE,
                `email`       TEXT,
                `passhash`    TEXT,
                `enabled`     INTEGER DEFAULT 1
            );
            CREATE TABLE "twitter_request_tokens" (
                `id`	INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT UNIQUE,
                `user_id`	INTEGER,
                `request_token`	TEXT,
                FOREIGN KEY(`user_id`) REFERENCES `user` ( `id` )
            );
            CREATE TABLE "twitter_accounts" (
                `id`	INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT UNIQUE,
                `user_id`	INTEGER,
                `client_id`	TEXT,
                `client_secret`	TEXT,
                FOREIGN KEY(`user_id`) REFERENCES `user` ( `id` )
            );
            CREATE TABLE "trigger_good" (
                `id`	INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT UNIQUE,
                `user_id`	INTEGER,
                `words`	TEXT,
                FOREIGN KEY(`user_id`) REFERENCES `user` ( `id` )
            );
            CREATE TABLE "trigger_bad" (
                `id`	INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT UNIQUE,
                `user_id`	INTEGER,
                `words`	TEXT,
                FOREIGN KEY(`user_id`) REFERENCES `user` ( `id` )
            );
            CREATE TABLE "mastodon_instances" (
                `id`	INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT UNIQUE,
                `instance`	TEXT,
                `client_id`	TEXT,
                `client_secret`  TEXT
            );
            CREATE TABLE "mastodon_accounts" (
                `id`	INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT UNIQUE,
                `user_id`	INTEGER,
                `access_token`	TEXT,
                `instance_id`	TEXT,
                `active`     INTEGER,
                FOREIGN KEY(`user_id`) REFERENCES `user` ( `id` ),
                FOREIGN KEY(`instance_id`) REFERENCES `mastodon_instances` ( `id` )
            );
            CREATE TABLE "seen_toots" (
                `id`	INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT UNIQUE,
                `user_id`	INTEGER,
                `mastodon_accounts_id`	INTEGER,
                `toot_id`	TEXT,
                FOREIGN KEY(`user_id`) REFERENCES `user` ( `id` ),
                FOREIGN KEY(`mastodon_accounts_id`) REFERENCES `mastodon_accounts` ( `id` )
            );
            CREATE TABLE "mail" (
                `id`	INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT UNIQUE,
                `user_id`	INTEGER,
                `email`	TEXT,
                `active` INTEGER,
                FOREIGN KEY(`user_id`) REFERENCES `user` ( `id` )
            );
            CREATE TABLE "seen_tweets" (
                `id`	INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT UNIQUE,
                `user_id`	INTEGER,
                `twitter_accounts_id`	INTEGER,
                `tweet_id` TEXT,
                FOREIGN KEY(`user_id`) REFERENCES `user` ( `id` )
                FOREIGN KEY(`twitter_accounts_id`) REFERENCES `twitter_accounts` ( `id` )
            );
        ''')

    def token(self, email, password):
        return jwt.encode({
            'email': email,
            'passhash': scrypt_mcf(password.encode('utf-8')).decode('ascii')
            }, self.secret).decode('ascii')

    def register(self, token):
        json = jwt.decode(token, self.secret)
        # create user
        self.cur.execute("INSERT INTO user (email, passhash) VALUES(?, ?);",
                         (json['email'], json['passhash']))
        return User(self, self.cur.lastrowid)

    def authenticate(self, email, password):
        # check email/password
        self.cur.execute("SELECT id, passhash FROM user WHERE email=?;",
                         (email, ))
        row = self.cur.fetchone()
        if not row:
            return None
        if not scrypt_mcf_check(row[1].encode('ascii'),
                                password.encode('utf-8')):
            return None
        return User(self, row[0])

    def by_email(self, email):
        self.cur.execute("SELECT id FROM user WHERE email=?;", (email, ))
        row = self.cur.fetchone()
        if not row:
            return None
        return User(self, row[0])

    def close(self):
        self.conn.close()


class User(object):
    def __init__(self, db, uid):
        # set cookie
        response.set_cookie('uid', uid, secret=db.secret, path='/')
        self.db = db
        self.uid = uid

    def state(self):
        return dict(foo='bar')


class DBPlugin(object):
    name = 'DBPlugin'
    api = 2

    def __init__(self, loginpage):
        self.db = DB()
        self.loginpage = loginpage

    def close(self):
        self.db.close()

    def apply(self, callback, route):
        uservar = route.config.get('user', None)
        dbvar = route.config.get('db', None)
        signature = Signature.from_callable(route.callback)

        @wraps(callback)
        def wrapper(*args, **kwargs):
            if uservar and uservar in signature.parameters:
                uid = request.get_cookie('uid', secret=self.db.secret)
                if uid is None:
                    return redirect(self.loginpage)
                kwargs[uservar] = User(self.db, uid)
            if dbvar and dbvar in signature.parameters:
                kwargs[dbvar] = self.db
            return callback(*args, **kwargs)

        return wrapper