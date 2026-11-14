"""Extension objects, created unbound and initialised in `create_app()`."""
from flask_bootstrap import Bootstrap5
from flask_caching import Cache
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)
migrate = Migrate()
login_manager = LoginManager()
csrf = CSRFProtect()
cache = Cache()
limiter = Limiter(key_func=get_remote_address)
bootstrap = Bootstrap5()
