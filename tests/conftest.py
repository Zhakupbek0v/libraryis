import os
import sys
import tempfile
from pathlib import Path

_tmp = tempfile.mkdtemp()
os.environ["LIBRARYIS_DB"] = "sqlite:///" + str(Path(_tmp) / "test.db").replace("\\", "/")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from app.models import Base, Session, engine  # noqa: E402
from app import services as sv  # noqa: E402
from app.models import AppUser  # noqa: E402


@pytest.fixture()
def s():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with Session() as session:
        session.add(AppUser(login="lib", password_hash=sv.hash_password("secret1"), full_name="Тест Библиотекарь", role="librarian"))
        session.commit()
        yield session
