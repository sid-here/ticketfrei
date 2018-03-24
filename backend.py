#!/usr/bin/env python3

import logging
import time

import sendmail
from db import DB
from config import config

from mastodonbot import MastodonBot
from twitterbot import TwitterBot
from mailbot import Mailbot
from trigger import Trigger


def get_users(db):
    user_rows = db.get_users()
    users = {}
    for row in user_rows:
        users[row[0]] = []
    return users


def init_bots(config, db, users):
    for uid in users:
        users[uid].append(Trigger(config, uid, db))
        users[uid].append(MastodonBot(config, uid, db))
        users[uid].append(TwitterBot(config, uid, db))
        users[uid].append(Mailbot(config, uid, db))
    return users


if __name__ == '__main__':
    logpath = config['logging']['logpath']
    logger = logging.getLogger()
    fh = logging.FileHandler(logpath)
    fh.setLevel(logging.DEBUG)
    logger.addHandler(fh)

    db = DB()

    while True:
        # get a dictionary { uid : [ Bot objects ] }
        users = get_users(db)

        # initialize bots
        users = init_bots(config, logger, db, users)

        try:
            for uid in users:
                for bot in users[uid]:
                    reports = bot.crawl()
                    for status in reports:
                        if not users[uid][0].is_ok(status.text):
                            continue
                        for bot2 in users[uid]:
                            if bot == bot2:
                                bot2.repost(status)
                            else:
                                bot2.post(status)
                time.sleep(60)  # twitter rate limit >.<
        except KeyboardInterrupt:
            print("Good bye. Remember to restart the bot!")
        except:
            logger.error('Shutdown', exc_info=True)
            for uid in users:
                for bot in users[uid]:
                    bot.save_last()
            mailer = sendmail.Mailer(config)
            try:
                mailer.send('', config['web']['contact'],
                            'Ticketfrei Crash Report',
                            attachment=config['logging']['logpath'])
            except:
                logger.error('Mail sending failed', exc_info=True)
