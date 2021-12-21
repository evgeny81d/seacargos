import os

from flask import Flask
#from werkzeug.utils import import_string


def create_app(test_config=None):
    # create and configure the app
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY='dev',
        DATABASE=os.path.join(app.instance_path, 'flaskr.sqlite'),
    )

    if test_config is None:
        # load the instance config, if it exists, when not testing
        #cfg = import_string('config.ProductionConfig')()
        #app.config.from_object(cfg)
        app.config.from_pyfile('config.py', silent=True)
    else:
        # load the test config if passed in
        app.config.from_mapping(test_config)

    # ensure the instance folder exists
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    # Run registration for close_conn() function
    from . import db
    db.init_app(app)

    # Register home page blueprint
    from . import home
    app.register_blueprint(home.bp)
    app.add_url_rule('/', endpoint='index')

    
    return app