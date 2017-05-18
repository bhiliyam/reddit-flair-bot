from collections import deque
import os
import os.path
import pickle
import urlparse
from time import time

import praw
import psycopg2
# Authentication info (manually set Heroku config for your reddit app)
CLIENT_ID = os.environ["CLIENT_ID"]
CLIENT_SECRET = os.environ["CLIENT_SECRET"]
USERNAME = os.environ["USERNAME"]
PASSWORD = os.environ["PASSWORD"]
USER_AGENT = 'FlairBotv0.1'

# PostgreSQL database url (set by Heroku when you add PostgreSQL addon)
DATABASE_URL = os.environ["DATABASE_URL"]

# Text of comment that will be posted as warning
FLAIR_WARNING = 'Add a flair to your post, bruh'
# Number of seconds to wait before posting warning
IGNORE_PERIOD = 10
# Number of seconds to wait before removing post
GRACE_PERIOD = 60
# Ignore posts that are older than this
NEGLECT_AGE = 600

class Bot(object):
    def __init__(self):
        self.r = praw.Reddit(client_id=CLIENT_ID,
                             client_secret=CLIENT_SECRET,
                             username=USERNAME,
                             password=PASSWORD,
                             user_agent=USER_AGENT)
        super(Bot, self).__init__()


class FlairMixin(object):
    def __init__(self):
        self._message = FLAIR_WARNING
        self._queue = deque()
        self._pending = set()
        super(FlairMixin, self).__init__()

    @staticmethod
    def has_flair(post):
        return post.link_flair_css_class is not None

    @staticmethod
    def elapsed(post):
        return time() - post.created_utc

    def should_warn(self, post):
        if post.id in self._pending:
            return False
        if self.elapsed(post) > NEGLECT_AGE:
            return False
        return (not self.has_flair(post)) and self.elapsed(post) > IGNORE_PERIOD

    def warn_user(self, post):
        print 'Add warning on post', post.id
        comment = post.reply(self._message)
        self._pending.add(post.id)
        self._queue.append((post, comment))

    def flair_action(self, post):
        if self.should_warn(post):
            self.warn_user(post)

    def manage_queue(self):
        q = self._queue
        while q:
            post, comment = q[0]
            if self.elapsed(post) < GRACE_PERIOD:
                break
            q.popleft()
            self._pending.remove(post.id)
            post = self.r.submission(post.id)
            if self.has_flair(post):
                print 'User added flair on post', post.id
                print 'Remove comment', comment.id
                comment.delete()
            else:
                print 'Remove post', post.id
                post.mod.remove()


class FlairMixinDB(FlairMixin):
    def __init__(self):
        super(FlairMixinDB, self).__init__()
        urlparse.uses_netloc.append("postgres")
        url = urlparse.urlparse(DATABASE_URL)
        self.conn = psycopg2.connect(
            database=url.path[1:],
            user=url.username,
            password=url.password,
            host=url.hostname,
            port=url.port
        )
        self.recover()

    @staticmethod
    def _db_send_update(cur, k, v):
        cur.execute("UPDATE data SET value = %s WHERE id = %s", (pickle.dumps(v), k))

    @staticmethod
    def _db_query(cur, k):
        cur.execute("SELECT value FROM data WHERE id = %s", (k,))
        return pickle.loads(cur.fetchone()[0])

    def save(self):
        cur = self.conn.cursor()
        self._db_send_update(cur, 'accessed', time())
        self._db_send_update(cur, 'pending', self._pending)
        self._db_send_update(cur, 'queue', self._queue)
        self.conn.commit()

    def recover(self):
        cur = self.conn.cursor()
        self._pending = self._db_query(cur, 'pending')
        self._queue = self._db_query(cur, 'queue')

        print "<Recovery>"
        print "pending:", self._pending
        print "queue:", self._queue

        if not self._pending:
            self._pending = set()
        if not self._queue:
            self._queue = deque()

    def flair_action(self, post):
        super(FlairMixinDB, self).flair_action(post)
        self.save()

    def manage_queue(self):
        super(FlairMixinDB, self).manage_queue()
        self.save()


class MyModerationBot(Bot, FlairMixinDB):
    def __init__(self):
        super(MyModerationBot, self).__init__()

    def loop(self):
        while True:
            self.moderate_new()
            self.manage_queue()

    def moderate_new(self):
        subreddit = self.r.subreddit('my_playground')
        for post in subreddit.new(limit=20):
            self.flair_action(post)


def main():
    bot = MyModerationBot()
    bot.loop()

if __name__ == '__main__':
    main()
