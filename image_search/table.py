from sqlalchemy import Column, Integer, String, Text

from mephisto.library.util.orm.base import Base


class ImageSearchResultTable(Base):
    __tablename__ = "image_search_result"

    id = Column(Integer(), primary_key=True)
    message_id = Column(String(length=64))

    index = Column(Integer())
    url = Column(Text())
    text = Column(Text())
    thumbnail = Column(Text())
    similarity = Column(Integer())
    engine = Column(Text())
