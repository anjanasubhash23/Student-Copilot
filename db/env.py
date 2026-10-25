from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

from core.config import get_settings

if context.config.config_file_name:
    fileConfig(context.config.config_file_name)

url = get_settings().database_url

if context.is_offline_mode():
    context.configure(url=url, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    with create_engine(url).connect() as connection:
        context.configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()
