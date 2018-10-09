FROM python:3.6

LABEL "description"="IOTA ZeroMQ to Websocket proxy"
LABEL "version"="0.1"
LABEL "maintainer"="github.com/lukas-hetzenecker"

ADD . /app
WORKDIR /app

RUN pip install -r requirements.txt
ENTRYPOINT ["python", "proxy.py"]

