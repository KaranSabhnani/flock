import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from werkzeug.datastructures import ImmutableMultiDict

import flask_login

from flock.model import Base


class User(Base, flask_login.UserMixin):
    __tablename__ = 'user'
    __table_args__ = (
        sa.UniqueConstraint('first_name', 'last_name'),
    )

    id = sa.Column(sa.Integer, primary_key=True)

    first_name = sa.Column(sa.String(50), nullable=False)
    last_name = sa.Column(sa.String(50), nullable=False)

    def is_active(self):
        return True


class Topic(Base):
    __tablename__ ='topic'

    id = sa.Column(sa.Integer, primary_key=True)

    title = sa.Column(sa.String(500), nullable=False)
    description = sa.Column(sa.String(1000), nullable=True)
    narrative = sa.Column(sa.String(1000), nullable=True)

    user_id = sa.Column(sa.Integer, sa.ForeignKey('user.id'), nullable=False)
    user = sa.orm.relationship('User', backref='topics')

    def judgment_count(self, value):
        return len([j for j in self.judgments if j.judgment == value])


class TopicQuery(Base):
    __tablename__ = 'topic_query'
    __table_args__ = (
        sa.UniqueConstraint('query', 'filter', 'filter_args', 'cluster', 'topic_id'),
    )

    id = sa.Column(sa.Integer, primary_key=True)

    query = sa.Column(sa.String)
    filter = sa.Column(sa.String)
    filter_args = sa.Column(pg.JSONB)
    cluster = sa.Column(sa.String)

    topic_id = sa.Column(sa.Integer, sa.ForeignKey('topic.id'), nullable=False)
    topic = sa.orm.relationship('Topic', backref='queries')

    @property
    def filter_args_dict(self):
        return dict(self.filter_args) if self.filter_args is not None else {}


class RelevanceJudgment(Base):
    __tablename__ = 'relevance_judgment'

    topic_id = sa.Column(sa.Integer, sa.ForeignKey('topic.id'), nullable=False, primary_key=True)
    topic = sa.orm.relationship('Topic', backref='judgments')

    tweet_id = sa.Column(
        sa.BigInteger,
        # sa.ForeignKey('tweet.tweet_id'),
        nullable=False,
        primary_key=True,
    )

    judgment = sa.Column(sa.Integer, nullable=False)