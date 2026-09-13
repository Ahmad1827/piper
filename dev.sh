#!/usr/bin/env bash

sudo service postgresql status > /dev/null || sudo service postgresql start

stripe listen --forward-to localhost:8000/api/v1/webhooks/stripe &
STRIPE_PID=$!

trap "kill $STRIPE_PID 2>/dev/null" EXIT INT TERM

source venv/bin/activate
uvicorn main:app --reload
