import logging
import json

import click
import click_log

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from flock.__main__ import create_session
from flock.model import metadata

from flock_web.app import create_app
import flock_web.model as fw_model


logger = logging.getLogger(__name__)
click_log.basic_config(logger)

@click.group()
@click_log.simple_verbosity_option(logger=logger)
def cli():
    pass


@cli.command()
@click.argument('filename')
def runserver(filename):
    app = create_app(filename)
    app.run()


@cli.command()
@click.option('--session', default='postgresql:///twitter', callback=create_session)
def initdb(session):
    metadata.create_all(
        tables=[
            o.__table__ for o in [
                fw_model.User, fw_model.Topic, fw_model.TopicQuery, fw_model.RelevanceJudgment, fw_model.TaskResult, fw_model.UserAction,
                fw_model.TopicQuestionnaire, fw_model.EvalTopic, fw_model.EvalRelevanceJudgment, fw_model.EvalCluster,
                fw_model.EvalClusterAssignment,
            ]
        ]
    )


@cli.command()
@click.option('--session', default='postgresql:///twitter', callback=create_session)
@click.option('--assr_topic_file', type=click.File())
@click.option('--collection')
def insert_eval_topics(session, assr_topic_file, collection):

    stmt = postgresql.insert(fw_model.EvalTopic.__table__)
    stmt = stmt.on_conflict_do_update(
        constraint=fw_model.EvalTopic.__table__.primary_key,
        set_={'user_id': stmt.excluded.user_id}
    )

    for line in assr_topic_file:
        rts_topic_id, assessor_user_name = line.split()

        try:
            int(rts_topic_id)
        except ValueError:
            pass
        else:
            rts_topic_id = f'RTS{rts_topic_id}'

        assessor = session.query(fw_model.User).filter_by(first_name=assessor_user_name).one_or_none()

        if assessor is None:
            assessor = fw_model.User(first_name=assessor_user_name, last_name='hi')
            session.add(assessor)

            session.flush()
            logger.warning('A new user %s is created.', assessor_user_name)

        session.execute(
            stmt.values(
                rts_id=rts_topic_id,
                collection=collection,
                title=rts_topic_id,
                user_id=assessor.id,
            )
        )

    session.commit()


@cli.command()
@click.option('--session', default='postgresql:///twitter', callback=create_session)
@click.option('--topic_file', type=click.File())
@click.option('--collection')
def insert_eval_topics_json(session, topic_file, collection):
    table = fw_model.EvalTopic.__table__
    stmt = sa.update(table)

    topics = json.load(topic_file)
    for topic in topics:
        session.execute(
            stmt
            .where(
                sa.and_(
                    table.c.rts_id == topic['topid'],
                    table.c.collection == collection,
                ),
            )
            .values(
                title=topic['title'],
                description=topic['description'],
                narrative=topic['narrative'],
            )
        )

    session.commit()


@cli.command()
@click.option('--session', default='postgresql:///twitter', callback=create_session)
@click.option('--collection')
@click.option('--qrels_file', type=click.File())
@click.option('--set_position/--no-set_position', default=False)
@click.option('--set_judgments/--no-set_order', default=False)
def insert_eval_relevance_judgements(session, collection, qrels_file, set_position, set_judgments):
    stmt = postgresql.insert(fw_model.EvalRelevanceJudgment.__table__)

    if not (set_position or set_judgments):
        stmt = stmt.on_conflict_do_nothing()
    else:
        set_ = {}
        if set_position:
            set_['position'] = stmt.excluded.position
        if set_judgments:
            set_['judgment'] = stmt.excluded.judgment
            set_['missing'] = stmt.excluded.missing

        stmt = stmt.on_conflict_do_update(
            constraint=fw_model.EvalRelevanceJudgment.__table__.primary_key,
            set_=set_,
        )

    for line_no, line in enumerate(qrels_file):
        full_format = True
        values = line.split()
        try:
            eval_topic_rts_id, _, _, _,tweet_id, _, _, judgment, _ = values
        except ValueError:
            if len(values) == 3:
                eval_topic_rts_id, _, tweet_id = values
                judgment = None
            else:
                eval_topic_rts_id, _, tweet_id, judgment = values
            full_format = False

        tweet_id = int(tweet_id)
        judgment = int(judgment) if judgment is not None and not full_format else None

        missing = judgment == -2
        if missing:
            judgment = None

        session.execute(
            stmt.values(
                eval_topic_rts_id=eval_topic_rts_id,
                collection=collection,
                tweet_id=tweet_id,
                judgment=judgment if set_judgments else None,
                position=line_no if set_position else None,
                missing=missing,
            )
        )

    session.commit()


@cli.command()
@click.option('--session', default='postgresql:///twitter', callback=create_session)
@click.option('--collection')
@click.option('--qrels_file', type=click.File())
def insert_eval_crowd_relevance_judgements(session, collection, qrels_file):
    table = fw_model.EvalRelevanceJudgment.__table__
    stmt = postgresql.insert(
        table,
    )
    stmt = stmt.on_conflict_do_update(
        constraint=table.primary_key,
        set_={
            'crowd_relevant': stmt.excluded.crowd_relevant,
            'crowd_not_relevant': stmt.excluded.crowd_not_relevant,
        },
    )

    judgments = {}

    for line in qrels_file:
        eval_topic_rts_id, _, tweet_id, judgment, _ = line.split()
        tweet_id = int(tweet_id)
        judgment = int(judgment)

        judgments.setdefault((tweet_id, eval_topic_rts_id), {}).setdefault(judgment, []).append(judgment)

    for (tweet_id, eval_topic_rts_id), js in judgments.items():
        relevant = len(js.get(1, [])) + len(js.get(2, []))
        not_relevant = len(js.get(0, []))

        session.execute(
            stmt.values(
                eval_topic_rts_id=eval_topic_rts_id,
                collection=collection,
                tweet_id=tweet_id,
                crowd_relevant=relevant,
                crowd_not_relevant=not_relevant,
            )
        )

    session.commit()


@cli.command()
@click.option('--session', default='postgresql:///twitter', callback=create_session)
@click.option('--collection')
@click.option('--cluster_glosses_file', type=click.File())
def insert_eval_cluster_glosses(session, collection, cluster_glosses_file):
    stmt = sa.insert(fw_model.EvalCluster.__table__)

    for line in cluster_glosses_file:
        eval_topic_rts_id, rts_id, gloss = line.split(maxsplit=2)
        gloss = gloss.strip()

        session.execute(
            stmt.values(
                eval_topic_rts_id=eval_topic_rts_id,
                eval_topic_collection=collection,
                rts_id=rts_id,
                gloss=gloss,
            )
        )

    session.commit()


@cli.command()
@click.option('--session', default='postgresql:///twitter', callback=create_session)
@click.option('--collection')
@click.option('--clusters_file', type=click.File())
def insert_eval_clusters(session, collection, clusters_file):
    stmt = sa.insert(fw_model.EvalClusterAssignment.__table__)

    for line in clusters_file:
        eval_topic_rts_id, eval_cluster_rts_id, tweet_id = line.split()

        try:
            tweet_id = int(tweet_id)
        except ValueError:
            logger.warning('Invalid tweet id: %s', tweet_id)
            continue

        session.execute(
            stmt.values(
                eval_topic_rts_id=eval_topic_rts_id,
                eval_topic_collection=collection,
                eval_cluster_rts_id=eval_cluster_rts_id,
                tweet_id=tweet_id,
            )
        )

    session.commit()


if __name__ == '__main__':
    cli()
