"""
Handles new tweets
"""
import MySQLdb

import Queue
from threading import Timer, Thread
from tweepy import OAuthHandler
from tweepy import Stream
from tweepy import StreamListener

from dynhashtag.config import (MYSQL_DB, MYSQL_USER, MYSQL_PWD, MYSQL_HOST,
    REMODEL, CONSUMER_SECRET, CONSUMER_KEY, ACCESS_TOKEN_SECRET,
    ACCESS_TOKEN)
from dynhashtag.classifier import AdaptiveTweetClassifierTrainer
from dynhashtag.util import extract_entity


class TweetStreamListener(StreamListener):
    """ A listener handles tweets are the received from the stream.
    This is a basic listener that just prints received tweets to stdout.

    """

    insert_tweet_query = u"""INSERT INTO tweets (\
            tweet_id,user,created_at,in_reply_to_user_id_str,\
            in_reply_to_status_id_str,retweeted,favorited,\
            favorite_count,retweet_count,source,\
            tweet,urls,hashtags,user_mentions) VALUES (\
            %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"""

    insert_user_query = u"""INSERT IGNORE INTO users (\
            user_id,created_at,description,favourites_count,\
            followers_count,friends_count,status_count,\
            listed_count,time_zone,verified,geo_enabled,lang,\
            location,screen_name) VALUES (%s,%s,%s,%s,%s,%s,
            %s, %s, %s, %s, %s, %s, %s, %s)"""

    def __init__(self, trainer, queue):
        """
        :param trainer: Instance used to create features and train a new
        classifier
        :param queue: Queue for retrieving classifiers
        """
        StreamListener.__init__(self)
        self.trainer = trainer
        self.classifier = None
        self.queue = queue

        self.timer = Timer(REMODEL, self.retrain)
        self.timer.start()

    def retrain(self):
        """
        Retrain the model in a different thread, restart streaming
        """
        thread = Thread(target=self.trainer.train_classifier)
        thread.start()

    def connect_db(self):
        """
        Connect to the database
        """
        self.connection = MySQLdb.connect(
            host=MYSQL_HOST, passwd=MYSQL_PWD,
            user=MYSQL_USER, db=MYSQL_DB)

    def on_connect(self):
        self.connect_db()

    def on_event(self, status):
        print status

    def on_status(self, data):
        """
        Write received tweets to file
        Format:

        """
        if 'text' not in data or not self.classifier:
            return

        features = trainer.get_feature_vector(data)
        if not self.classifier.predict(features):
            return

        print "Tweet arriving"

        hashtags, user_mentions = extract_entity(data)
        tweet = data['text']
        user_id = data['user']['id_str']

        # BUG in python (fixed in python 3.2): %z not supported in strptime
        date = data['created_at'].strptime("%a %b %d %H:%M:%S +0000 %Y")
        statement = "%s;%s" % (self.insert_tweet_query, self.insert_user_query)

        try:
            cursor = self.connection.cursor()
            cursor.execute(statement, (
                data['id'], user_id, date.strftime("%Y-%m-%d %H:%M:%S"),
                data['in_reply_to_user_id_str'], data['in_reply_to_status_id_str'],
                data['retweeted'], data['favorited'], data['favorite_count'],
                data['retweet_count'], data['source'], tweet, data['urls'], hashtags,
                user_mentions, user_id, data['user']['created_at'], data['user']['description'],
                data['user']['favourites_count'], data['user']['followers_count'],
                data['user']['friends_count'], data['user']['statuses_count'],
                data['user']['listed_count'], data['user']['time_zone'],
                data['user']['verified'], data['user']['geo_enabled'],
                data['user']['lang'], data['user']['location'],
                data['user']['screen_name']))
            cursor.close()
            self.connection.commit()
        except Exception as inst:
            print type(inst)     # the exception instance
            print inst.args      # arguments stored in .args
            print inst           # __str__ allows args to printed directly

        if not self.queue.empty():
            self.classifier = self.queue.get()
            return False # force a restart of the stream
        else:
            return True

    def on_error(self, status):
        print status

if __name__ == '__main__':
    query_set = dict()
    query_set['keyword'] = ['obama']
    query_set['user'] = []
    queue = Queue.Queue()
    trainer = AdaptiveTweetClassifierTrainer(queue)
    l = TweetStreamListener(trainer, queue)
    auth = OAuthHandler(CONSUMER_KEY, CONSUMER_SECRET)
    auth.set_access_token(ACCESS_TOKEN, ACCESS_TOKEN_SECRET)
    stream = Stream(auth, l)

    while 1:
        query_set = trainer.get_query_set()
        stream.filter(follow=query_set['user'], track=query_set['keyword'])