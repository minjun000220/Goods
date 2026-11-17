import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from storage.models import Base
from storage.repository import Repository


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    yield s
    s.close()


@pytest.fixture
def repo(session):
    return Repository(session)
