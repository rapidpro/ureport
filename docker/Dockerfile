FROM python:3.6

ENV WORKDIR /ureport
WORKDIR $WORKDIR

RUN apt update
RUN apt upgrade -y
RUN apt install -y \
    varnish \
    gettext \
    supervisor \
    curl \
    software-properties-common

RUN curl -sL https://deb.nodesource.com/setup_10.x | bash -
RUN apt update
RUN apt install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

COPY varnish.default.vcl /etc/varnish/default.vcl
COPY pip-freeze.txt .

RUN pip install -r pip-freeze.txt
RUN npm install -g less coffeescript

COPY . .
RUN ln -s $WORKDIR/ureport/settings.py.prod $WORKDIR/ureport/settings.py

EXPOSE 8000
EXPOSE 8080

RUN chmod +x ./docker-entrypoint.sh
RUN chmod +x ./app-entrypoint.sh

ENTRYPOINT ["sh", "docker-entrypoint.sh"]
CMD ["supervisor"]
