FROM python:3.10.6-slim as build-poetry

WORKDIR /app

COPY ./pyproject.toml .
COPY ./poetry.lock .

RUN python -m pip install -U poetry
RUN poetry export --without-hashes --output requirements.txt

FROM python:3.10.6-slim-buster AS base

ARG APP_UID=1000
ARG APP_GID=1000

ARG NODE_VERSION="18"

ARG BUILD_DEPS="\
  python3-dev \
  build-essential \
  gettext \
  git cmake \
  autoconf pkg-config autoconf libtool automake"

ARG NODE_BUILD_DEPS="less coffeescript"

ARG RUNTIME_DEPS="\
  tzdata \
  curl \
  gosu \
  gettext \
  libpq5"

ARG NODE_RUNTIME_DEPS=${NODE_BUILD_DEPS}

ARG APP_PORT="8000"

ARG APP_VERSION="0.1"

# set environment variables
ENV PROJECT_PATH="/ureport"

ENV APPLICATION_NAME="U-Report"

ENV APP_VERSION=${APP_VERSION} \
  RUNTIME_DEPS=${RUNTIME_DEPS} \
  BUILD_DEPS=${BUILD_DEPS} \
  NODE_RUNTIME_DEPS=${NODE_RUNTIME_DEPS} \
  NODE_BUILD_DEPS=${NODE_BUILD_DEPS} \
  NODE_VERSION=${NODE_VERSION} \
  APP_UID=${APP_UID} \
  APP_GID=${APP_GID} \
  PYTHONDONTWRITEBYTECODE=1 \
  PYTHONUNBUFFERED=1 \
  PYTHONIOENCODING=UTF-8 \
  PIP_DISABLE_PIP_VERSION_CHECK=1 \
  PATH="/install/bin:${PATH}" \
  APP_PORT=${APP_PORT}

LABEL app=${VERSION} \
  os="debian" \
  os.version="10" \
  name="${APPLICATION_NAME} ${APP_VERSION}" \
  description="${APPLICATION_NAME} image" \
  maintainer="${APPLICATION_NAME} Team"

RUN addgroup --gid "${APP_GID}" app_group \
  && useradd --system -m -d ${PROJECT_PATH} -u "${APP_UID}" -g "${APP_GID}" app_user

# set work directory
WORKDIR ${PROJECT_PATH}

FROM base AS build

RUN if [ ! "x${NODE_BUILD_DEPS}" = "x" ] ; then apt-get update \
 && apt-get install -y --no-install-recommends curl -y \
 && curl -sL https://deb.nodesource.com/setup_"${NODE_VERSION}".x | bash - \
 && apt-get install -y nodejs \
 && npm install -g ${NODE_BUILD_DEPS} ; fi

RUN if [ ! "x${BUILD_DEPS}" = "x" ] ; then apt-get update \
  && apt-get install -y --no-install-recommends ${BUILD_DEPS} ; fi

# install dependencies
COPY --from=build-poetry /app/requirements.txt .
COPY weni_requirements.txt .

RUN mkdir /install \
  && pip install --no-cache-dir --prefix=/install -r requirements.txt \
  && pip install --no-cache-dir --prefix=/install -r weni_requirements.txt

FROM base

COPY --from=build /install /usr/local
COPY --from=build --chown=app_user:app_group ${PROJECT_PATH} ${PROJECT_PATH}

RUN if [ ! "x${NODE_RUNTIME_DEPS}" = "x" ] ; then apt-get update \
 && apt-get install -y --no-install-recommends curl -y \
 && curl -sL https://deb.nodesource.com/setup_"${NODE_VERSION}".x | bash - \
 && apt-get install -y nodejs \
 && npm install -g ${NODE_RUNTIME_DEPS} ; fi

RUN apt-get update \
  && SUDO_FORCE_REMOVE=yes apt-get remove --purge -y ${BUILD_DEPS} \
  && apt-get autoremove -y \
  && apt-get install -y --no-install-recommends ${RUNTIME_DEPS} \
  && rm -rf /usr/share/man \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

# copy project
COPY --chown=app_user:app_group . . 
RUN ln -s "${PROJECT_PATH}"/ureport/settings.py.prod "${PROJECT_PATH}"/ureport/settings.py

ENTRYPOINT ["/ureport/docker-entrypoint.sh"]

CMD ["start"]
#CMD sleep 6d

HEALTHCHECK --interval=15s --timeout=20s --start-period=60s \
  CMD "${PROJECT_PATH}"/docker-entrypoint.sh healthcheck
