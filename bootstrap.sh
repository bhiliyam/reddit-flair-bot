#!/bin/bash
heroku create
source config.sh
heroku config:set CLIENT_ID=$CLIENT_ID CLIENT_SECRET=$CLIENT_SECRET \
    USERNAME=$USERNAME PASSWORD=$PASSWORD

if [ -z "$DATABASE_URL" ]; then
    heroku addons:create heroku-postgresql:hobby-dev
else
    heroku config:set DATABASE_URL=$DATABASE_URL
fi

git push heroku master
heroku ps:scale flairbot=1

